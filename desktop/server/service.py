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
from ..tts.build import (LEFTOVER_SUFFIXES, ROOT, Cancelled, build_book, chapter_number, chapter_text_sha1,
                         encode_m4a, make_book_id, remove_leftovers, select_chapters)
from ..core.language import detect_language
from ..tts import build
from ..tts.backend import BACKENDS, Backend, chosen, create, save_setting
from ..tts.backend import NAMES as BACKEND_NAMES
from ..tts.models import ZH_REPO, ZH_VOICES, ZhModel

CANCELLED_MESSAGE = "Cancelled: approve again to resume (finished chapters and sentences are kept)."
LIBRARY = ROOT / "library"
DRAFTS = ROOT / "drafts"
SAMPLES = ROOT / "cache" / "voice-samples"
SAMPLE_TEXTS = {"en": "Hello! This is how I sound when I read your books aloud. I hope you enjoy listening.",
                "zh": "你好！这就是我为你朗读书籍时的声音，希望你听得开心。"}
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
    "file": "", "source": "", "message": "", "done": 0, "total": 0, "auto": False, "voice": "",
    "speed": 1.0, "ocr": "auto", "error": None, "created": 0, "chapters": 0, "checks": 0, "job_id": None,
    "book_id": None, "source_sha1": "", "last_chapters": None,
}


CLI_TTS: str | None = None  # ebook-server --tts


def configure_tts(cli: str | None) -> None:
    """ebook-server --tts: checked at start, so a typo stops the server instead of the first conversion."""
    global CLI_TTS
    chosen(build.ROOT, cli)  # ValueError for an unknown name (also from EBOOK_AUDIO_TTS)
    CLI_TTS = cli


def tts() -> Backend:
    """The TTS backend in use (D-045)."""
    return jobs.backend()


def tts_setting() -> dict:
    current = tts()
    return {"backend": current.id, "fixed_by": jobs.fixed_by,
            "backends": [{"id": n, "name": BACKEND_NAMES.get(n, n)} for n in BACKENDS]}


def set_tts(name: str) -> dict:
    """The page's backend choice: saved in <data>/settings.json and used from now on. Refused when --tts or
    EBOOK_AUDIO_TTS chose it, and while a conversion is queued or running."""
    if name not in BACKENDS:
        raise Invalid(f"Unknown TTS backend {name}: choose one of {', '.join(BACKENDS)}")
    tts()  # fixed_by is known once the backend exists
    if jobs.fixed_by:
        raise Conflict(f"The TTS backend was set with {jobs.fixed_by} when the server started")
    if name != jobs.tts.id:
        jobs.switch_backend(name)
    save_setting(build.ROOT, "tts", name)
    return tts_setting()


def check_options(voice: str | None, speed: float) -> None:
    """voice None: the backend's default for the book's language, chosen when the language is known."""
    if voice is not None and voice not in tts().voice_ids():
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
        self._book_info: dict[str, tuple] = {}  # draft id -> library_state() cache
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

    def create(self, upload: BinaryIO, filename: str, auto: bool = False, voice: str | None = None,
               speed: float = 1.0, ocr: str = "auto") -> dict:
        """Upload a book to clean. auto=True converts right after cleaning, with no review stop.
        ocr (PDF only): auto, always or never (D-030). voice None: the English default (a Chinese book then gets
        the Chinese default at approval)."""
        voice = voice or tts().default_voice("en")
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

    def create_cleaned(self, upload: BinaryIO, filename: str, voice: str | None = None, speed: float = 1.0) -> dict:
        """A book already cleaned (CLI, or edited in Sigil): no cleaning step, straight to conversion (D-030)."""
        voice = voice or tts().default_voice("en")
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
            "language": detect_language(book) or "en",
            "chapters": [[c.title, len(c.text)] for c in book.chapters],
            "removed": [], "unconfirmed": [], "notes": [], "checks": []})
        self.approve(draft_id, voice, speed)
        return draft

    def public(self) -> list[dict]:
        with self.lock:
            drafts = [dict(d) for d in sorted(self.drafts.values(), key=lambda d: d["created"], reverse=True)]
        for d in drafts:  # for "converted 3 of 12" on the list
            d["converted"] = self.library_state(d["id"])[0]
        return drafts

    def detail(self, draft_id: str) -> dict:
        """The draft plus its cleaning report (None until cleaned)."""
        draft = self.get(draft_id)
        report = self.report(draft_id) if draft["status"] != "cleaning" and draft["chapters"] else None
        converted, book_voice, book_speed = self.library_state(draft_id) if report is not None else ([], None, None)
        return {**draft, "report": report, "converted": converted, "book_voice": book_voice, "book_speed": book_speed}

    def library_state(self, draft_id: str) -> tuple[list[int], str | None, float | None]:
        """(chapters of this cleaned book already in its library book, that book's voice, its speed). A chapter edited
        since it was converted doesn't count; books before D-035 have no hash, so theirs do.
        Cached per draft by the cleaned file's and book.json's mtimes: the draft list asks every 2 s."""
        draft = self.drafts.get(draft_id)
        std = self.root / draft_id / STD
        if not draft or not draft["chapters"] or draft["status"] == "cleaning" or not std.exists():
            return [], None, None
        std_key = std.stat().st_mtime_ns
        cached = self._book_info.get(draft_id)
        if cached is None or cached[0] != std_key:  # parse the cleaned book once per version
            book = load_book(std)
            cached = (std_key, make_book_id(book, std), [chapter_text_sha1(c.text) for c in book.chapters], None)
        _, book_id, hashes, last = cached
        manifest = LIBRARY / book_id / "book.json"
        man_key = manifest.stat().st_mtime_ns if manifest.exists() else None
        if last is None or last[0] != man_key:
            m = _library_manifest(book_id) if man_key is not None else None
            converted, voice, speed = [], None, None
            if m is not None:
                voice, speed = m.get("voice"), m.get("speed")
                for pos, c in enumerate(m.get("chapters", [])):
                    n = chapter_number(c, pos, m)
                    if 1 <= n <= len(hashes) and c.get("text_sha1") in (None, hashes[n - 1]):
                        converted.append(n)
            last = (man_key, (sorted(set(converted)), voice, speed))
        self._book_info[draft_id] = (std_key, book_id, hashes, last)
        return last[1]

    def cancel(self, draft_id: str) -> dict:
        """Stop this draft's conversion (queued or running); the draft goes back to review."""
        draft = self.get(draft_id)
        if draft["status"] not in ("queued", "converting") or not draft["job_id"]:
            raise Conflict(f"Nothing to cancel: the draft is {draft['status']}")
        return jobs.cancel(draft["job_id"])

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
        if not voice and draft["voice"] in tts().voice_ids():
            voice = draft["voice"]  # the upload's voice, unless that backend or model is no longer in use
        speed = speed or draft["speed"]
        check_options(voice, speed)
        if draft["status"] not in ("review", "done"):
            raise Conflict(f"Cannot convert a draft that is {draft['status']}")
        book = _std_book(self, draft_id)
        try:
            select_chapters(chapters, len(book.chapters))
        except ValueError as e:
            raise Invalid(str(e)) from None
        book_id = make_book_id(book, self.root / draft_id / STD)  # known now, so the library can say "converting"
        # A voice in another language than the book's (picked at upload, before the language was known) gives way
        # to that language's default voice (D-043).
        lang = (self.report(draft_id) or {}).get("language") or detect_language(book) or "en"
        backend = tts()
        if lang not in backend.languages():
            raise Invalid(f"{backend.name} can't read this book's language")
        picked = backend.voice_for(voice, lang) if voice else backend.default_voice(lang)
        message = "Waiting to convert" if picked == voice or not voice else \
            f"Waiting to convert, with {picked}: {voice} does not speak this book's language"
        job = jobs.submit(self.root / draft_id / STD, draft["file"], picked, speed, draft_id=draft_id,
                          chapters=chapters, book_id=book_id)
        self.update(draft_id, status="queued", voice=picked, speed=speed, job_id=job["id"], error=None,
                    message=message, book_id=book_id, last_chapters=chapters)
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
        self.tts: Backend | None = None  # backend(): made on first use
        self.fixed_by: str | None = None  # "--tts" / "EBOOK_AUDIO_TTS" when one of them chose the backend
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, path: Path, filename: str, voice: str, speed: float, draft_id: str | None = None,
               chapters: list[int] | None = None, book_id: str | None = None) -> dict:
        job = {
            "id": uuid.uuid4().hex[:12], "file": filename, "voice": voice, "speed": speed,
            "status": "queued", "done": 0, "total": 0, "message": "Waiting", "book_id": book_id,
            "error": None, "created": time.time(), "draft_id": draft_id, "_path": str(path),
            "_chapters": chapters, "_cancel": threading.Event(),
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

    def backend(self) -> Backend:
        """The one TTS backend (D-045), shared by every job and voice sample. Made on first use from the setting
        (backend.chosen); its model loads with the first sentence and stays loaded (D-031)."""
        with self.model_lock:
            if self.tts is None:
                name, self.fixed_by = chosen(build.ROOT, CLI_TTS)
                self.tts = create(name)
            return self.tts

    def switch_backend(self, name: str) -> None:
        """Use another backend from now on; the old one's model is freed (D-045)."""
        with self.lock:
            if any(j["status"] in ("queued", "running") for j in self.jobs.values()):
                raise Conflict("A conversion is queued or running: wait for it or cancel it first")
        with self.model_lock:
            old, self.tts = self.tts, create(name)
        if old is not None and old.id != name:
            old.unload()

    def cancel(self, job_id: str) -> dict:
        """Stop a conversion. Queued: it never starts. Running: it stops at the next sentence (build_book's cancel
        event). The server and the loaded model keep going; the draft goes back to review, and approving it again
        resumes from the finished chapters and cached sentences (D-038)."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise NotFound("No such job")
            if job["status"] == "queued":
                job.update(status="cancelled", message="Cancelled before it started")
            elif job["status"] == "running":
                job["_cancel"].set()
                job["message"] = "Cancelling…"
            else:
                raise Conflict(f"This conversion has already ended ({job['status']})")
            queued = job["status"] == "cancelled"
            public = self._public(job)
        if queued and job["draft_id"]:
            drafts.update(job["draft_id"], status="review", message=CANCELLED_MESSAGE)
        return public

    def _worker(self) -> None:
        while True:
            job_id = self.queue.get()
            job = self.jobs[job_id]
            with self.lock:
                if job["status"] == "cancelled":  # cancelled while it waited in the queue
                    continue
                job["status"] = "running"
            draft_id = job["draft_id"]
            if draft_id:
                drafts.update(draft_id, status="converting", message="Converting")

            def progress(done: int, total: int, msg: str) -> None:
                job.update(done=done, total=total, message=msg)

            try:
                # The job gets the cleaned .std.epub the user approved (D-029).
                job["message"] = "Loading TTS model"
                out = build_book(job["_path"], LIBRARY, job["voice"], job["speed"], progress, self.backend(),
                                 chapters=job["_chapters"], merge=True, cancel=job["_cancel"])
                job.update(status="done", book_id=out.name, message="Done")
                if draft_id:
                    drafts.update(draft_id, status="done", book_id=out.name, message="Converted")
            except Cancelled:
                job.update(status="cancelled", message="Cancelled")
                if draft_id:
                    drafts.update(draft_id, status="review", message=CANCELLED_MESSAGE)
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
    d = _book_dir(book_id)
    m = _read_manifest(d)
    for pos, c in enumerate(m.get("chapters", [])):
        c["number"] = chapter_number(c, pos, m)  # books before D-035 have none
        if "size_bytes" not in c or "updated_ms" not in c:  # books before D-038: from the file itself
            try:
                st = (d / c["audio"]).stat()
                c.setdefault("size_bytes", st.st_size)
                c.setdefault("updated_ms", st.st_mtime_ns // 1_000_000)
            except OSError:
                c.setdefault("size_bytes", 0)
                c.setdefault("updated_ms", 0)
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
    d = _book_dir(book_id)
    if book_id in jobs.busy_books():  # the worker is writing into the folder (D-038)
        raise Conflict("This book is being converted: cancel the conversion first")
    shutil.rmtree(d)


# ---------------------------------------------------------------- voice samples

_sample_lock = threading.Lock()


def voice_sample(voice: str) -> Path:
    """About 5 s of the voice reading one fixed sentence; made once, then kept in cache/voice-samples/."""
    backend = tts()
    if voice not in backend.voice_ids():
        raise NotFound("No such voice")
    text = SAMPLE_TEXTS[backend.voice_language(voice) or "en"]
    digest = hashlib.sha1(text.encode()).hexdigest()[:8]
    path = SAMPLES / (f"{voice}-{digest}.m4a" if backend.id == "kokoro" else f"{backend.id}-{voice}-{digest}.m4a")
    with _sample_lock:  # two first clicks must not make the same file at once
        if not path.exists():
            SAMPLES.mkdir(parents=True, exist_ok=True)
            audio = backend.synth(text, voice, 1.0)
            encode_m4a(audio, path, backend.sample_rate)
    return path


def saved_samples() -> dict:
    """How many voice samples are kept, and their size."""
    files = list(SAMPLES.glob("*.m4a")) if SAMPLES.is_dir() else []
    return {"count": len(files), "bytes": sum(f.stat().st_size for f in files)}


def delete_samples() -> dict:
    """Delete the kept samples; the next ▶ makes them again. Waits for a sample being made."""
    with _sample_lock:
        for f in SAMPLES.glob("*.m4a") if SAMPLES.is_dir() else []:
            f.unlink(missing_ok=True)
    return saved_samples()


# ---------------------------------------------------------------- optional Kokoro v1.1-zh (D-044)

zh_model = ZhModel()


def install_zh_model() -> None:
    zh_model.install()


def remove_zh_model() -> None:
    """Refused while a queued or running conversion reads with one of its voices; the loaded copy is dropped."""
    with jobs.lock:
        if any(j["status"] in ("queued", "running") and j["voice"] in ZH_VOICES for j in jobs.jobs.values()):
            raise Conflict("A conversion is using a Kokoro v1.1-zh voice: wait for it or cancel it first")
    try:
        zh_model.remove()
    except RuntimeError as e:
        raise Conflict(str(e)) from None
    if jobs.tts is not None and jobs.tts.id == "kokoro":
        jobs.tts.unload(ZH_REPO)


jobs = Jobs()
drafts = Drafts(DRAFTS)
