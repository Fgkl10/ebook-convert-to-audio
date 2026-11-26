"""Convert an ebook into library/<book_id>/ with one .m4a per chapter + book.json.

Usage:
    python -m desktop.build path/to/book.epub [--voice af_heart] [--speed 1.0] [--out library]

Sentence timestamps are exact: every sentence is synthesized separately and
we know its sample offset when stitching the chapter together.
Per-sentence audio is cached under cache/ so an interrupted run resumes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import numpy as np

from .parse import Book, load_book
from .segment import split_text
from .tts import DEFAULT_VOICE, SAMPLE_RATE

ROOT = Path(__file__).resolve().parent.parent
SENTENCE_GAP_S = 0.25
PARAGRAPH_GAP_S = 0.6
CHAPTER_LEAD_S = 0.3

# progress(done_sentences, total_sentences, message)
ProgressFn = Callable[[int, int, str], None]


def make_book_id(book: Book, source: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", book.title.lower()).strip("-")[:40] or "book"
    digest = hashlib.sha1(source.read_bytes()).hexdigest()[:8]
    return f"{slug}-{digest}"


def plan_chapters(book: Book) -> list[list[list[str]]]:
    """chapters -> paragraphs -> sentences"""
    return [split_text(ch.text) for ch in book.chapters]


def assemble_chapter(
    paragraphs: list[list[str]],
    synth: Callable[[str], np.ndarray],
    on_sentence: Callable[[], None] | None = None,
) -> tuple[np.ndarray, list[dict]]:
    """Synthesize and stitch one chapter. Returns (audio, sentences-with-timestamps).

    end_ms of a sentence == start_ms of the next one (the pause belongs to the
    sentence before it), so every playback position maps to exactly one sentence.
    """
    sent_gap = np.zeros(int(SENTENCE_GAP_S * SAMPLE_RATE), dtype=np.float32)
    para_gap = np.zeros(int(PARAGRAPH_GAP_S * SAMPLE_RATE), dtype=np.float32)
    pieces: list[np.ndarray] = [np.zeros(int(CHAPTER_LEAD_S * SAMPLE_RATE), dtype=np.float32)]
    pos = len(pieces[0])
    sentences: list[dict] = []
    for p_idx, para in enumerate(paragraphs):
        for s_idx, text in enumerate(para):
            audio = synth(text)
            sentences.append({"i": len(sentences), "p": p_idx, "text": text, "start_ms": round(pos * 1000 / SAMPLE_RATE)})
            pieces.append(audio)
            pos += len(audio)
            gap = para_gap if s_idx == len(para) - 1 else sent_gap
            pieces.append(gap)
            pos += len(gap)
            if on_sentence:
                on_sentence()
    total_ms = round(pos * 1000 / SAMPLE_RATE)
    for a, b in zip(sentences, sentences[1:]):
        a["end_ms"] = b["start_ms"]
    if sentences:
        sentences[-1]["end_ms"] = total_ms
    return np.concatenate(pieces), sentences


def encode_m4a(audio: np.ndarray, out_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    tmp = out_path.with_suffix(".tmp.m4a")
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", "pipe:0",
        "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(tmp),
    ]
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 1.0:
        audio = audio / peak
    proc = subprocess.run(cmd, input=audio.astype("<f4").tobytes(), capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode(errors='replace')}")
    tmp.replace(out_path)


class CachedSynth:
    """Caches each sentence's audio on disk keyed by (voice, speed, text)."""

    def __init__(self, tts, cache_dir: Path):
        self.tts = tts
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, text: str) -> np.ndarray:
        key = hashlib.sha1(f"{self.tts.voice}|{self.tts.speed}|{text}".encode()).hexdigest()
        f = self.cache_dir / f"{key}.npy"
        if f.exists():
            return np.load(f)
        audio = self.tts.synth(text)
        np.save(f, audio)
        return audio


def build_book(
    source: str | Path,
    out_root: str | Path = ROOT / "library",
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    progress: ProgressFn | None = None,
    tts=None,
) -> Path:
    source = Path(source)
    out_root = Path(out_root)
    book = load_book(source)
    book_id = make_book_id(book, source)
    out_dir = out_root / book_id
    out_dir.mkdir(parents=True, exist_ok=True)

    plans = plan_chapters(book)
    total = sum(len(p) for chapter in plans for p in chapter)
    done = 0

    def report(msg: str) -> None:
        if progress:
            progress(done, total, msg)

    report("Loading TTS model")
    if tts is None:
        from .tts import KokoroTTS

        tts = KokoroTTS(voice=voice, speed=speed)
    synth = CachedSynth(tts, ROOT / "cache" / book_id)

    cover_name = None
    if book.cover:
        cover_name = f"cover{book.cover_ext}"
        (out_dir / cover_name).write_bytes(book.cover)

    manifest = {
        "id": book_id,
        "title": book.title,
        "author": book.author,
        "cover": cover_name,
        "voice": tts.voice,
        "speed": tts.speed,
        "complete": False,
        "created": int(time.time()),
        "chapters": [],
    }
    manifest_path = out_dir / "book.json"

    def write_manifest() -> None:
        manifest["duration_ms"] = sum(c["duration_ms"] for c in manifest["chapters"])
        tmp = manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(manifest_path)

    for idx, (chapter, paragraphs) in enumerate(zip(book.chapters, plans)):
        if not paragraphs:
            continue
        report(f"Chapter {idx + 1}/{len(plans)}: {chapter.title}")

        def tick() -> None:
            nonlocal done
            done += 1
            if done % 5 == 0:
                report(f"Chapter {idx + 1}/{len(plans)}: {chapter.title}")

        audio, sentences = assemble_chapter(paragraphs, synth, tick)
        audio_name = f"ch{idx:03d}.m4a"
        encode_m4a(audio, out_dir / audio_name)
        manifest["chapters"].append({
            "index": len(manifest["chapters"]),
            "title": chapter.title,
            "audio": audio_name,
            "duration_ms": round(len(audio) * 1000 / SAMPLE_RATE),
            "sentences": sentences,
        })
        write_manifest()  # partial books are already playable

    manifest["complete"] = True
    write_manifest()
    shutil.rmtree(ROOT / "cache" / book_id, ignore_errors=True)
    report("Done")
    return out_dir


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Convert an ebook to an audiobook with sentence timestamps.")
    ap.add_argument("source")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", default=str(ROOT / "library"))
    args = ap.parse_args(argv)

    start = time.time()

    def progress(done: int, total: int, msg: str) -> None:
        pct = 100 * done / total if total else 0
        sys.stdout.write(f"\r[{pct:5.1f}%] {done}/{total} sentences  {msg[:60]:<60}")
        sys.stdout.flush()

    out = build_book(args.source, args.out, args.voice, args.speed, progress)
    print(f"\nWrote {out} in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
