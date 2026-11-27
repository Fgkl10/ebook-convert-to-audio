"""LAN server: converts uploaded ebooks and serves the audiobook library.

Run:  .venv\\Scripts\\python -m desktop.server [--port 8000]
Then open http://localhost:8000 on the PC, or the printed LAN address on the phone.
"""
from __future__ import annotations

import argparse
import json
import queue
import re
import shutil
import socket
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .build import ROOT, build_book
from .normalize import normalize
from .tts import DEFAULT_VOICE, VOICES

LIBRARY = ROOT / "library"
UPLOADS = ROOT / "uploads"
STATIC = Path(__file__).resolve().parent / "static"
SERVICE_TYPE = "_ebookaudio._tcp.local."
_ID_RE = re.compile(r"^[a-z0-9\-]{1,80}$")

app = FastAPI(title="Ebook Audio Server")
app.state.port = 8000


# ---------------------------------------------------------------- jobs

class Jobs:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.lock = threading.Lock()
        self.tts = None
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, path: Path, filename: str, voice: str, speed: float) -> dict:
        job = {
            "id": uuid.uuid4().hex[:12], "file": filename, "voice": voice, "speed": speed,
            "status": "queued", "done": 0, "total": 0, "message": "Waiting", "book_id": None,
            "error": None, "created": time.time(), "_path": str(path),
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

            def progress(done: int, total: int, msg: str) -> None:
                job.update(done=done, total=total, message=msg)

            try:
                # The web flow cleans automatically (no manual review step), before the model loads,
                # so a refused language or an unreadable book fails fast (D-019).
                job["message"] = "Cleaning the book"
                std, _report = normalize(job["_path"])
                job["message"] = "Loading TTS model"
                tts = self._get_tts(job["voice"], job["speed"])
                out = build_book(std, LIBRARY, job["voice"], job["speed"], progress, tts=tts)
                job.update(status="done", book_id=out.name, message="Done")
            except Exception as e:  # noqa: BLE001 - report any failure to the UI
                traceback.print_exc()
                job.update(status="error", error=str(e), message="Failed")


jobs = Jobs()


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


@app.post("/api/convert")
async def convert(file: UploadFile = File(...), voice: str = Form(DEFAULT_VOICE), speed: float = Form(1.0)) -> dict:
    if voice not in VOICES:
        raise HTTPException(400, f"Unknown voice {voice}")
    if not 0.5 <= speed <= 2.0:
        raise HTTPException(400, "Speed must be between 0.5 and 2.0")
    name = Path(file.filename or "book").name
    ext = Path(name).suffix.lower()
    if ext not in (".epub", ".pdf", ".txt"):
        raise HTTPException(400, "Upload an .epub, .pdf or .txt file")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / f"{uuid.uuid4().hex[:8]}_{re.sub(r'[^A-Za-z0-9._-]+', '_', name)}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    job = jobs.submit(dest, name, voice, speed)
    return {"job_id": job["id"]}


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
