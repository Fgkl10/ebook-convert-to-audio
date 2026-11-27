"""Server API tests: the clean → review → approve → convert flow (D-029) through /api/v1 (D-032).
IDs refer to desktop/docs/test-cases.md.

Real workers run in background threads; the TTS is fake and every folder lives in tmp_path.
"""
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from desktop import build, server, service
from tests.epub_factory import build_epub, novel_spec
from tests.test_desktop import FakeTTS
from tests.test_language import EN, HU

V1 = "/api/v1"
STORY = ("Chapter 1\n\nIt was a dark night. The wind howled loudly over the hills.\n\n"
         "Chapter 2\n\nMorning came at last. Everyone was relieved to see the sun.\n\n" + EN * 3)


class RecordingTTS(FakeTTS):
    """One shared model like KokoroTTS: synth(text, voice=None, speed=None), every call recorded."""

    def __init__(self):
        self.calls = []

    def synth(self, text, voice=None, speed=None):
        self.calls.append((voice or self.voice, text))
        return super().synth(text)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(service, "LIBRARY", tmp_path / "library")
    monkeypatch.setattr(service, "SAMPLES", tmp_path / "samples")
    jobs = service.Jobs()
    jobs.tts = RecordingTTS()  # model() returns it; the real Kokoro is never loaded
    monkeypatch.setattr(service, "jobs", jobs)
    monkeypatch.setattr(service, "drafts", service.Drafts(tmp_path / "drafts"))
    return TestClient(server.app)


def _upload(api, name, data, **form):
    r = api.post(f"{V1}/drafts", files={"file": (name, data)}, data={k: str(v).lower() for k, v in form.items()})
    assert r.status_code == 200, r.text
    return r.json()["draft_id"]


def _wait(api, draft_id, *statuses, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        d = api.get(f"{V1}/drafts/{draft_id}").json()
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
    ch = api.get(f"{V1}/drafts/{draft_id}/chapters/{len(titles) - 3}").json()
    assert ch["title"] == "1 The River" and ch["paragraphs"][1].startswith("The river remembered")
    assert api.get(f"{V1}/drafts/{draft_id}/chapters/99").status_code == 404
    assert api.get(f"{V1}/jobs").json() == []  # nothing converts before approval
    r = api.get(f"{V1}/drafts/{draft_id}/std.epub")
    assert r.status_code == 200 and r.headers["content-type"] == "application/epub+zip"
    assert 'filename="novel.std.epub"' in r.headers["content-disposition"]


def test_srv20_approve_converts_into_library(api):
    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    r = api.post(f"{V1}/drafts/{draft_id}/approve", json={"voice": "am_adam", "speed": 1.1})
    assert r.status_code == 200
    d = _wait(api, draft_id, "done")
    books = api.get(f"{V1}/books").json()
    assert [b["id"] for b in books] == [d["book_id"]] and books[0]["voice"] == "am_adam"
    assert books[0]["title"] == "story"  # a TXT takes its title from the uploaded file's name
    assert api.post(f"{V1}/drafts/{draft_id}/approve", json={"voice": "nope"}).status_code == 400


def test_srv21_auto_converts_without_review(api):
    draft_id = _upload(api, "story.txt", STORY.encode(), auto=True)
    d = _wait(api, draft_id, "done")
    assert d["auto"] is True
    assert [b["id"] for b in api.get(f"{V1}/books").json()] == [d["book_id"]]


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
    edited = _rename_first_chapter(api.get(f"{V1}/drafts/{draft_id}/std.epub").content, "The Dark Night")
    r = api.put(f"{V1}/drafts/{draft_id}/std.epub", files={"file": ("x.std.epub", edited)})
    assert r.status_code == 200, r.text
    assert r.json() == {"chapters": 2}
    d = api.get(f"{V1}/drafts/{draft_id}").json()
    assert d["report"]["chapters"][0][0] == "The Dark Night"
    assert any("edited .std.epub uploaded" in n for n in d["report"]["notes"])
    api.post(f"{V1}/drafts/{draft_id}/approve", json={})
    d = _wait(api, draft_id, "done")
    digest = d["source_sha1"][:8]
    assert d["book_id"].endswith(digest)  # the id comes from the original upload, not the edited file
    m = api.get(f"{V1}/books/{d['book_id']}").json()
    assert m["chapters"][0]["title"] == "The Dark Night"
    bad = api.put(f"{V1}/drafts/{draft_id}/std.epub", files={"file": ("x.epub", b"not a zip")})
    assert bad.status_code == 400


def test_srv23_discard_removes_draft(api, tmp_path):
    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    assert api.delete(f"{V1}/drafts/{draft_id}").json() == {"ok": True}
    assert not (tmp_path / "drafts" / draft_id).exists()
    assert api.get(f"{V1}/drafts/{draft_id}").status_code == 404
    assert api.get(f"{V1}/drafts").json() == []
    assert api.delete(f"{V1}/drafts/{draft_id}").status_code == 404


def test_srv24_bad_ids_and_inputs(api):
    for path in ("/drafts/nope", "/drafts/..%2Flibrary", "/drafts/Nope!/std.epub", "/drafts/abc/chapters/0"):
        assert api.get(V1 + path).status_code == 404, path
    assert api.post(f"{V1}/drafts", files={"file": ("x.docx", b"x")}).status_code == 400
    long_name = "A Very Long Download Name, With (Commas) -- " * 6 + ".TXT"
    draft_id = _upload(api, long_name, STORY.encode())
    saved = service.drafts.get(draft_id)["source"]
    assert saved.endswith(".txt") and len(saved) <= 84 and "," not in saved and "(" not in saved
    assert _wait(api, draft_id, "review", "error")["status"] == "review"
    assert api.post(f"{V1}/drafts", files={"file": ("x.txt", b"x")}, data={"speed": "2.5"}).status_code == 400
    assert api.post(f"{V1}/drafts", files={"file": ("x.txt", b"x")}, data={"voice": "zz"}).status_code == 400


def test_srv28_ocr_mode_reaches_normalize(api, monkeypatch):
    seen = []
    real = service.normalize
    monkeypatch.setattr(service, "normalize", lambda *a, **k: seen.append(k["ocr"]) or real(*a, **k))
    draft_id = _upload(api, "story.txt", STORY.encode(), ocr="always")
    assert _wait(api, draft_id, "review")["ocr"] == "always" and seen == ["always"]
    r = api.post(f"{V1}/drafts", files={"file": ("x.pdf", b"x")}, data={"ocr": "sometimes"})
    assert r.status_code == 400 and "OCR must be one of" in r.json()["detail"]


def test_srv29_upload_cleaned_book_converts_directly(api, tmp_path):
    plain = build_epub(tmp_path / "novel.epub", novel_spec()).read_bytes()
    draft_id = _upload(api, "story.txt", STORY.encode())
    first = _wait(api, draft_id, "review")
    std = api.get(f"{V1}/drafts/{draft_id}/std.epub").content
    r = api.post(f"{V1}/drafts/cleaned", files={"file": ("story.std.epub", std)}, data={"voice": "bf_emma"})
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"draft_id", "job_id"}
    d = _wait(api, r.json()["draft_id"], "done")
    assert d["report"]["method"].startswith("uploaded cleaned book")
    assert d["book_id"].endswith(first["source_sha1"][:8])  # same library id as cleaning the original here
    for name, data in (("plain.epub", plain), ("story.txt", STORY.encode()), ("x.epub", b"not a zip")):
        bad = api.post(f"{V1}/drafts/cleaned", files={"file": (name, data)})
        assert bad.status_code == 400 and "Clean page" in bad.json()["detail"], name
    assert len(api.get(f"{V1}/drafts").json()) == 2  # refused uploads leave no draft behind


def test_srv30_voice_sample_made_once_and_cached(api):
    tts = service.jobs.tts
    r = api.get(f"{V1}/voices/bm_george/sample")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mp4" and len(r.content) > 1000
    assert tts.calls == [("bm_george", service.SAMPLE_TEXT)]
    assert api.get(f"{V1}/voices/bm_george/sample").content == r.content
    assert len(tts.calls) == 1  # the second click is served from the file
    assert api.get(f"{V1}/voices/zz_nobody/sample").status_code == 404


def test_srv31_sample_does_not_change_a_conversions_voice(api):
    tts = service.jobs.tts
    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    api.post(f"{V1}/drafts/{draft_id}/approve", json={"voice": "af_heart"})
    api.get(f"{V1}/voices/bm_george/sample")  # while (or just before) the book converts
    d = _wait(api, draft_id, "done")
    assert api.get(f"{V1}/books/{d['book_id']}").json()["voice"] == "af_heart"
    assert {v for v, text in tts.calls if text != service.SAMPLE_TEXT} == {"af_heart"}
    assert tts.voice == "af_heart"  # the sample passed its own voice instead of setting the model's


def test_srv10_language_refusal_is_a_draft_error(api):
    draft_id = _upload(api, "hu.txt", "\n\n".join([HU] * 8).encode())
    d = _wait(api, draft_id, "error")
    assert "English" in d["error"] or "language" in d["error"].lower()
    assert d["report"] is None
    assert api.post(f"{V1}/drafts/{draft_id}/approve", json={}).status_code == 409


def test_srv25_restart_marks_interrupted_drafts(tmp_path):
    root = tmp_path / "drafts"
    for draft_id, status in (("aaa", "cleaning"), ("bbb", "converting"), ("ccc", "review")):
        (root / draft_id).mkdir(parents=True)
        (root / draft_id / "draft.json").write_text(json.dumps(
            {"id": draft_id, "status": status, "created": 0, "error": None, "message": ""}), encoding="utf-8")
    drafts = service.Drafts(root)
    assert drafts.drafts["aaa"]["status"] == "error" and "restart" in drafts.drafts["aaa"]["error"]
    assert drafts.drafts["bbb"]["status"] == "review" and "approve again" in drafts.drafts["bbb"]["message"]
    assert drafts.drafts["ccc"]["status"] == "review"
    saved = json.loads((root / "aaa" / "draft.json").read_text(encoding="utf-8"))
    assert saved["status"] == "error"
