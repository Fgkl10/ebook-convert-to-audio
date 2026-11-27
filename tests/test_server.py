"""Server API tests: the clean → review → approve → convert flow (D-029). IDs refer to desktop/docs/test-cases.md.

Real workers run in background threads; the TTS is fake and every folder lives in tmp_path.
"""
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from desktop import build, server
from tests.epub_factory import build_epub, novel_spec
from tests.test_desktop import FakeTTS
from tests.test_language import EN, HU

STORY = ("Chapter 1\n\nIt was a dark night. The wind howled loudly over the hills.\n\n"
         "Chapter 2\n\nMorning came at last. Everyone was relieved to see the sun.\n\n" + EN * 3)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(server, "LIBRARY", tmp_path / "library")
    def fake_tts(voice, speed):
        tts = FakeTTS()
        tts.voice, tts.speed = voice, speed
        return tts

    jobs = server.Jobs()
    monkeypatch.setattr(jobs, "_get_tts", fake_tts)
    monkeypatch.setattr(server, "jobs", jobs)
    monkeypatch.setattr(server, "drafts", server.Drafts(tmp_path / "drafts"))
    return TestClient(server.app)


def _upload(api, name, data, **form):
    r = api.post("/api/clean", files={"file": (name, data)}, data={k: str(v).lower() for k, v in form.items()})
    assert r.status_code == 200, r.text
    return r.json()["draft_id"]


def _wait(api, draft_id, *statuses, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        d = api.get(f"/api/drafts/{draft_id}").json()
        if d["status"] in statuses:
            return d
        time.sleep(0.05)
    raise AssertionError(f"draft stayed {d['status']}: {d['message']} {d['error']}")


def test_srv19_clean_stops_for_review(api, tmp_path):
    epub = build_epub(tmp_path / "novel.epub", novel_spec())
    draft_id = _upload(api, "novel.epub", epub.read_bytes())
    d = _wait(api, draft_id, "review", "error")
    assert d["status"] == "review" and d["job_id"] is None
    titles = [t for t, _ in d["report"]["chapters"]]
    assert titles[-3:] == ["1 The River", "2 The Mill", "3 The Storm"]
    ch = api.get(f"/api/drafts/{draft_id}/chapters/{len(titles) - 3}").json()
    assert ch["title"] == "1 The River" and ch["paragraphs"][1].startswith("The river remembered")
    assert api.get(f"/api/drafts/{draft_id}/chapters/99").status_code == 404
    assert api.get("/api/jobs").json() == []  # nothing converts before approval
    r = api.get(f"/api/drafts/{draft_id}/std.epub")
    assert r.status_code == 200 and r.headers["content-type"] == "application/epub+zip"
    assert 'filename="novel.std.epub"' in r.headers["content-disposition"]


def test_srv20_approve_converts_into_library(api):
    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    r = api.post(f"/api/drafts/{draft_id}/approve", data={"voice": "am_adam", "speed": "1.1"})
    assert r.status_code == 200
    d = _wait(api, draft_id, "done")
    books = api.get("/api/books").json()
    assert [b["id"] for b in books] == [d["book_id"]] and books[0]["voice"] == "am_adam"
    assert books[0]["title"] == "story"  # a TXT takes its title from the uploaded file's name
    assert api.post(f"/api/drafts/{draft_id}/approve", data={"voice": "nope"}).status_code == 400


def test_srv21_auto_converts_without_review(api):
    draft_id = _upload(api, "story.txt", STORY.encode(), auto=True)
    d = _wait(api, draft_id, "done")
    assert [b["id"] for b in api.get("/api/books").json()] == [d["book_id"]]


def test_srv21_convert_endpoint_is_clean_with_auto(api):
    r = api.post("/api/convert", files={"file": ("story.txt", STORY.encode())})
    d = _wait(api, r.json()["draft_id"], "done")
    assert d["auto"] is True


def _rename_first_chapter(epub_bytes: bytes, new_title: str) -> bytes:
    """What an edit in Sigil looks like: one chapter renamed in its heading and the navigation, markers dropped."""
    src, out = zipfile.ZipFile(io.BytesIO(epub_bytes)), io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for info in src.infolist():
            data = src.read(info)
            if info.filename.endswith((".xhtml", ".html", ".ncx")):
                data = data.replace(b"Chapter 1", new_title.encode())
            if info.filename.endswith(".opf"):
                data = data.replace(b"ebook-audio:", b"x-dropped:")  # an editor that drops our markers
            z.writestr(info, data)
    return out.getvalue()


def test_srv22_edited_std_replaces_draft_and_keeps_book_id(api):
    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    edited = _rename_first_chapter(api.get(f"/api/drafts/{draft_id}/std.epub").content, "The Dark Night")
    r = api.post(f"/api/drafts/{draft_id}/std.epub", files={"file": ("x.std.epub", edited)})
    assert r.status_code == 200, r.text
    d = api.get(f"/api/drafts/{draft_id}").json()
    assert d["report"]["chapters"][0][0] == "The Dark Night"
    assert any("edited .std.epub uploaded" in n for n in d["report"]["notes"])
    api.post(f"/api/drafts/{draft_id}/approve", data={})
    d = _wait(api, draft_id, "done")
    digest = d["source_sha1"][:8]
    assert d["book_id"].endswith(digest)  # the id comes from the original upload, not the edited file
    m = api.get(f"/api/books/{d['book_id']}").json()
    assert m["chapters"][0]["title"] == "The Dark Night"
    bad = api.post(f"/api/drafts/{draft_id}/std.epub", files={"file": ("x.epub", b"not a zip")})
    assert bad.status_code == 400


def test_srv23_discard_removes_draft(api, tmp_path):
    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    assert api.delete(f"/api/drafts/{draft_id}").json() == {"ok": True}
    assert not (tmp_path / "drafts" / draft_id).exists()
    assert api.get(f"/api/drafts/{draft_id}").status_code == 404
    assert api.get("/api/drafts").json() == []


def test_srv24_bad_ids_and_inputs(api):
    for path in ("/api/drafts/nope", "/api/drafts/..%2Flibrary", "/api/drafts/Nope!/std.epub",
                 "/api/drafts/abc/chapters/0"):
        assert api.get(path).status_code == 404, path
    assert api.post("/api/clean", files={"file": ("x.docx", b"x")}).status_code == 400
    assert api.post("/api/clean", files={"file": ("x.txt", b"x")}, data={"speed": "2.5"}).status_code == 400
    assert api.post("/api/clean", files={"file": ("x.txt", b"x")}, data={"voice": "zz"}).status_code == 400


def test_srv10_language_refusal_is_a_draft_error(api):
    draft_id = _upload(api, "hu.txt", "\n\n".join([HU] * 8).encode())
    d = _wait(api, draft_id, "error")
    assert "English" in d["error"] or "language" in d["error"].lower()
    assert d["report"] is None
    assert api.post(f"/api/drafts/{draft_id}/approve", data={}).status_code == 409


def test_srv25_restart_marks_interrupted_drafts(tmp_path):
    root = tmp_path / "drafts"
    for draft_id, status in (("aaa", "cleaning"), ("bbb", "converting"), ("ccc", "review")):
        (root / draft_id).mkdir(parents=True)
        (root / draft_id / "draft.json").write_text(json.dumps(
            {"id": draft_id, "status": status, "created": 0, "error": None, "message": ""}), encoding="utf-8")
    drafts = server.Drafts(root)
    assert drafts.drafts["aaa"]["status"] == "error" and "restart" in drafts.drafts["aaa"]["error"]
    assert drafts.drafts["bbb"]["status"] == "review" and "approve again" in drafts.drafts["bbb"]["message"]
    assert drafts.drafts["ccc"]["status"] == "review"
    saved = json.loads((root / "aaa" / "draft.json").read_text(encoding="utf-8"))
    assert saved["status"] == "error"
