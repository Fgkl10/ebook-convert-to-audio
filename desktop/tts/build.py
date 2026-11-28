"""Convert an ebook into library/<book_id>/ with one .m4a per chapter + book.json.

Usage:
    ebook-normalize path/to/book.epub     # first: writes book.std.epub to review
    ebook-convert path/to/book.std.epub [--voice af_heart] [--speed 1.0] [--out library]
    ebook-convert path/to/book.epub --list-chapters
    ebook-convert path/to/book.epub --chapters 3        # or 2-4, or 1,3,5-6
    ebook-convert path/to/book.epub --ignore-language   # skip the English check

--chapters converts only those chapters (1-based, as --list-chapters numbers them) into a
separate library/<book_id>-ch<spec>/ folder, so a test conversion never touches the full book.

Sentence timestamps are exact: every sentence is synthesized separately and
we know its sample offset when stitching the chapter together.
Per-sentence audio is cached under cache/ so an interrupted run resumes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from .. import PROJECT
from ..core.language import check_language
from ..core.parse import Book, load_book
from ..core.segment import split_text
from .kokoro import DEFAULT_VOICE, SAMPLE_RATE

# Data folder for library/, cache/ and drafts/: the project, unless EBOOK_AUDIO_DATA points elsewhere (D-032), so a
# second server (e.g. for testing) can run without touching the first one's books.
ROOT = Path(os.environ.get("EBOOK_AUDIO_DATA") or PROJECT).resolve()
SENTENCE_GAP_S = 0.25
PARAGRAPH_GAP_S = 0.6
CHAPTER_LEAD_S = 0.3

# progress(done_sentences, total_sentences, message)
ProgressFn = Callable[[int, int, str], None]


def make_book_id(book: Book, source: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", book.title.lower()).strip("-")[:40] or "book"
    # A standard EPUB carries the original file's hash, so re-normalizing or editing it in Sigil
    # keeps the same book_id (and the per-sentence cache).
    digest = (book.source_hash or hashlib.sha1(source.read_bytes()).hexdigest())[:8]
    return f"{slug}-{digest}"


def parse_chapter_spec(spec: str, count: int) -> list[int]:
    """"3", "2-4", "1,3,5-6" (1-based, inclusive) -> sorted 0-based indices. Raises ValueError."""
    picked: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            raise ValueError(f"Bad chapter spec {spec!r}: use e.g. 3, 2-4 or 1,3,5-6")
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        if lo < 1 or hi < lo or hi > count:
            raise ValueError(f"Chapters {part} out of range: this book has chapters 1-{count}")
        picked.update(range(lo - 1, hi))
    return sorted(picked)


class Cancelled(Exception):
    """A conversion stopped on request (build_book's cancel event); not an error."""


def select_chapters(chapters: str | list[int] | None, count: int) -> list[int]:
    """Which chapters to convert, as sorted 0-based indices. None = all; a spec string as on the command line;
    or a list of 1-based numbers (the web page). Raises ValueError."""
    if chapters is None:
        return list(range(count))
    if isinstance(chapters, str):
        return parse_chapter_spec(chapters, count)
    if not chapters:
        raise ValueError("Pick at least one chapter")
    if len(set(chapters)) != len(chapters):
        raise ValueError("A chapter is listed twice")
    for n in chapters:
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= count:
            raise ValueError(f"Chapter {n} out of range: this book has chapters 1-{count}")
    return sorted(n - 1 for n in chapters)


def chapter_text_sha1(text: str) -> str:
    """Identifies a chapter's text, so a chapter edited after it was converted can be told apart."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


_AUDIO_NAME_RE = re.compile(r"ch(\d{3,})\.m4a")


def chapter_number(chapter: dict, pos: int, manifest: dict) -> int:
    """A manifest chapter's 1-based number in the cleaned book. Books written before D-035 have no "number": for a
    full book the audio name holds the original index (empty chapters were skipped, so the position can be off);
    an old --chapters test folder named its audio by place in the selection, so the number comes from its spec
    when the spec selects exactly as many chapters as the folder holds, else from the position."""
    if chapter.get("number"):
        return int(chapter["number"])
    spec = manifest.get("chapter_selection")
    if not spec:
        m = _AUDIO_NAME_RE.fullmatch(chapter.get("audio") or "")
        return int(m.group(1)) + 1 if m else pos + 1
    try:
        selected = parse_chapter_spec(str(spec), 10**6)
    except ValueError:
        return pos + 1
    if len(selected) == len(manifest.get("chapters") or []):
        return selected[pos] + 1
    return pos + 1  # an empty chapter inside the selection was skipped: which one is unknown


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


TMP_SUFFIX = ".tmp"            # sentence cache: <key>.npy.tmp while it is written
TMP_M4A_SUFFIX = ".tmp.m4a"    # chapter audio and voice samples: <name>.tmp.m4a while ffmpeg writes it
LEFTOVER_SUFFIXES = (TMP_M4A_SUFFIX, ".npy" + TMP_SUFFIX)


def remove_leftovers(*folders: Path) -> list[Path]:
    """Delete half-written files that an interrupted run (Ctrl+C, crash) left in these folders, recursively.
    Only call it when nothing else is writing there (server start)."""
    removed = []
    for folder in folders:
        if not folder.exists():
            continue
        for f in folder.rglob("*"):
            if f.name.endswith(LEFTOVER_SUFFIXES) and f.is_file():
                f.unlink(missing_ok=True)
                removed.append(f)
    return removed


def encode_m4a(audio: np.ndarray, out_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    tmp = out_path.with_suffix(TMP_M4A_SUFFIX)
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

    def path(self, text: str) -> Path:
        key = hashlib.sha1(f"{self.tts.voice}|{self.tts.speed}|{text}".encode()).hexdigest()
        return self.cache_dir / f"{key}.npy"

    def __call__(self, text: str) -> np.ndarray:
        f = self.path(text)
        if f.exists():
            try:
                return np.load(f)
            except (ValueError, EOFError, OSError):  # cut off by a version before atomic writes: make it again
                f.unlink(missing_ok=True)
        audio = self.tts.synth(text)
        # Atomic: a Ctrl+C mid-write leaves only <key>.npy.tmp (removed at server start), never a half <key>.npy.
        # Through a file handle, because np.save(path) would append ".npy" to the temp name.
        tmp = f.with_name(f.name + TMP_SUFFIX)
        with open(tmp, "wb") as fh:
            np.save(fh, audio)
        os.replace(tmp, f)
        return audio


def build_book(
    source: str | Path,
    out_root: str | Path = ROOT / "library",
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    progress: ProgressFn | None = None,
    tts=None,
    chapters: str | list[int] | None = None,
    ignore_language: bool = False,
    merge: bool = False,
    cancel: threading.Event | None = None,
) -> Path:
    """Convert the book, or only the chosen chapters (see select_chapters).

    merge=False: a spec string writes a separate <book_id>-ch<spec>/ test folder (D-017); no selection rewrites
    the whole book. merge=True (the server, D-035): the chosen chapters are added to <book_id>/, replacing the same
    chapters if they were converted before and keeping all the others.
    Chapters keep their number in the cleaned book: audio ch{number-1:03d}.m4a, "number" in book.json.
    cancel: when set, the run stops at the next sentence with Cancelled (D-038). Finished chapters stay in book.json
    and the sentences made so far stay cached, so the same call later resumes.
    """
    source = Path(source)
    out_root = Path(out_root)
    book = load_book(source)
    if not ignore_language:
        check_language(book)  # before the TTS model loads
    book_id = make_book_id(book, source)
    selected = select_chapters(chapters, len(book.chapters))
    test_folder = isinstance(chapters, str) and not merge
    if test_folder:
        book_id = f"{book_id}-ch{chapters.replace(' ', '').replace(',', '_')}"
    out_dir = out_root / book_id
    out_dir.mkdir(parents=True, exist_ok=True)

    plans = plan_chapters(book)
    todo = [i for i in selected if plans[i]]  # chapters with no sentences are skipped
    # The numbers this folder should hold when it is complete: the selection for a test folder, else the whole book.
    wanted = {i + 1 for i in (todo if test_folder else range(len(plans))) if plans[i]}
    total = sum(len(p) for i in todo for p in plans[i])
    done = 0

    def report(msg: str) -> None:
        if progress:
            progress(done, total, msg)

    report("Loading TTS model")
    if tts is None:
        from .kokoro import KokoroTTS

        tts = KokoroTTS(voice=voice, speed=speed)
    synth = CachedSynth(tts, ROOT / "cache" / book_id)

    cover_name = None
    if book.cover:
        cover_name = f"cover{book.cover_ext}"
        (out_dir / cover_name).write_bytes(book.cover)

    manifest_path = out_dir / "book.json"
    kept: list[dict] = []
    created = int(time.time())
    if merge and manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        created = old.get("created") or created
        for pos, c in enumerate(old.get("chapters", [])):
            kept.append({**c, "number": chapter_number(c, pos, old)})  # old books: fill in the number once
    manifest = {
        "id": book_id,
        "title": book.title,
        "author": book.author,
        "cover": cover_name,
        "voice": tts.voice,  # of the latest run; each chapter has its own
        "speed": tts.speed,
        "complete": False,
        "chapter_selection": chapters if test_folder else None,  # only a CLI test folder is a selection
        "chapters_total": len(wanted),
        "created": created,
        "chapters": kept,
    }

    def write_manifest() -> None:
        manifest["chapters"].sort(key=lambda c: c["number"])
        for pos, c in enumerate(manifest["chapters"]):
            c["index"] = pos
        manifest["duration_ms"] = sum(c["duration_ms"] for c in manifest["chapters"])
        manifest["complete"] = wanted <= {c["number"] for c in manifest["chapters"]}
        tmp = manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(manifest_path)

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled("Cancelled")

    for idx in todo:
        check_cancel()
        chapter, paragraphs = book.chapters[idx], plans[idx]
        report(f"Chapter {idx + 1}/{len(plans)}: {chapter.title}")

        def tick() -> None:
            nonlocal done
            done += 1
            if done % 5 == 0:
                report(f"Chapter {idx + 1}/{len(plans)}: {chapter.title}")
            check_cancel()  # between sentences: the sentence just made is cached, ffmpeg is not running

        audio, sentences = assemble_chapter(paragraphs, synth, tick)
        audio_name = f"ch{idx:03d}.m4a"  # the chapter's index in the cleaned book, stable as chapters are added
        encode_m4a(audio, out_dir / audio_name)
        written = (out_dir / audio_name).stat()
        manifest["chapters"] = [c for c in manifest["chapters"] if c["number"] != idx + 1]
        manifest["chapters"].append({
            "index": 0,  # set in write_manifest
            "number": idx + 1,
            "title": chapter.title,
            "audio": audio_name,
            "duration_ms": round(len(audio) * 1000 / SAMPLE_RATE),
            "size_bytes": written.st_size,  # with "updated_ms": a phone can tell its copy is stale (D-038)
            "updated_ms": written.st_mtime_ns // 1_000_000,
            "voice": tts.voice,
            "speed": tts.speed,
            "text_sha1": chapter_text_sha1(chapter.text),
            "sentences": sentences,
        })
        write_manifest()  # partial books are already playable

    write_manifest()
    cache = ROOT / "cache" / book_id
    if manifest["complete"]:
        shutil.rmtree(cache, ignore_errors=True)
    else:  # other chapters' cached sentences stay, so an interrupted selection still resumes
        for idx in todo:
            for para in plans[idx]:
                for text in para:
                    synth.path(text).unlink(missing_ok=True)
    report("Done")
    return out_dir


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Convert an ebook to an audiobook with sentence timestamps.")
    ap.add_argument("source")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", default=str(ROOT / "library"))
    ap.add_argument("--chapters", help="convert only these chapters, e.g. 3, 2-4 or 1,3,5-6 (see --list-chapters)")
    ap.add_argument("--list-chapters", action="store_true", help="print the numbered chapter list and exit")
    ap.add_argument("--ignore-language", action="store_true",
                    help="skip the language check (for an English book that is wrongly refused)")
    args = ap.parse_args(argv)

    try:
        book = load_book(args.source)
    except ValueError as e:
        sys.exit(f"error: {e}")
    if args.list_chapters:
        for n, (ch, paras) in enumerate(zip(book.chapters, plan_chapters(book)), 1):
            print(f"{n:3}  {sum(map(len, paras)):5} sentences  {ch.title}")
        return
    if not book.normalized:  # the CLI converts only reviewed, standard EPUBs (D-019)
        sys.exit(f'error: {args.source} has not been cleaned yet. Run:\n'
                 f'  ebook-normalize "{args.source}"\n'
                 f'then check the .std.epub it writes and convert that file.')

    start = time.time()

    def progress(done: int, total: int, msg: str) -> None:
        pct = 100 * done / total if total else 0
        sys.stdout.write(f"\r[{pct:5.1f}%] {done}/{total} sentences  {msg[:60]:<60}")
        sys.stdout.flush()

    try:
        out = build_book(args.source, args.out, args.voice, args.speed, progress, chapters=args.chapters,
                         ignore_language=args.ignore_language)
    except ValueError as e:
        sys.exit(f"error: {e}")
    print(f"\nWrote {out} in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
