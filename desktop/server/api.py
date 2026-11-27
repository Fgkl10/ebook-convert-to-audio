"""The JSON API, version 1 (D-032): every book operation, for the web page and the Android app alike.

Routes are thin: they read the request, call desktop/server/service.py and return the models below, which are the written
contract (served as /openapi.json and /docs). Errors are always JSON {"detail": "..."} with the status code.
Uploads are multipart; every other body is JSON. A breaking change goes into a new /api/v2, never into v1.
"""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import service
from ..core.normalize import OCR_MODES
from ..tts.kokoro import DEFAULT_VOICE, VOICES

API_VERSION = 1
PREFIX = f"/api/v{API_VERSION}"

router = APIRouter(prefix=PREFIX)

DraftStatus = Literal["cleaning", "review", "queued", "converting", "done", "error"]
JobStatus = Literal["queued", "running", "done", "error"]


# ---------------------------------------------------------------- models

class Info(BaseModel):
    api_version: int
    name: str = Field(description="The PC's host name")
    url: str = Field(description="The LAN address the phone connects to")
    qr_svg: Optional[str] = Field(description="QR code of url as SVG, or null")
    voices: list[str]
    default_voice: str
    ocr_modes: list[str]


class Report(BaseModel):
    source: str
    method: str
    chapters: list[tuple[str, int]] = Field(description="(title, characters) per chapter")
    removed: list[tuple[str, str]] = Field(description="(reason, first characters) per removed part")
    unconfirmed: list[str] = Field(description="Contents entries with no matching heading")
    notes: list[str]
    checks: list[str] = Field(description="Things to look at by hand before converting")


class Draft(BaseModel):
    # Defaults cover draft.json files written by older versions (e.g. no "ocr" before D-030).
    id: str
    file: str = Field("", description="The uploaded file's name")
    source: str = ""
    status: DraftStatus
    message: str = ""
    done: int = Field(0, description="Progress while cleaning (scanned pages read)")
    total: int = 0
    auto: bool = Field(False, description="Converts right after cleaning, with no review stop")
    voice: str = DEFAULT_VOICE
    speed: float = 1.0
    ocr: str = "auto"
    error: Optional[str] = None
    created: float = 0
    chapters: int = 0
    checks: int = 0
    job_id: Optional[str] = None
    book_id: Optional[str] = Field(None, description="The library book, set when a conversion is approved")
    source_sha1: str = ""
    last_chapters: Optional[list[int]] = Field(None, description="The chapters of the last approval (null = all)")


class DraftDetail(Draft):
    report: Optional[Report] = Field(description="The cleaning report; null until cleaned")
    converted: list[int] = Field([], description="1-based chapters already in the library book with this text")
    book_voice: Optional[str] = Field(None, description="The library book's voice (latest conversion), or null")
    book_speed: Optional[float] = None


class DraftCreated(BaseModel):
    draft_id: str


class CleanedCreated(BaseModel):
    draft_id: str
    job_id: str


class Chapter(BaseModel):
    index: int
    title: str
    paragraphs: list[str]


class Replaced(BaseModel):
    chapters: int


class ApproveRequest(BaseModel):
    voice: Optional[str] = Field(None, description="Defaults to the voice chosen at upload")
    speed: Optional[float] = Field(None, description="0.5 to 2.0; defaults to the speed chosen at upload")
    chapters: Optional[list[int]] = Field(
        None, description="1-based chapter numbers to convert into the book's library entry, replacing those chapters "
                          "and keeping the others; null converts every chapter")


class JobCreated(BaseModel):
    job_id: str


class Job(BaseModel):
    id: str
    file: str
    voice: str
    speed: float
    status: JobStatus
    done: int = Field(description="Sentences made so far")
    total: int = Field(description="Sentences in the book (0 until known)")
    message: str
    book_id: Optional[str]
    error: Optional[str]
    created: float
    draft_id: Optional[str]


class BookSummary(BaseModel):
    id: str
    title: str
    author: Optional[str] = ""
    cover: Optional[str] = Field(None, description="File name of the cover under /files/, or null")
    voice: Optional[str]
    complete: bool = Field(description="True when every chapter of the book is converted (D-035)")
    chapters: int = Field(description="Chapters converted so far")
    chapters_total: Optional[int] = Field(None, description="Chapters in the book (null for books before D-035)")
    converting: bool = Field(False, description="A conversion for this book is queued or running")
    duration_ms: int
    size_bytes: int
    created: float


class Sentence(BaseModel):
    model_config = ConfigDict(extra="allow")
    i: int
    p: int = Field(description="Paragraph number in the chapter")
    text: str
    start_ms: int
    end_ms: Optional[int] = None


class BookChapter(BaseModel):
    model_config = ConfigDict(extra="allow")
    index: int = Field(description="Position in this list")
    number: int = Field(description="1-based chapter number in the cleaned book (D-035); filled in for older books")
    title: str
    audio: str = Field(description="File name of the chapter's .m4a under /files/")
    duration_ms: int
    sentences: list[Sentence]


class Book(BaseModel):
    """The manifest (book.json). Download a book by fetching each chapter's audio file (HTTP Range works; add
    ?download=1 for a readable file name)."""
    model_config = ConfigDict(extra="allow")
    id: str
    title: str
    author: Optional[str] = ""
    cover: Optional[str] = None
    voice: Optional[str] = None
    speed: Optional[float] = None
    complete: bool = False
    created: float = 0
    duration_ms: int = 0
    chapters: list[BookChapter]


class Ok(BaseModel):
    ok: bool = True


class Error(BaseModel):
    detail: str


ERRORS = {400: {"model": Error}, 404: {"model": Error}, 409: {"model": Error}}


async def service_error(_request: Request, exc: service.ServiceError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


def _upload_name(file: UploadFile) -> str:
    return Path((file.filename or "book").replace("\\", "/")).name


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ---------------------------------------------------------------- server

@router.get("/info", response_model=Info, tags=["server"])
def info(request: Request) -> dict:
    url = f"http://{lan_ip()}:{request.app.state.port}"
    qr_svg = None
    try:
        import qrcode
        import qrcode.image.svg

        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
        qr_svg = img.to_string(encoding="unicode")
    except Exception:  # noqa: BLE001 - QR is optional
        pass
    return {"api_version": API_VERSION, "name": socket.gethostname(), "url": url, "qr_svg": qr_svg,
            "voices": VOICES, "default_voice": DEFAULT_VOICE, "ocr_modes": list(OCR_MODES)}


@router.get("/voices/{voice}/sample", response_class=FileResponse, responses={404: {"model": Error}},
            tags=["server"])
def voice_sample(voice: str) -> FileResponse:
    """About 5 s of the voice reading one fixed sentence (audio/mp4). The first one loads the model (~10 s)."""
    return FileResponse(service.voice_sample(voice), media_type="audio/mp4")


# ---------------------------------------------------------------- drafts: clean and review

@router.post("/drafts", response_model=DraftCreated, responses=ERRORS, tags=["drafts"])
def create_draft(file: UploadFile = File(...), voice: str = Form(DEFAULT_VOICE), speed: float = Form(1.0),
                 auto: bool = Form(False), ocr: str = Form("auto")) -> dict:
    """Upload an .epub, .pdf or .txt to clean. auto=true converts right after cleaning, with no review stop.
    ocr (PDF only): auto, always or never."""
    draft = service.drafts.create(file.file, _upload_name(file), auto, voice, speed, ocr)
    return {"draft_id": draft["id"]}


@router.post("/drafts/cleaned", response_model=CleanedCreated, responses=ERRORS, tags=["drafts"])
def create_cleaned(file: UploadFile = File(...), voice: str = Form(DEFAULT_VOICE),
                   speed: float = Form(1.0)) -> dict:
    """Upload a book that is already cleaned (a .std.epub from the CLI or Sigil); it converts right away."""
    draft = service.drafts.create_cleaned(file.file, _upload_name(file), voice, speed)
    return {"draft_id": draft["id"], "job_id": draft["job_id"]}


@router.get("/drafts", response_model=list[Draft], tags=["drafts"])
def list_drafts() -> list[dict]:
    return service.drafts.public()


@router.get("/drafts/{draft_id}", response_model=DraftDetail, responses=ERRORS, tags=["drafts"])
def get_draft(draft_id: str) -> dict:
    return service.drafts.detail(draft_id)


@router.get("/drafts/{draft_id}/chapters/{n}", response_model=Chapter, responses=ERRORS, tags=["drafts"])
def get_draft_chapter(draft_id: str, n: int) -> dict:
    """The text of one cleaned chapter (0-based), to review before converting."""
    return service.drafts.chapter(draft_id, n)


@router.get("/drafts/{draft_id}/std.epub", response_class=FileResponse, responses=ERRORS, tags=["drafts"])
def download_std(draft_id: str) -> FileResponse:
    """The cleaned book, to edit in Sigil."""
    path, name = service.drafts.std_path(draft_id)
    return FileResponse(path, media_type="application/epub+zip", filename=name)


@router.put("/drafts/{draft_id}/std.epub", response_model=Replaced, responses=ERRORS, tags=["drafts"])
def replace_std(draft_id: str, file: UploadFile = File(...)) -> dict:
    """Replace the cleaned book with a version edited in Sigil; the book keeps its library id."""
    return {"chapters": service.drafts.replace_std(draft_id, file.file)}


@router.post("/drafts/{draft_id}/approve", response_model=JobCreated, responses=ERRORS, tags=["drafts"])
def approve(draft_id: str, body: Optional[ApproveRequest] = None) -> dict:
    """Convert the cleaned book. Converting a done draft again resumes from the cached sentences."""
    body = body or ApproveRequest()
    return {"job_id": service.drafts.approve(draft_id, body.voice, body.speed, body.chapters)["id"]}


@router.delete("/drafts/{draft_id}", response_model=Ok, responses=ERRORS, tags=["drafts"])
def delete_draft(draft_id: str) -> dict:
    """Discard the upload and its cleaned version (a converted book stays in the library)."""
    service.drafts.delete(draft_id)
    return {"ok": True}


# ---------------------------------------------------------------- jobs: conversion progress

@router.get("/jobs", response_model=list[Job], tags=["jobs"])
def list_jobs() -> list[dict]:
    """Conversions since the server started, newest first."""
    return service.jobs.public()


@router.get("/jobs/{job_id}", response_model=Job, responses={404: {"model": Error}}, tags=["jobs"])
def get_job(job_id: str) -> dict:
    return service.jobs.get(job_id)


# ---------------------------------------------------------------- library

@router.get("/books", response_model=list[BookSummary], tags=["library"])
def list_books() -> list[dict]:
    return service.list_books()


@router.get("/books/{book_id}", response_model=Book, responses={404: {"model": Error}}, tags=["library"])
def get_book(book_id: str) -> dict:
    return service.read_book(book_id)


@router.get("/books/{book_id}/files/{name}", response_class=FileResponse, responses={404: {"model": Error}},
            tags=["library"])
def get_file(book_id: str, name: str,
             download: bool = Query(False, description="Send as an attachment with a readable file name, "
                                                       "e.g. \"Book Title - Ch 01 - Chapter Title.m4a\"")
             ) -> FileResponse:
    """A chapter's audio (.m4a) or the cover. Supports HTTP Range, so downloads resume and players seek.

    Without `download` the file is served inline (no Content-Disposition), for players and <img>.
    """
    path = service.book_file(book_id, name)
    if download:
        return FileResponse(path, filename=service.download_name(book_id, name), content_disposition_type="attachment")
    return FileResponse(path)


@router.delete("/books/{book_id}", response_model=Ok, responses={404: {"model": Error}}, tags=["library"])
def delete_book(book_id: str) -> dict:
    service.delete_book(book_id)
    return {"ok": True}
