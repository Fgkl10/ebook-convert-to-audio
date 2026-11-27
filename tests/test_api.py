"""API v1 contract tests (D-032): one test per endpoint, the error format, and the frontend/backend split.
IDs refer to desktop/docs/test-cases.md (API-xx). The flow tests are in tests/test_server.py.
"""
import json
import os
import re
import time
from pathlib import Path

import pytest

from desktop import api as api_module
from desktop import service
from tests.test_server import STORY, V1, _upload, _wait, api  # noqa: F401 - api is a fixture

STATIC = Path(service.__file__).resolve().parent / "static"

# The whole v1 surface. Changing the API means changing this list on purpose (the Android app depends on it).
EXPECTED_ROUTES = {
    ("GET", "/api/v1/info"),
    ("GET", "/api/v1/voices/{voice}/sample"),
    ("POST", "/api/v1/drafts"),
    ("POST", "/api/v1/drafts/cleaned"),
    ("GET", "/api/v1/drafts"),
    ("GET", "/api/v1/drafts/{draft_id}"),
    ("GET", "/api/v1/drafts/{draft_id}/chapters/{n}"),
    ("GET", "/api/v1/drafts/{draft_id}/std.epub"),
    ("PUT", "/api/v1/drafts/{draft_id}/std.epub"),
    ("POST", "/api/v1/drafts/{draft_id}/approve"),
    ("DELETE", "/api/v1/drafts/{draft_id}"),
    ("GET", "/api/v1/jobs"),
    ("GET", "/api/v1/jobs/{job_id}"),
    ("GET", "/api/v1/books"),
    ("GET", "/api/v1/books/{book_id}"),
    ("GET", "/api/v1/books/{book_id}/files/{name}"),
    ("DELETE", "/api/v1/books/{book_id}"),
}

AUDIO = bytes(range(256)) * 8  # 2 KB standing in for a chapter's .m4a


@pytest.fixture
def book(api):  # noqa: F811 - pytest fixture chaining
    """A finished book written straight into the library, without converting anything."""
    d = service.LIBRARY / "made-up-book-0123abcd"
    d.mkdir(parents=True)
    (d / "ch000.m4a").write_bytes(AUDIO)
    (d / "cover.jpg").write_bytes(b"\xff\xd8 made-up cover")
    (d / "book.json").write_text(json.dumps({
        "id": d.name, "title": "A Made-Up Book", "author": "Nobody", "cover": "cover.jpg", "voice": "af_heart",
        "speed": 1.0, "complete": True, "chapter_selection": None, "created": 1700000000, "duration_ms": 1500,
        "chapters": [{"index": 0, "title": "One", "audio": "ch000.m4a", "duration_ms": 1500, "sentences": [
            {"i": 0, "p": 0, "text": "Hello there.", "start_ms": 300, "end_ms": 1500}]}],
    }), encoding="utf-8")
    return d


# ---------------------------------------------------------------- contract

def test_api01_routes_are_exactly_v1(api):  # noqa: F811
    spec = api.get("/openapi.json").json()
    routes = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}
    assert routes == EXPECTED_ROUTES
    assert spec["info"]["version"] == "1"
    for name in ("Draft", "DraftDetail", "Job", "BookSummary", "Book", "Info", "ApproveRequest", "Error"):
        assert name in spec["components"]["schemas"], name
    assert api.get("/docs").status_code == 200


def test_api02_old_unversioned_routes_are_gone(api):  # noqa: F811
    assert api.get("/api/books").status_code == 404
    assert api.get("/api/jobs").status_code == 404
    assert api.post("/api/clean", files={"file": ("x.txt", b"x")}).status_code == 404
    assert api.post("/api/convert", files={"file": ("x.txt", b"x")}).status_code == 404


def test_api03_page_calls_only_existing_v1_routes():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert re.search(r"const API = '/api/v1';", js)
    assert "/api/" not in js.replace("const API = '/api/v1';", "")  # no other hard-coded API path
    calls = re.findall(r"\$\{API\}(/[^`'\s]*)|getJSON\(['`](/[^'`]*)['`]", js)
    paths = {a or b for a, b in calls}
    assert len(paths) >= 10
    patterns = [re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p.removeprefix(V1)) + "$")
                for _m, p in EXPECTED_ROUTES]
    for path in paths:
        concrete = re.sub(r"\$\{[^}]+\}", "x", path)
        assert any(p.match(concrete) for p in patterns), path
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "<style>" not in html  # markup only; code and style are separate files


def test_api04_backend_has_no_http_in_it():
    src = Path(service.__file__).read_text(encoding="utf-8")
    assert "fastapi" not in src and "HTTPException" not in src
    assert issubclass(service.NotFound, service.ServiceError) and service.NotFound.status == 404
    assert service.Conflict.status == 409 and service.Invalid.status == 400


def test_api05_test_data_folder_is_not_the_project():
    project = Path(service.__file__).resolve().parent.parent
    data = Path(os.environ["EBOOK_AUDIO_DATA"]).resolve()
    assert data != project and service.DRAFTS.parent == data  # conftest moved it before the import


# ---------------------------------------------------------------- page and static files

def test_api06_page_and_static_files(api):  # noqa: F811
    r = api.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"] and "/static/app.js" in r.text
    assert "text/css" in api.get("/static/app.css").headers["content-type"]
    js = api.get("/static/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert api.get("/static/nope.js").status_code == 404


# ---------------------------------------------------------------- server

def test_api07_info(api):  # noqa: F811
    info = api.get(f"{V1}/info").json()
    assert info["api_version"] == 1 and info["url"].startswith("http://") and info["url"].endswith(":8000")
    assert "af_heart" in info["voices"] and info["default_voice"] in info["voices"]
    assert info["ocr_modes"] == ["auto", "always", "never"]


# ---------------------------------------------------------------- drafts

def test_api08_draft_list_and_detail(api):  # noqa: F811
    assert api.get(f"{V1}/drafts").json() == []
    draft_id = _upload(api, "story.txt", STORY.encode(), voice="bf_emma", speed=1.2)
    d = _wait(api, draft_id, "review")
    assert d["voice"] == "bf_emma" and d["speed"] == 1.2 and d["report"]["chapters"][0][0] == "Chapter 1"
    listed = api.get(f"{V1}/drafts").json()
    assert [x["id"] for x in listed] == [draft_id] and "report" not in listed[0]


def test_api09_approve_takes_json_with_defaults(api):  # noqa: F811
    draft_id = _upload(api, "story.txt", STORY.encode(), voice="bm_lewis", speed=1.3)
    _wait(api, draft_id, "review")
    assert api.post(f"{V1}/drafts/{draft_id}/approve", json={"speed": 3}).status_code == 400
    assert api.post(f"{V1}/drafts/{draft_id}/approve", json={"speed": "fast"}).status_code == 422
    r = api.post(f"{V1}/drafts/{draft_id}/approve")  # no body: the upload's voice and speed
    assert r.status_code == 200
    job = api.get(f"{V1}/jobs/{r.json()['job_id']}").json()
    assert job["voice"] == "bm_lewis" and job["speed"] == 1.3
    assert api.post(f"{V1}/drafts/nope/approve", json={}).status_code == 404


def test_api10_std_download_before_cleaning_is_conflict(api, monkeypatch):  # noqa: F811
    monkeypatch.setattr(service.Drafts, "_worker", lambda self: None)  # nothing ever cleans
    monkeypatch.setattr(service, "drafts", service.Drafts(service.DRAFTS.parent / "drafts-idle"))
    draft_id = _upload(api, "story.txt", STORY.encode())
    for path in (f"/drafts/{draft_id}/std.epub", f"/drafts/{draft_id}/chapters/0"):
        r = api.get(V1 + path)
        assert r.status_code == 409 and r.json()["detail"] == "This book is not cleaned yet", path
    assert api.get(f"{V1}/drafts/{draft_id}").json()["report"] is None
    r = api.put(f"{V1}/drafts/{draft_id}/std.epub", files={"file": ("x.epub", b"x")})
    assert r.status_code == 409
    assert api.delete(f"{V1}/drafts/{draft_id}").status_code == 409  # still cleaning


# ---------------------------------------------------------------- jobs

def test_api11_job_progress_until_done(api):  # noqa: F811
    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    job_id = api.post(f"{V1}/drafts/{draft_id}/approve", json={}).json()["job_id"]
    end, job = time.time() + 30, None
    while time.time() < end:
        job = api.get(f"{V1}/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert job["status"] == "done" and job["total"] > 0 and job["done"] == job["total"]
    assert job["draft_id"] == draft_id and job["book_id"] and "_path" not in job
    assert [j["id"] for j in api.get(f"{V1}/jobs").json()] == [job_id]
    r = api.get(f"{V1}/jobs/nope")
    assert r.status_code == 404 and r.json() == {"detail": "No such job"}


# ---------------------------------------------------------------- library

def test_api12_book_list_and_manifest(api, book):  # noqa: F811
    [summary] = api.get(f"{V1}/books").json()
    assert summary["id"] == book.name and summary["chapters"] == 1 and summary["complete"] is True
    assert summary["size_bytes"] > len(AUDIO) and summary["cover"] == "cover.jpg"
    m = api.get(f"{V1}/books/{book.name}").json()
    assert m["chapters"][0]["audio"] == "ch000.m4a" and m["chapters"][0]["sentences"][0]["start_ms"] == 300
    assert m["chapter_selection"] is None  # fields outside the schema still come through
    for bad in ("nope", "UPPER", "..%2Fdrafts"):
        r = api.get(f"{V1}/books/{bad}")
        assert r.status_code == 404 and "detail" in r.json(), bad


def test_api13_file_download_with_range(api, book):  # noqa: F811
    url = f"{V1}/books/{book.name}/files/ch000.m4a"
    full = api.get(url)
    assert full.status_code == 200 and full.content == AUDIO and full.headers["accept-ranges"] == "bytes"
    part = api.get(url, headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and part.content == AUDIO[:100]
    rest = api.get(url, headers={"Range": "bytes=2000-"})  # resuming a download
    assert rest.status_code == 206 and rest.content == AUDIO[2000:]
    assert api.get(f"{V1}/books/{book.name}/files/cover.jpg").content.startswith(b"\xff\xd8")
    for name in ("missing.m4a", ".hidden", "..%2Fbook.json", "..%5Cbook.json"):
        assert api.get(f"{V1}/books/{book.name}/files/{name}").status_code == 404, name


def test_api14_delete_book(api, book):  # noqa: F811
    assert api.delete(f"{V1}/books/{book.name}").json() == {"ok": True}
    assert not book.exists() and api.get(f"{V1}/books").json() == []
    assert api.delete(f"{V1}/books/{book.name}").status_code == 404


def test_api15_errors_are_json_detail(api):  # noqa: F811
    for method, path in (("get", "/drafts/nope"), ("get", "/books/nope"), ("get", "/jobs/nope"),
                         ("get", "/voices/nope/sample"), ("delete", "/books/nope")):
        r = getattr(api, method)(V1 + path)
        assert r.status_code == 404 and r.headers["content-type"] == "application/json"
        assert isinstance(r.json()["detail"], str), path
    r = api.post(f"{V1}/drafts")  # no file: FastAPI's own validation error, same "detail" key
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)


def test_api16_service_raises_without_http():
    drafts = service.Drafts(service.DRAFTS.parent / "drafts-unit")
    with pytest.raises(service.NotFound):
        drafts.get("nope")
    with pytest.raises(service.Invalid, match="Upload an"):
        drafts.create(None, "x.docx")
    with pytest.raises(service.NotFound):
        service.read_book("nope")
    with pytest.raises(service.NotFound):
        service.voice_sample("zz_nobody")
    assert api_module.PREFIX == "/api/v1"
