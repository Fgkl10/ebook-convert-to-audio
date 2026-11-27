"""API v1 contract tests (D-032): one test per endpoint, the error format, and the frontend/backend split.
IDs refer to desktop/docs/test-cases.md (API-xx). The flow tests are in tests/test_server.py.
"""
import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import unquote

import pytest

from desktop import PROJECT
from desktop.server import api as api_module
from desktop.server import service
from tests.test_server import STORY, V1, _upload, _wait, api  # noqa: F401 - api is a fixture

STATIC = PROJECT / "desktop" / "web"

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
    data = Path(os.environ["EBOOK_AUDIO_DATA"]).resolve()
    assert data != PROJECT and service.DRAFTS.parent == data  # conftest moved it before the import


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


def _attachment_name(r) -> str:
    """The saved file name a browser takes from Content-Disposition (filename* wins over filename)."""
    cd = r.headers["content-disposition"]
    assert cd.startswith("attachment;"), cd
    m = re.search(r"filename\*=utf-8''([^;]+)", cd)
    return unquote(m.group(1)) if m else re.search(r'filename="([^"]*)"', cd).group(1)


def _write_book(book_id: str, title: str, chapter_titles: list[str]) -> Path:
    d = service.LIBRARY / book_id
    d.mkdir(parents=True)
    chapters = []
    for i, t in enumerate(chapter_titles):
        (d / f"ch{i:03d}.m4a").write_bytes(AUDIO)
        chapters.append({"index": i, "title": t, "audio": f"ch{i:03d}.m4a", "duration_ms": 1, "sentences": []})
    (d / "book.json").write_text(json.dumps({"id": book_id, "title": title, "chapters": chapters}), encoding="utf-8")
    return d


def test_api18_chapter_download_name(api, book):  # noqa: F811
    url = f"{V1}/books/{book.name}/files/ch000.m4a"
    inline = api.get(url)  # the player's request: no attachment, so playback stays inline
    assert inline.status_code == 200 and "content-disposition" not in inline.headers
    r = api.get(url, params={"download": 1})
    assert r.status_code == 200 and r.content == AUDIO
    assert _attachment_name(r) == "A Made-Up Book - Ch 01 - One.m4a"
    part = api.get(url, params={"download": 1}, headers={"Range": "bytes=2000-"})  # a resumed download
    assert part.status_code == 206 and part.content == AUDIO[2000:]
    assert _attachment_name(part) == "A Made-Up Book - Ch 01 - One.m4a"
    cover = api.get(f"{V1}/books/{book.name}/files/cover.jpg", params={"download": 1})
    assert _attachment_name(cover) == "A Made-Up Book - cover.jpg"
    assert "content-disposition" not in api.get(f"{V1}/books/{book.name}/files/cover.jpg").headers
    assert api.get(f"{V1}/books/{book.name}/files/missing.m4a", params={"download": 1}).status_code == 404
    assert api.get(f"{V1}/books/nope/files/ch000.m4a", params={"download": 1}).status_code == 404
    js = (STATIC / "app.js").read_text(encoding="utf-8")  # the reader's per-chapter button uses it
    assert re.search(r"files/\$\{esc\(c\.audio\)\}\?download=1\" download", js)
    assert "a.dl').forEach(a => a.onclick = e => e.stopPropagation())" in js  # downloading doesn't switch chapter


def test_api19_download_names_are_safe_and_keep_unicode(api):  # noqa: F811
    d = _write_book("odd-names-0123abcd", 'What/Why: "A" <Tale>?. ', ["中文 章节", "", "Line\nbreak|pipe..."])
    names = [_attachment_name(api.get(f"{V1}/books/{d.name}/files/ch{i:03d}.m4a", params={"download": 1}))
             for i in range(3)]
    assert names == ["What Why A Tale - Ch 01 - 中文 章节.m4a",
                     "What Why A Tale - Ch 02.m4a",
                     "What Why A Tale - Ch 03 - Line break pipe.m4a"]
    long = _write_book("long-book-0123abcd", "T" * 300, [f"c{i}" for i in range(120)])
    name = service.download_name(long.name, "ch007.m4a")
    assert name.endswith(".m4a") and len(name.encode()) <= 200 and " - " not in name  # cut inside the long title
    cjk = _write_book("cjk-book-0123abcd", "长" * 60, ["章" * 40])  # 300 bytes of UTF-8 before the cut
    name = service.download_name(cjk.name, "ch000.m4a")
    assert name.endswith(".m4a") and len(name.encode()) <= 200 and not name.endswith("-.m4a")
    assert name.startswith("长" * 60 + " - Ch 01 - 章")  # cut between whole characters, never inside one
    assert service.download_name(long.name, "ch119.m4a").startswith("T")
    short = _write_book("short-book-0123abcd", "Short", [f"c{i}" for i in range(120)])
    assert service.download_name(short.name, "ch007.m4a") == "Short - Ch 008 - c7.m4a"  # 3 digits for 100+ chapters
    untitled = _write_book("untitled-0123abcd", "", ["One"])
    assert service.download_name(untitled.name, "ch000.m4a") == "Ch 01 - One.m4a"


def test_api18_download_name_uses_chapter_number(api):  # noqa: F811
    d = _write_book("only-four-0123abcd", "Partial", ["One", "Two", "Three", "Four"])
    m = json.loads((d / "book.json").read_text(encoding="utf-8"))
    m["chapters"] = [{**m["chapters"][3], "number": 4}]
    m["chapters_total"] = 120
    (d / "book.json").write_text(json.dumps(m), encoding="utf-8")
    assert service.download_name(d.name, "ch003.m4a") == "Partial - Ch 004 - Four.m4a"  # padded for 120 chapters
    assert api.get(f"{V1}/books/{d.name}").json()["chapters"][0]["number"] == 4


# ---------------------------------------------------------------- choosing chapters (D-035)

def _approve(api, draft_id, **body):
    r = api.post(f"{V1}/drafts/{draft_id}/approve", json=body)
    assert r.status_code == 200, r.text
    return _wait(api, draft_id, "done", "review")


def test_api20_convert_chosen_chapters_into_one_book(api):  # noqa: F811
    draft_id = _upload(api, "story.txt", STORY.encode())
    d = _wait(api, draft_id, "review")
    assert d["converted"] == [] and d["book_voice"] is None
    for bad in ([], [0], [99], [1, 1]):
        r = api.post(f"{V1}/drafts/{draft_id}/approve", json={"chapters": bad})
        assert r.status_code == 400 and isinstance(r.json()["detail"], str), bad
    assert api.post(f"{V1}/drafts/{draft_id}/approve", json={"chapters": ["x"]}).status_code == 422

    d = _approve(api, draft_id, chapters=[2], voice="bf_emma")
    assert d["status"] == "done" and d["converted"] == [2] and d["last_chapters"] == [2]
    assert d["book_voice"] == "bf_emma" and d["book_speed"] == 1.0
    [b] = api.get(f"{V1}/books").json()
    assert b["id"] == d["book_id"] and (b["chapters"], b["chapters_total"], b["complete"]) == (1, 2, False)
    assert b["converting"] is False

    d = _approve(api, draft_id, chapters=[1], voice="af_heart")  # without it, the draft's last voice (bf_emma)
    assert d["converted"] == [1, 2]
    [b] = api.get(f"{V1}/books").json()  # still one book
    assert (b["chapters"], b["complete"]) == (2, True)
    m = api.get(f"{V1}/books/{b['id']}").json()
    assert [(c["number"], c["voice"]) for c in m["chapters"]] == [(1, "af_heart"), (2, "bf_emma")]


def test_api21_edited_chapter_counts_as_not_converted(api):  # noqa: F811
    from tests.test_server import _rename_first_chapter
    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    assert _approve(api, draft_id)["converted"] == [1, 2]
    edited = _rename_first_chapter(api.get(f"{V1}/drafts/{draft_id}/std.epub").content, "The Dark Night")
    assert api.put(f"{V1}/drafts/{draft_id}/std.epub", files={"file": ("x.std.epub", edited)}).status_code == 200
    d = api.get(f"{V1}/drafts/{draft_id}").json()
    assert d["converted"] == [2] and d["last_chapters"] is None


def test_api22_library_says_converting_while_queued_or_running(api):  # noqa: F811
    gate = threading.Event()

    class SlowTTS(type(service.jobs.tts)):
        def synth(self, text, voice=None, speed=None):
            gate.wait(10)
            return super().synth(text, voice, speed)

    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    _approve(api, draft_id, chapters=[1])  # the book exists, with chapter 1
    assert api.get(f"{V1}/books").json()[0]["converting"] is False
    service.jobs.tts = SlowTTS()
    try:
        assert api.post(f"{V1}/drafts/{draft_id}/approve", json={"chapters": [2]}).status_code == 200
        [b] = api.get(f"{V1}/books").json()  # held at the first sentence: queued or running
        assert b["converting"] is True and b["chapters"] == 1
    finally:
        gate.set()
    _wait(api, draft_id, "done")
    [b] = api.get(f"{V1}/books").json()
    assert b["converting"] is False and b["complete"] is True


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


def test_api17_older_files_still_serve(api, monkeypatch, tmp_path):  # noqa: F811
    """A draft.json from before D-030 (no ocr, few fields) and a manifest with a null author must not turn a list
    into a 500."""
    root = tmp_path / "old-drafts"
    (root / "abc123").mkdir(parents=True)
    (root / "abc123" / "draft.json").write_text(json.dumps(
        {"id": "abc123", "status": "error", "created": 1, "error": "x", "message": "Failed"}), encoding="utf-8")
    monkeypatch.setattr(service, "drafts", service.Drafts(root))
    assert [d["ocr"] for d in api.get(f"{V1}/drafts").json()] == ["auto"]
    assert api.get(f"{V1}/drafts/abc123").json()["report"] is None
    d = service.LIBRARY / "old-book-0123abcd"
    d.mkdir(parents=True)
    (d / "book.json").write_text(json.dumps({"id": d.name, "title": "Old", "author": None, "chapters": []}),
                                 encoding="utf-8")
    assert api.get(f"{V1}/books").json()[0]["author"] is None
    assert api.get(f"{V1}/books/{d.name}").json()["complete"] is False


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
