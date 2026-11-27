"""The backend: cleaning, conversion and the library, with no HTTP in it (D-032).

desktop/server/api.py is the only caller; it turns ServiceError into an HTTP status. Flow (D-029):
upload -> clean (drafts/<id>/, its own worker) -> review -> approve -> convert (Jobs worker) -> library/<book_id>/.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import BinaryIO

from ..core.normalize import OCR_MODES, normalize, write_std_epub
from ..core.parse import load_book
from ..tts.build import (LEFTOVER_SUFFIXES, ROOT, build_book, chapter_number, chapter_text_sha1, encode_m4a,
                         make_book_id, remove_leftovers, select_chapters)
from ..tts.kokoro import DEFAULT_VOICE, VOICES

LIBRARY = ROOT / "library"
DRAFTS = ROOT / "drafts"
SAMPLES = ROOT / "cache" / "voice-samples"
SAMPLE_TEXT = "Hello! This is how I sound when I read your books aloud. I hope you enjoy listening."
BOOK_TYPES = (".epub", ".pdf", ".txt")
STD = "book.std.epub"
_ID_RE = re.compile(r"^[a-z0-9\-]{1,80}$")


class ServiceError(Exception):
    """A refusal the user can act on; `status` is the HTTP status the API answers with."""
    status = 400


class Invalid(ServiceError):
    status = 400


class NotFound(ServiceError):
    status = 404


class Conflict(ServiceError):
    status = 409


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


_DRAFT_DEFAULTS = {
    "file": "", "source": "", "message": "", "done": 0, "total": 0, "auto": False, "voice": DEFAULT_VOICE,
    "speed": 1.0, "ocr": "auto", "error": None, "created": 0, "chapters": 0, "checks": 0, "job_id": None,
    "book_id": None, "source_sha1": "", "last_chapters": None,
}


def check_options(voice: str, speed: float) -> None:
    if voice not in VOICES:
        raise Invalid(f"Unknown voice {voice}")
    if not 0.5 <= speed <= 2.0:
        raise Invalid("Speed must be between 0.5 and 2.0")


# ---------------------------------------------------------------- drafts (clean + review)

class Drafts:
    """Uploaded books being cleaned or waiting for review. Each lives in <root>/<id>/ with the upload,
    book.std.epub, report.json and draft.json, so drafts survive a server restart."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.drafts: dict[str, dict] = {}
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.lock = threading.Lock()
        self._load()
        threading.Thread(target=self._worker, daemon=True).start()

    def _load(self) -> None:
        if not self.root.exists():
            return
        for d in self.root.iterdir():
            try:
                draft = json.loads((d / "draft.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for key, value in _DRAFT_DEFAULTS.items():  # fields added since an older version wrote the file
                draft.setdefault(key, value)
            # Work that was running when the server stopped did not finish.
            if draft["status"] == "cleaning":
                draft.update(status="error", error="Interrupted by a server restart: upload the book again.",
                             message="Failed")
            elif draft["status"] in ("queued", "converting"):
                draft.update(status="review", message="The server restarted before the conversion finished: "
                                                      "approve again to resume (finished sentences are kept).")
            self.drafts[draft["id"]] = draft
            _write_json(d / "draft.json", draft)

    def dir(self, draft_id: str) -> Path:
        if not _ID_RE.match(draft_id) or draft_id not in self.drafts:
            raise NotFound("No such draft")
        return self.root / draft_id

    def get(self, draft_id: str) -> dict:
        self.dir(draft_id)
        return self.drafts[draft_id]

    def update(self, draft_id: str, **fields) -> None:
        with self.lock:
            draft = self.drafts.get(draft_id)
            if draft is None:  # discarded meanwhile
                return
            draft.update(fields)
            if (self.root / draft_id).exists():
                _write_json(self.root / draft_id / "draft.json", draft)

    def create(self, upload: BinaryIO, filename: str, auto: bool = False, voice: str = DEFAULT_VOICE,
               speed: float = 1.0, ocr: str = "auto") -> dict:
        """Upload a book to clean. auto=True converts right after cleaning, with no review stop.
        ocr (PDF only): auto, always or never (D-030)."""
        check_options(voice, speed)
        if ocr not in OCR_MODES:
            raise Invalid(f"OCR must be one of {', '.join(OCR_MODES)}")
        if Path(filename).suffix.lower() not in BOOK_TYPES:
            raise Invalid("Upload an .epub, .pdf or .txt file")
        draft_id = uuid.uuid4().hex[:12]
        d = self.root / draft_id
        d.mkdir(parents=True)
        # Keep the file's own name: a TXT or PDF without metadata takes its title from it. The stem is capped
        # so long download names (200+ chars) stay under Windows' 260-character path limit.
        safe = Path(re.sub(r"[^A-Za-z0-9._ -]+", "_", filename).lstrip(". "))
        source = d / (safe.stem[:80].rstrip(" .") + safe.suffix.lower())
        if source.name in (STD, "draft.json", "report.json", "edited.epub") or not source.stem:
            source = d / ("book" + Path(filename).suffix.lower())
        with source.open("wb") as out:
            shutil.copyfileobj(upload, out)
        draft = {
            "id": draft_id, "file": filename, "source": source.name, "status": "cleaning", "message": "Waiting",
            "done": 0, "total": 0, "auto": auto, "voice": voice, "speed": speed, "ocr": ocr, "error": None,
            "created": time.time(), "chapters": 0, "checks": 0, "job_id": None, "book_id": None,
            "source_sha1": hashlib.sha1(source.read_bytes()).hexdigest(),
        }
        with self.lock:
            self.drafts[draft_id] = draft
            _write_json(d / "draft.json", draft)
        self.queue.put(draft_id)
        return draft

    def create_cleaned(self, upload: BinaryIO, filename: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> dict:
        """A book already cleaned (CLI, or edited in Sigil): no cleaning step, straight to conversion (D-030)."""
        check_options(voice, speed)
        draft_id = uuid.uuid4().hex[:12]
        d = self.root / draft_id
        d.mkdir(parents=True)
        with (d / STD).open("wb") as out:
            shutil.copyfileobj(upload, out)
        try:
            book = load_book(d / STD) if Path(filename).suffix.lower() == ".epub" else None
        except Exception:  # noqa: BLE001 - unreadable: refused below
            book = None
        if book is None or not book.normalized:
            shutil.rmtree(d, ignore_errors=True)
            raise Invalid("Not a cleaned book (.std.epub): clean it on the Clean page first.")
        draft = {
            "id": draft_id, "file": filename, "source": STD, "status": "review", "message": "Uploaded cleaned book",
            "done": 0, "total": 0, "auto": True, "voice": voice, "speed": speed, "ocr": "auto", "error": None,
            "created": time.time(), "chapters": 0, "checks": 0, "job_id": None, "book_id": None,
            # the original book's hash, so the library id and sentence cache match a cleaning on this server
            "source_sha1": book.source_hash or hashlib.sha1((d / STD).read_bytes()).hexdigest(),
        }
        with self.lock:
            self.drafts[draft_id] = draft
            _write_json(d / "draft.json", draft)
        self.set_report(draft_id, {
            "source": filename, "method": "uploaded cleaned book: converted as it is",
            "chapters": [[c.title, len(c.text)] for c in book.chapters],
            "removed": [], "unconfirmed": [], "notes": [], "checks": []})
        self.approve(draft_id, voice, speed)
        return draft

    def public(self) -> list[dict]:
        with self.lock:
            return [dict(d) for d in sorted(self.drafts.values(), key=lambda d: d["created"], reverse=True)]

    def detail(self, draft_id: str) -> dict:
        """The draft plus its cleaning report (None until cleaned)."""
        draft = self.get(draft_id)
        report = self.report(draft_id) if draft["status"] != "cleaning" and draft["chapters"] else None
        converted, book_voice, book_speed = [], None, None
        if report is not None:
            book = _std_book(self, draft_id)
            m = _library_manifest(make_book_id(book, self.root / draft_id / STD))
            if m is not None:
                book_voice, book_speed = m.get("voice"), m.get("speed")
                for pos, c in enumerate(m.get("chapters", [])):
                    n = chapter_number(c, pos, m)
                    # a chapter edited since it was converted counts as not converted; books before D-035 have no hash
                    if 1 <= n <= len(book.chapters) and c.get("text_sha1") in (
                            None, chapter_text_sha1(book.chapters[n - 1].text)):
                        converted.append(n)
        return {**draft, "report": report, "converted": sorted(set(converted)),
                "book_voice": book_voice, "book_speed": book_speed}

    def report(self, draft_id: str) -> dict:
        try:
            return json.loads((self.dir(draft_id) / "report.json").read_text(encoding="utf-8"))
        except OSError:
            raise Conflict("This book is not cleaned yet") from None

    def set_report(self, draft_id: str, report: dict) -> None:
        _write_json(self.root / draft_id / "report.json", report)
        self.update(draft_id, chapters=len(report["chapters"]), checks=len(report["checks"]))

    def std_path(self, draft_id: str) -> tuple[Path, str]:
        """The cleaned book and the name to download it as."""
        path = self.dir(draft_id) / STD
        if not path.exists():
            raise Conflict("This book is not cleaned yet")
        stem = Path(self.get(draft_id)["file"]).stem.removesuffix(".std")
        return path, f"{stem}.std.epub"

    def chapter(self, draft_id: str, n: int) -> dict:
        book = _std_book(self, draft_id)
        if not 0 <= n < len(book.chapters):
            raise NotFound("No such chapter")
        ch = book.chapters[n]
        return {"index": n, "title": ch.title, "paragraphs": [p for p in ch.text.split("\n") if p.strip()]}

    def replace_std(self, draft_id: str, upload: BinaryIO) -> int:
        """Replace the cleaned book with a version edited in Sigil. Rewritten with the draft's source hash, so the
        markers survive an editor that drops them and the book keeps its id (and its sentence cache)."""
        draft = self.get(draft_id)
        if draft["status"] not in ("review", "done", "error") or not draft["chapters"]:
            raise Conflict(f"Cannot replace the book while it is {draft['status']}")
        d = self.dir(draft_id)
        tmp = d / "edited.epub"
        with tmp.open("wb") as out:
            shutil.copyfileobj(upload, out)
        try:
            book = load_book(tmp)
        except Exception as e:  # noqa: BLE001 - any unreadable upload is the user's to fix
            raise Invalid(f"Could not read that EPUB: {e}") from None
        finally:
            tmp.unlink(missing_ok=True)
        write_std_epub(book, d / STD, draft["source_sha1"])
        report = self.report(draft_id)
        report["chapters"] = [[c.title, len(c.text)] for c in book.chapters]
        report["notes"].append(f"edited .std.epub uploaded ({time.strftime('%Y-%m-%d %H:%M')}): the chapters above "
                               "are the edited ones; the removed list is from the first cleaning")
        self.set_report(draft_id, report)
        self.update(draft_id, status="review", error=None, message="Edited version ready for review",
                    last_chapters=None)
        return len(book.chapters)

    def approve(self, draft_id: str, voice: str | None = None, speed: float | None = None,
                chapters: list[int] | None = None) -> dict:
        """Queue the cleaned book for conversion; voice and speed default to the ones chosen at upload.
        chapters: 1-based numbers to convert into the book's library entry (D-035); None converts them all."""
        draft = self.get(draft_id)
        voice, speed = voice or draft["voice"], speed or draft["speed"]
        check_options(voice, speed)
        if draft["status"] not in ("review", "done"):
            raise Conflict(f"Cannot convert a draft that is {draft['status']}")
        book = _std_book(self, draft_id)
        try:
            select_chapters(chapters, len(book.chapters))
        except ValueError as e:
            raise Invalid(str(e)) from None
        book_id = make_book_id(book, self.root / draft_id / STD)  # known now, so the library can say "converting"
        job = jobs.submit(self.root / draft_id / STD, draft["file"], voice, speed, draft_id=draft_id,
                          chapters=chapters, book_id=book_id)
        self.update(draft_id, status="queued", voice=voice, speed=speed, job_id=job["id"], error=None,
                    message="Waiting to convert", book_id=book_id, last_chapters=chapters)
        return job

    def delete(self, draft_id: str) -> None:
        d = self.dir(draft_id)
        if self.drafts[draft_id]["status"] in ("cleaning", "queued", "converting"):
            raise Conflict("Wait until cleaning or converting has finished")
        with self.lock:
            del self.drafts[draft_id]
        shutil.rmtree(d, ignore_errors=True)

    def _worker(self) -> None:
        while True:
            draft_id = self.queue.get()
            draft = self.drafts.get(draft_id)
            if draft is None:
                continue
            d = self.root / draft_id

            def progress(done: int, total: int) -> None:
                self.update(draft_id, done=done, total=total, message=f"Reading scanned pages {done}/{total}")

            try:
                self.update(draft_id, message="Cleaning the book")
                _std, report = normalize(d / draft["source"], d / STD, progress=progress,
                                         ocr=draft.get("ocr", "auto"))
                self.set_report(draft_id, asdict(report))
                self.update(draft_id, status="review", message="Ready for review")
                if draft["auto"]:
                    self.approve(draft_id, draft["voice"], draft["speed"])
            except Exception as e:  # noqa: BLE001 - report any failure to the client
                traceback.print_exc()
                self.update(draft_id, status="error", error=str(e), message="Failed")


def _std_book(owner: Drafts, draft_id: str):
    """The draft's cleaned book, parsed once per version of the file."""
    path = owner.dir(draft_id) / STD
    if not path.exists():
        raise Conflict("This book is not cleaned yet")
    key = (str(path), path.stat().st_mtime_ns)
    cached = _std_cache.get("v")  # one (key, book) tuple: replaced in one step, safe across request threads
    if cached is None or cached[0] != key:
        cached = _std_cache["v"] = (key, load_book(path))
    return cached[1]


_std_cache: dict = {}


# ---------------------------------------------------------------- jobs (convert)

class Jobs:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.lock = threading.Lock()
        self.model_lock = threading.Lock()
        self.tts = None
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, path: Path, filename: str, voice: str, speed: float, draft_id: str | None = None,
               chapters: list[int] | None = None, book_id: str | None = None) -> dict:
        job = {
            "id": uuid.uuid4().hex[:12], "file": filename, "voice": voice, "speed": speed,
            "status": "queued", "done": 0, "total": 0, "message": "Waiting", "book_id": book_id,
            "error": None, "created": time.time(), "draft_id": draft_id, "_path": str(path),
            "_chapters": chapters,
        }
        with self.lock:
            self.jobs[job["id"]] = job
        self.queue.put(job["id"])
        return job

    @staticmethod
    def _public(job: dict) -> dict:
        return {k: v for k, v in job.items() if not k.startswith("_")}

    def public(self) -> list[dict]:
        with self.lock:
            return [self._public(j) for j in sorted(self.jobs.values(), key=lambda j: j["created"], reverse=True)]

    def busy_books(self) -> set[str]:
        """Library ids of books with a conversion queued or running."""
        with self.lock:
            return {j["book_id"] for j in self.jobs.values() if j["status"] in ("queued", "running") and j["book_id"]}

    def get(self, job_id: str) -> dict:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise NotFound("No such job")
            return self._public(job)

    def model(self):
        """The one TTS model, loaded on first use and kept (it speaks both voice languages, D-031)."""
        with self.model_lock:  # not self.lock: loading takes ~10 s and must not block the job list
            if self.tts is None:
                from ..tts.kokoro import KokoroTTS

                self.tts = KokoroTTS()
            return self.tts

    def _get_tts(self, voice: str, speed: float):
        tts = self.model()
        tts.voice, tts.speed = voice, speed  # only the conversion worker sets these; samples pass their own
        return tts

    def _worker(self) -> None:
        while True:
            job_id = self.queue.get()
            job = self.jobs[job_id]
            job["status"] = "running"
            draft_id = job["draft_id"]
            if draft_id:
                drafts.update(draft_id, status="converting", message="Converting")

            def progress(done: int, total: int, msg: str) -> None:
                job.update(done=done, total=total, message=msg)

            try:
                # The job gets the cleaned .std.epub the user approved (D-029).
                job["message"] = "Loading TTS model"
                tts = self._get_tts(job["voice"], job["speed"])
                out = build_book(job["_path"], LIBRARY, job["voice"], job["speed"], progress, tts=tts,
                                 chapters=job["_chapters"], merge=True)
                job.update(status="done", book_id=out.name, message="Done")
                if draft_id:
                    drafts.update(draft_id, status="done", book_id=out.name, message="Converted")
            except Exception as e:  # noqa: BLE001 - report any failure to the client
                traceback.print_exc()
                job.update(status="error", error=str(e), message="Failed")
                if draft_id:
                    drafts.update(draft_id, status="review", error=str(e), message="Conversion failed")


# ---------------------------------------------------------------- library

def _book_dir(book_id: str) -> Path:
    if not _ID_RE.match(book_id):
        raise NotFound("No such book")
    d = LIBRARY / book_id
    if not (d / "book.json").exists():
        raise NotFound("No such book")
    return d


def _read_manifest(d: Path) -> dict:
    return json.loads((d / "book.json").read_text(encoding="utf-8"))


def clean_leftovers() -> list[Path]:
    """At server start: delete half-written chapter audio (*.tmp.m4a) and sentence-cache files (*.npy.tmp) that a
    Ctrl+C or crash left in library/ and cache/. Finished chapters and cached sentences stay, so an interrupted
    conversion still resumes. Assumes no other server uses the same data folder."""
    return remove_leftovers(LIBRARY, LIBRARY.parent / "cache")


def _library_manifest(book_id: str) -> dict | None:
    """The library book's manifest, or None if the book has not been converted yet."""
    try:
        return _read_manifest(LIBRARY / book_id)
    except (OSError, json.JSONDecodeError):
        return None


def list_books() -> list[dict]:
    books = []
    busy = jobs.busy_books()
    if LIBRARY.exists():
        for d in LIBRARY.iterdir():
            if not (d / "book.json").exists():
                continue
            try:
                m = _read_manifest(d)
            except (OSError, json.JSONDecodeError):
                continue
            size = sum(f.stat().st_size for f in d.iterdir()
                       if f.is_file() and not f.name.endswith(LEFTOVER_SUFFIXES))  # not a half-written chapter
            books.append({
                "id": m["id"], "title": m["title"], "author": m.get("author", ""), "cover": m.get("cover"),
                "voice": m.get("voice"), "complete": m.get("complete", False),
                "chapters": len(m["chapters"]), "chapters_total": m.get("chapters_total"),
                "converting": m["id"] in busy, "duration_ms": m.get("duration_ms", 0),
                "size_bytes": size, "created": m.get("created", 0),
            })
    books.sort(key=lambda b: b["created"], reverse=True)
    return books


def read_book(book_id: str) -> dict:
    """The book's manifest (book.json): chapters, their audio files and sentence timestamps."""
    m = _read_manifest(_book_dir(book_id))
    for pos, c in enumerate(m.get("chapters", [])):
        c["number"] = chapter_number(c, pos, m)  # books before D-035 have none
    return m


def book_file(book_id: str, name: str) -> Path:
    """One file of a book (chapter audio or cover); only plain names inside the book's folder."""
    d = _book_dir(book_id)
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise NotFound("No such file")
    f = d / name
    if not f.is_file():
        raise NotFound("No such file")
    return f


_UNSAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_MAX_NAME_BYTES = 200  # UTF-8 bytes, under the common 255-byte file name limit


def _safe_name_part(text: str) -> str:
    """Text usable in a file name on Windows, macOS and Android: no reserved characters, one-line, trimmed."""
    text = " ".join(_UNSAFE_NAME_RE.sub(" ", text or "").split())
    return text.rstrip(". ")


def download_name(book_id: str, name: str) -> str:
    """A readable file name for saving one of a book's files, e.g. "Book Title - Ch 01 - Chapter Title.m4a".

    Chapters keep their number in the cleaned book (D-035), padded to at least two digits, or to the width of the
    book's chapter count so a name doesn't change as more chapters are converted.
    Files that are not chapter audio (the cover) become "Book Title - cover.jpg". Falls back to the stored name.
    """
    f = book_file(book_id, name)
    m = _read_manifest(f.parent)
    book = _safe_name_part(m.get("title") or "")
    chapters = m.get("chapters") or []
    numbers = [chapter_number(ch, pos, m) for pos, ch in enumerate(chapters)]
    width = max(2, len(str(max([m.get("chapters_total") or 0, len(chapters), *numbers]))))
    stem = None
    for ch, number in zip(chapters, numbers):
        if ch.get("audio") == name:
            parts = [book, f"Ch {number:0{width}d}", _safe_name_part(ch.get("title") or "")]
            stem = " - ".join(p for p in parts if p)
            break
    else:
        if book:
            stem = f"{book} - {_safe_name_part(f.stem)}"
    if not stem:
        return name
    suffix = f.suffix
    budget = _MAX_NAME_BYTES - len(suffix.encode())
    if len(stem.encode()) > budget:  # trim whole characters; filesystems limit bytes (255 on ext4/f2fs)
        while len(stem.encode()) > budget:
            stem = stem[:-1]
        stem = stem.rstrip(". -")  # no dangling " - " separator after the cut
    return stem + suffix


def delete_book(book_id: str) -> None:
    shutil.rmtree(_book_dir(book_id))


# ---------------------------------------------------------------- voice samples

_sample_lock = threading.Lock()


def voice_sample(voice: str) -> Path:
    """About 5 s of the voice reading one fixed sentence; made once, then kept in cache/voice-samples/."""
    if voice not in VOICES:
        raise NotFound("No such voice")
    digest = hashlib.sha1(SAMPLE_TEXT.encode()).hexdigest()[:8]
    path = SAMPLES / f"{voice}-{digest}.m4a"
    with _sample_lock:  # two first clicks must not make the same file at once
        if not path.exists():
            SAMPLES.mkdir(parents=True, exist_ok=True)
            audio = jobs.model().synth(SAMPLE_TEXT, voice=voice, speed=1.0)
            encode_m4a(audio, path)
    return path


jobs = Jobs()
drafts = Drafts(DRAFTS)
