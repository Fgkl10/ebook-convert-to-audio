"""The JSON API, version 1 (D-032): every book operation, for the web page and the Android app alike.

Routes are thin: they read the request, call desktop/server/service.py and return the models below, which are the written
contract (served as /openapi.json and /docs). Errors are always JSON {"detail": "..."} with the status code.
Uploads are multipart; every other body is JSON. A breaking change goes into a new /api/v2, never into v1.
Every route needs the pairing token unless the request comes from the PC itself (D-037, server/auth.py).
"""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import auth, network, service
from ..core.normalize import OCR_MODES

API_VERSION = 1
PREFIX = f"/api/v{API_VERSION}"

router = APIRouter(prefix=PREFIX, dependencies=[Depends(auth.require_pairing)],
                   responses={401: {"description": "Not paired: no or wrong token from another device"}})

DraftStatus = Literal["cleaning", "review", "queued", "converting", "done", "error"]
JobStatus = Literal["queued", "running", "done", "error", "cancelled"]


# ---------------------------------------------------------------- models

class Address(BaseModel):
    address: str = Field(description="An IPv4 address of the PC, a typed host name, or [IPv6]")
    adapter: str = Field(description="The network adapter's name (e.g. \"ZeroTier Virtual Port\"), \"typed\", or \"\"")
    url: str = Field(description="http://address:port")
    pair_url: str = Field(description="url + /#token=… : what the QR code holds")
    qr_svg: Optional[str] = Field(description="QR code of pair_url as SVG, or null")


class VoiceDetail(BaseModel):
    id: str
    gender: Literal["female", "male"]
    accent: Optional[Literal["us", "gb"]] = Field(description="English voices: American or British")
    name: Optional[str] = Field(description="The voice's own name ('Heart'); null for a numbered voice")
    number: Optional[int] = Field(description="A numbered voice's number (Kokoro v1.1-zh's zf_001 = 1)")
    traits: list[Literal["low", "high", "slow", "fast"]] = Field(
        description="Measured, relative to the voices of the same model, language and gender: pitch low/high, "
                    "pace slow/fast; none for the middle third (D-046)")


class VoiceLanguage(BaseModel):
    code: Literal["en", "zh"]
    voices: list[str]
    default_voice: str
    voice_details: list[VoiceDetail] = Field(description="The same voices, in the same order, with what to call "
                                                         "them (D-046)")


class Info(BaseModel):
    api_version: int
    name: str = Field(description="The PC's host name")
    url: str = Field(description="The address the phone connects to by default (the local one, or --advertise)")
    qr_svg: Optional[str] = Field(description="QR code to pair a phone at url (holds the token), or null")
    urls: list[Address] = Field(description="Every address of the PC, the default first, each with its own QR code")
    voices: list[str] = Field(description="Every voice, all languages (apps before D-043 read only this)")
    default_voice: str = Field(description="The English default voice")
    languages: list[VoiceLanguage] = Field(description="The voices by the language they speak (D-043)")
    ocr_modes: list[str]


class TtsModel(BaseModel):
    id: Literal["kokoro-v1.1-zh"]
    installed: bool
    installing: bool
    done_bytes: int = Field(description="Downloaded so far, while installing")
    total_bytes: int
    error: Optional[str]


class TtsBackend(BaseModel):
    id: str
    name: str


class TtsSetting(BaseModel):
    backend: str = Field(description="The TTS backend in use (D-045)")
    backends: list[TtsBackend] = Field(description="The backends this server can use")
    fixed_by: Optional[str] = Field(description='"--tts" or "EBOOK_AUDIO_TTS" when one of them chose the backend at '
                                                "server start: it can't be changed here then")


class TtsChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: str


class Report(BaseModel):
    source: str
    method: str
    language: str = Field("en", description="\"en\" or \"zh\", detected from the text (D-042)")
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
    voice: str = ""
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
    converted: list[int] = Field([], description="1-based chapters already in the library book with this text")


class DraftDetail(Draft):
    report: Optional[Report] = Field(description="The cleaning report; null until cleaned")
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
    size_bytes: int = Field(description="Size of the .m4a; with updated_ms, tells a phone its copy is stale (D-038)")
    updated_ms: int = Field(description="When the .m4a was written (epoch milliseconds). A re-converted chapter "
                                        "keeps its file name, so compare this with the downloaded copy")
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
    language: str = Field("en", description="\"en\" or \"zh\" (books before D-042 are English)")
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


def _address(host: str, adapter: str, port: int) -> dict:
    pair = network.pair_url(host, port, auth.token())
    return {"address": host, "adapter": adapter, "url": network.base_url(host, port), "pair_url": pair,
            "qr_svg": network.qr_svg(pair)}


# ---------------------------------------------------------------- server

@router.get("/info", response_model=Info, tags=["server"])
def info(request: Request) -> dict:
    """Server facts for the page and the app. Holds the pairing token (in each QR code), so it needs pairing too."""
    port = request.app.state.port
    urls = [_address(a["address"], a["adapter"], port)
            for a in network.phone_addresses(getattr(request.app.state, "advertise", None))]
    return {"api_version": API_VERSION, "name": socket.gethostname(), "url": urls[0]["url"],
            "qr_svg": urls[0]["qr_svg"], "urls": urls,
            "ocr_modes": list(OCR_MODES), **_voices()}


def _voices() -> dict:
    """/info's voice fields, from the TTS backend in use (D-045)."""
    tts = service.tts()
    return {"voices": tts.voice_ids(), "default_voice": tts.default_voice("en"),
            "languages": [{"code": lang, "voices": tts.voice_ids(lang), "default_voice": tts.default_voice(lang),
                           "voice_details": [v.public() for v in tts.voices(lang)]}
                          for lang in tts.languages()]}


@router.get("/models/zh", response_model=TtsModel, tags=["server"])
def zh_model() -> dict:
    """The optional Kokoro v1.1-zh model (better Chinese voices, D-044): installed, or how far its download is."""
    return service.zh_model.status()


@router.post("/models/zh", response_model=TtsModel, responses=ERRORS, tags=["server"])
def install_zh_model() -> dict:
    """Start downloading Kokoro v1.1-zh (~330 MB). Poll GET to follow it. Nothing happens when it is installed."""
    service.install_zh_model()
    return service.zh_model.status()


@router.delete("/models/zh", response_model=TtsModel, responses=ERRORS, tags=["server"])
def remove_zh_model() -> dict:
    """Remove Kokoro v1.1-zh. Refused while a conversion uses one of its voices. Chinese goes back to v1.0's voices."""
    service.remove_zh_model()
    return service.zh_model.status()


@router.get("/settings/tts", response_model=TtsSetting, tags=["server"])
def tts_setting() -> dict:
    """The TTS backend in use and the ones on offer (D-045)."""
    return service.tts_setting()


@router.put("/settings/tts", response_model=TtsSetting, responses=ERRORS, tags=["server"])
def set_tts(choice: TtsChoice) -> dict:
    """Use another TTS backend from now on (kept across restarts). 409 while a conversion is queued or running, or
    when --tts / EBOOK_AUDIO_TTS chose it. Voices of the old backend give way to the new one's defaults."""
    return service.set_tts(choice.backend)


@router.get("/qr", response_model=Address, responses=ERRORS, tags=["server"])
def qr(request: Request, address: str = Query(description="A host name, IPv4 or [IPv6] address, optional :port")
       ) -> dict:
    """A pairing QR code for an address typed by hand (e.g. a ZeroTier or VPN address the PC doesn't list)."""
    host, port = network.parse_address(address, request.app.state.port)
    return _address(host, "typed", port)


class SavedSamples(BaseModel):
    count: int = Field(description="Voice samples kept on the PC")
    bytes: int


@router.get("/voices/samples", response_model=SavedSamples, tags=["server"])
def saved_samples() -> dict:
    """The voice samples kept on the PC (each is made on its first ▶, then reused)."""
    return service.saved_samples()


@router.delete("/voices/samples", response_model=SavedSamples, tags=["server"])
def delete_samples() -> dict:
    """Delete the kept voice samples → what is left (nothing). The next ▶ of each voice makes it again."""
    return service.delete_samples()


@router.get("/voices/{voice}/sample", response_class=FileResponse, responses={404: {"model": Error}},
            tags=["server"])
def voice_sample(voice: str) -> FileResponse:
    """About 5 s of the voice reading one fixed sentence (audio/mp4). The first one loads the model (~10 s)."""
    return FileResponse(service.voice_sample(voice), media_type="audio/mp4")


# ---------------------------------------------------------------- drafts: clean and review

@router.post("/drafts", response_model=DraftCreated, responses=ERRORS, tags=["drafts"])
def create_draft(file: UploadFile = File(...), voice: Optional[str] = Form(None), speed: float = Form(1.0),
                 auto: bool = Form(False), ocr: str = Form("auto")) -> dict:
    """Upload an .epub, .pdf or .txt to clean. auto=true converts right after cleaning, with no review stop.
    ocr (PDF only): auto, always or never."""
    draft = service.drafts.create(file.file, _upload_name(file), auto, voice, speed, ocr)
    return {"draft_id": draft["id"]}


@router.post("/drafts/cleaned", response_model=CleanedCreated, responses=ERRORS, tags=["drafts"])
def create_cleaned(file: UploadFile = File(...), voice: Optional[str] = Form(None),
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


@router.post("/drafts/{draft_id}/cancel", response_model=Job, responses=ERRORS, tags=["drafts"])
def cancel_draft(draft_id: str) -> dict:
    """Stop the draft's queued or running conversion (same as POST /jobs/{job_id}/cancel with its job_id).
    The draft goes back to review. 409 if it isn't converting."""
    return service.drafts.cancel(draft_id)


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


@router.post("/jobs/{job_id}/cancel", response_model=Job, responses=ERRORS, tags=["jobs"])
def cancel_job(job_id: str) -> dict:
    """Stop a queued or running conversion. Finished chapters and cached sentences are kept, so approving the
    draft again resumes. 409 if the job has already ended."""
    return service.jobs.cancel(job_id)


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


@router.delete("/books/{book_id}", response_model=Ok, responses={404: {"model": Error}, 409: {"model": Error}},
               tags=["library"])
def delete_book(book_id: str) -> dict:
    """Delete a book folder. 409 while a conversion of the book is queued or running: cancel it first."""
    service.delete_book(book_id)
    return {"ok": True}
