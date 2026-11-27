"""LAN server: cleans uploaded ebooks for review, converts approved ones, and serves the audiobook library.

Run:  .venv\\Scripts\\python -m desktop.server [--port 8000]
Then open http://localhost:8000 on the PC, or the printed LAN address on the phone.

Web flow (D-029): upload -> clean (drafts/<id>/, its own worker) -> review -> approve -> convert (Jobs worker).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import socket
import threading
import time
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .build import ROOT, build_book
from .normalize import OCR_MODES, normalize, write_std_epub
from .parse import load_book
from .tts import DEFAULT_VOICE, VOICES

LIBRARY = ROOT / "library"
DRAFTS = ROOT / "drafts"
STATIC = Path(__file__).resolve().parent / "static"
SERVICE_TYPE = "_ebookaudio._tcp.local."
_ID_RE = re.compile(r"^[a-z0-9\-]{1,80}$")
STD = "book.std.epub"

app = FastAPI(title="Ebook Audio Server")
app.state.port = 8000


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _check_options(voice: str, speed: float) -> None:
    if voice not in VOICES:
        raise HTTPException(400, f"Unknown voice {voice}")
    if not 0.5 <= speed <= 2.0:
        raise HTTPException(400, "Speed must be between 0.5 and 2.0")


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
            raise HTTPException(404, "No such draft")
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

    def create(self, upload, filename: str, auto: bool, voice: str, speed: float, ocr: str = "auto") -> dict:
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

    def create_cleaned(self, upload, filename: str, voice: str, speed: float) -> dict:
        """A book already cleaned (CLI, or edited in Sigil): no cleaning step, straight to conversion (D-030)."""
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
            raise HTTPException(400, "Not a cleaned book (.std.epub): clean it on the Clean page first.")
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

    def report(self, draft_id: str) -> dict:
        try:
            return json.loads((self.dir(draft_id) / "report.json").read_text(encoding="utf-8"))
        except OSError:
            raise HTTPException(409, "This book is not cleaned yet") from None

    def set_report(self, draft_id: str, report: dict) -> None:
        _write_json(self.root / draft_id / "report.json", report)
        self.update(draft_id, chapters=len(report["chapters"]), checks=len(report["checks"]))

    def approve(self, draft_id: str, voice: str, speed: float) -> dict:
        draft = self.get(draft_id)
        if draft["status"] not in ("review", "done"):
            raise HTTPException(409, f"Cannot convert a draft that is {draft['status']}")
        job = jobs.submit(self.root / draft_id / STD, draft["file"], voice, speed, draft_id=draft_id)
        self.update(draft_id, status="queued", voice=voice, speed=speed, job_id=job["id"], error=None,
                    message="Waiting to convert")
        return job

    def delete(self, draft_id: str) -> None:
        d = self.dir(draft_id)
        if self.drafts[draft_id]["status"] in ("cleaning", "queued", "converting"):
            raise HTTPException(409, "Wait until cleaning or converting has finished")
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
            except Exception as e:  # noqa: BLE001 - report any failure to the UI
                traceback.print_exc()
                self.update(draft_id, status="error", error=str(e), message="Failed")


# ---------------------------------------------------------------- jobs (convert)

class Jobs:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.lock = threading.Lock()
        self.tts = None
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, path: Path, filename: str, voice: str, speed: float, draft_id: str | None = None) -> dict:
        job = {
            "id": uuid.uuid4().hex[:12], "file": filename, "voice": voice, "speed": speed,
            "status": "queued", "done": 0, "total": 0, "message": "Waiting", "book_id": None,
            "error": None, "created": time.time(), "draft_id": draft_id, "_path": str(path),
        }
        with self.lock:
            self.jobs[job["id"]] = job
        self.queue.put(job["id"])
        return job

    def public(self) -> list[dict]:
        with self.lock:
            return [{k: v for k, v in j.items() if not k.startswith("_")} for j in
                    sorted(self.jobs.values(), key=lambda j: j["created"], reverse=True)]

    def _get_tts(self, voice: str, speed: float):
        from .tts import KokoroTTS

        # Reuse the loaded model when the language (a/b) matches; voices are swapped per call.
        if self.tts is None or self.tts.voice[0] != voice[0]:
            self.tts = None
            self.tts = KokoroTTS(voice=voice, speed=speed)
        self.tts.voice, self.tts.speed = voice, speed
        return self.tts

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
                out = build_book(job["_path"], LIBRARY, job["voice"], job["speed"], progress, tts=tts)
                job.update(status="done", book_id=out.name, message="Done")
                if draft_id:
                    drafts.update(draft_id, status="done", book_id=out.name, message="Converted")
            except Exception as e:  # noqa: BLE001 - report any failure to the UI
                traceback.print_exc()
                job.update(status="error", error=str(e), message="Failed")
                if draft_id:
                    drafts.update(draft_id, status="review", error=str(e), message="Conversion failed")


jobs = Jobs()
drafts = Drafts(DRAFTS)


def _std_book(draft_id: str):
    """The draft's cleaned book, parsed once per version of the file."""
    path = drafts.dir(draft_id) / STD
    if not path.exists():
        raise HTTPException(409, "This book is not cleaned yet")
    key = (str(path), path.stat().st_mtime_ns)
    cached = _std_cache.get("v")  # one (key, book) tuple: replaced in one step, safe across request threads
    if cached is None or cached[0] != key:
        cached = _std_cache["v"] = (key, load_book(path))
    return cached[1]


_std_cache: dict = {}


# ---------------------------------------------------------------- helpers

def _book_dir(book_id: str) -> Path:
    if not _ID_RE.match(book_id):
        raise HTTPException(404, "No such book")
    d = LIBRARY / book_id
    if not (d / "book.json").exists():
        raise HTTPException(404, "No such book")
    return d


def _read_manifest(d: Path) -> dict:
    return json.loads((d / "book.json").read_text(encoding="utf-8"))


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ---------------------------------------------------------------- API

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/api/info")
def info() -> dict:
    url = f"http://{lan_ip()}:{app.state.port}"
    qr_svg = None
    try:
        import qrcode
        import qrcode.image.svg

        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
        qr_svg = img.to_string(encoding="unicode")
    except Exception:  # noqa: BLE001 - QR is optional
        pass
    return {"name": socket.gethostname(), "url": url, "qr_svg": qr_svg, "voices": VOICES, "default_voice": DEFAULT_VOICE}


@app.get("/api/books")
def list_books() -> list[dict]:
    books = []
    if LIBRARY.exists():
        for d in LIBRARY.iterdir():
            if not (d / "book.json").exists():
                continue
            try:
                m = _read_manifest(d)
            except (OSError, json.JSONDecodeError):
                continue
            size = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
            books.append({
                "id": m["id"], "title": m["title"], "author": m.get("author", ""), "cover": m.get("cover"),
                "voice": m.get("voice"), "complete": m.get("complete", False),
                "chapters": len(m["chapters"]), "duration_ms": m.get("duration_ms", 0),
                "size_bytes": size, "created": m.get("created", 0),
            })
    books.sort(key=lambda b: b["created"], reverse=True)
    return books


@app.get("/api/books/{book_id}")
def get_book(book_id: str) -> JSONResponse:
    return JSONResponse(_read_manifest(_book_dir(book_id)))


@app.get("/api/books/{book_id}/files/{name}")
def get_file(book_id: str, name: str) -> FileResponse:
    d = _book_dir(book_id)
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(404)
    f = d / name
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)  # Starlette handles HTTP Range requests (seeking/resume)


@app.delete("/api/books/{book_id}")
def delete_book(book_id: str) -> dict:
    shutil.rmtree(_book_dir(book_id))
    return {"ok": True}


@app.post("/api/clean")
def clean(file: UploadFile = File(...), voice: str = Form(DEFAULT_VOICE), speed: float = Form(1.0),
          auto: bool = Form(False), ocr: str = Form("auto")) -> dict:
    """Upload a book to clean. auto=true converts right after cleaning, with no review stop.
    ocr (PDF only): auto, always or never (D-030)."""
    _check_options(voice, speed)
    if ocr not in OCR_MODES:
        raise HTTPException(400, f"OCR must be one of {', '.join(OCR_MODES)}")
    name = _upload_name(file)
    if Path(name).suffix.lower() not in (".epub", ".pdf", ".txt"):
        raise HTTPException(400, "Upload an .epub, .pdf or .txt file")
    draft = drafts.create(file.file, name, auto, voice, speed, ocr)
    return {"draft_id": draft["id"]}


def _upload_name(file: UploadFile) -> str:
    return Path((file.filename or "book").replace("\\", "/")).name


@app.post("/api/convert")
def convert(file: UploadFile = File(...), voice: str = Form(DEFAULT_VOICE), speed: float = Form(1.0)) -> dict:
    """One step: clean, then convert with no review (the same as /api/clean with auto=true)."""
    return clean(file, voice, speed, True, "auto")


@app.post("/api/convert-std")
def convert_std(file: UploadFile = File(...), voice: str = Form(DEFAULT_VOICE), speed: float = Form(1.0)) -> dict:
    """Convert a book that is already cleaned (a .std.epub from the CLI or Sigil), with no cleaning step."""
    _check_options(voice, speed)
    draft = drafts.create_cleaned(file.file, _upload_name(file), voice, speed)
    return {"draft_id": draft["id"], "job_id": draft["job_id"]}


@app.get("/api/drafts")
def list_drafts() -> list[dict]:
    return drafts.public()


@app.get("/api/drafts/{draft_id}")
def get_draft(draft_id: str) -> dict:
    draft = drafts.get(draft_id)
    report = drafts.report(draft_id) if draft["status"] != "cleaning" and draft["chapters"] else None
    return {**draft, "report": report}


@app.get("/api/drafts/{draft_id}/chapters/{n}")
def get_draft_chapter(draft_id: str, n: int) -> dict:
    book = _std_book(draft_id)
    if not 0 <= n < len(book.chapters):
        raise HTTPException(404, "No such chapter")
    ch = book.chapters[n]
    return {"index": n, "title": ch.title, "paragraphs": [p for p in ch.text.split("\n") if p.strip()]}


@app.get("/api/drafts/{draft_id}/std.epub")
def download_std(draft_id: str) -> FileResponse:
    path = drafts.dir(draft_id) / STD
    if not path.exists():
        raise HTTPException(409, "This book is not cleaned yet")
    stem = Path(drafts.get(draft_id)["file"]).stem.removesuffix(".std")
    return FileResponse(path, media_type="application/epub+zip", filename=f"{stem}.std.epub")


@app.post("/api/drafts/{draft_id}/std.epub")
def upload_std(draft_id: str, file: UploadFile = File(...)) -> dict:
    """Replace the cleaned book with a version edited in Sigil. Rewritten with the draft's source hash, so the
    markers survive an editor that drops them and the book keeps its id (and its sentence cache)."""
    draft = drafts.get(draft_id)
    if draft["status"] not in ("review", "done", "error") or not draft["chapters"]:
        raise HTTPException(409, f"Cannot replace the book while it is {draft['status']}")
    d = drafts.dir(draft_id)
    tmp = d / "edited.epub"
    with tmp.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        book = load_book(tmp)
    except Exception as e:  # noqa: BLE001 - any unreadable upload is the user's to fix
        raise HTTPException(400, f"Could not read that EPUB: {e}") from None
    finally:
        tmp.unlink(missing_ok=True)
    write_std_epub(book, d / STD, draft["source_sha1"])
    report = drafts.report(draft_id)
    report["chapters"] = [[c.title, len(c.text)] for c in book.chapters]
    report["notes"].append(f"edited .std.epub uploaded ({time.strftime('%Y-%m-%d %H:%M')}): the chapters above "
                           "are the edited ones; the removed list is from the first cleaning")
    drafts.set_report(draft_id, report)
    drafts.update(draft_id, status="review", error=None, message="Edited version ready for review")
    return {"chapters": len(book.chapters)}


@app.post("/api/drafts/{draft_id}/approve")
def approve(draft_id: str, voice: str = Form(DEFAULT_VOICE), speed: float = Form(1.0)) -> dict:
    _check_options(voice, speed)
    return {"job_id": drafts.approve(draft_id, voice, speed)["id"]}


@app.delete("/api/drafts/{draft_id}")
def delete_draft(draft_id: str) -> dict:
    drafts.delete(draft_id)
    return {"ok": True}


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return jobs.public()


# ---------------------------------------------------------------- mDNS

def advertise(port: int):
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        return None
    ip = lan_ip()
    host = socket.gethostname()
    zc = Zeroconf()
    svc = ServiceInfo(
        SERVICE_TYPE, f"{host}.{SERVICE_TYPE}", addresses=[socket.inet_aton(ip)], port=port,
        properties={"path": "/api", "name": host}, server=f"{host}.local.",
    )
    try:
        zc.register_service(svc)
    except Exception as e:  # noqa: BLE001 - discovery is optional
        print(f"mDNS advertise failed ({e}); enter the address manually on the phone.")
        zc.close()
        return None
    return zc, svc


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    app.state.port = args.port
    LIBRARY.mkdir(exist_ok=True)

    adv = advertise(args.port)
    print(f"\n  Ebook Audio Server\n  On this PC:   http://localhost:{args.port}\n  On the phone: http://{lan_ip()}:{args.port}\n")
    try:
        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
    finally:
        if adv:
            zc, svc = adv
            zc.unregister_service(svc)
            zc.close()


if __name__ == "__main__":
    main()
