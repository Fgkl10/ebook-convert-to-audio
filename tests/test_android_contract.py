"""The Android app's view of the API (android/docs/test-cases.md, AND-01).

The app's unit tests decode JSON fixtures in android/app/src/test/resources/api/. This test makes the same responses
from the real server (a made-up story, converted with the fake TTS) and fails if their shape no longer matches the
fixtures: a renamed or removed field, or a changed type. Then the app's models need updating too.

To rewrite the fixtures after a deliberate API change: set UPDATE_ANDROID_FIXTURES=1 and run this test.
"""
import json
import os
import re
from pathlib import Path

from tests.test_api import _approve
from tests.test_server import STORY, V1, _upload, _wait, api  # noqa: F401 - api is a fixture

FIXTURES = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "test" / "resources" / "api"
TOKEN = "T" * 32  # stands in for the test server's random token


def _scrub_field(key, value, token):
    if key == "qr_svg" and value:
        return "<svg/>"
    if key == "source" and isinstance(value, str):  # a report's source is a path on the PC: keep the file name
        return re.split(r"[\\/]", value)[-1]
    return _scrub(value, token)


def _scrub(value, token):
    """No real token, QR drawing or PC path in a committed file."""
    if isinstance(value, dict):
        return {k: _scrub_field(k, v, token) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, token) for v in value]
    if isinstance(value, str):
        return value.replace(token, TOKEN)
    return value


def _kind(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    return type(v).__name__


def _same_shape(fixture, live, path="$"):
    """Same keys at every level and compatible types where both have a value. Returns a list of differences."""
    if _kind(fixture) is None or _kind(live) is None:
        return []
    if _kind(fixture) != _kind(live):
        return [f"{path}: {_kind(fixture)} in the fixture, {_kind(live)} from the server"]
    if isinstance(fixture, dict):
        diffs = [f"{path}.{k}: only in the fixture" for k in fixture.keys() - live.keys()]
        diffs += [f"{path}.{k}: only from the server" for k in live.keys() - fixture.keys()]
        for k in fixture.keys() & live.keys():
            diffs += _same_shape(fixture[k], live[k], f"{path}.{k}")
        return diffs
    if isinstance(fixture, list) and fixture and live:
        return _same_shape(fixture[0], live[0], f"{path}[0]")
    return []


def test_and01_android_fixtures_match_the_server(api, monkeypatch):  # noqa: F811
    from desktop.server import api as api_module
    from desktop.server import auth, network

    # made-up PC: no real host name or addresses in a committed file (documentation-range IPs)
    monkeypatch.setattr(api_module.socket, "gethostname", lambda: "my-pc")
    monkeypatch.setattr(network, "phone_addresses", lambda override=None: [
        {"address": "192.0.2.10", "adapter": "Wi-Fi"}, {"address": "198.51.100.7", "adapter": "ZeroTier Virtual Port"}])

    draft_id = _upload(api, "story.txt", STORY.encode())
    _wait(api, draft_id, "review")
    book_id = _approve(api, draft_id)["book_id"]
    live = {
        "info.json": api.get(f"{V1}/info").json(),
        "books.json": api.get(f"{V1}/books").json(),
        "book.json": api.get(f"{V1}/books/{book_id}").json(),
        # the Convert tab (M4b)
        "drafts.json": api.get(f"{V1}/drafts").json(),
        "draft.json": api.get(f"{V1}/drafts/{draft_id}").json(),
        "draft_chapter.json": api.get(f"{V1}/drafts/{draft_id}/chapters/0").json(),
        "jobs.json": api.get(f"{V1}/jobs").json(),
    }
    live = {name: _scrub(body, auth.token()) for name, body in live.items()}
    if os.environ.get("UPDATE_ANDROID_FIXTURES") == "1":
        FIXTURES.mkdir(parents=True, exist_ok=True)
        for name, body in live.items():
            (FIXTURES / name).write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, body in live.items():
        fixture = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        diffs = _same_shape(fixture, body)
        assert not diffs, f"{name} changed shape (update the app's models, then the fixtures): {diffs}"
    assert TOKEN not in json.dumps(live) or auth.token() != TOKEN  # the scrub ran


def _num(pattern, text):
    m = re.search(pattern, text)
    assert m, pattern
    return float(m.group(1).replace("_", ""))


def test_and11_web_reader_and_app_share_the_reading_rules():
    """M5: the web reader and the app agree on the sentence buttons and the text size range (A-015)."""
    root = Path(__file__).resolve().parent.parent
    js = (root / "desktop" / "web" / "app.js").read_text(encoding="utf-8")
    html = (root / "desktop" / "web" / "index.html").read_text(encoding="utf-8")
    src = root / "android" / "app" / "src" / "main" / "java" / "app" / "ebookaudio"
    sync = (src / "player" / "SentenceSync.kt").read_text(encoding="utf-8")
    settings = (src / "settings" / "Settings.kt").read_text(encoding="utf-8")

    assert _num(r"const RESTART_MS = ([\d_]+)", js) == _num(r"const val RESTART_MS = ([\d_]+)L", sync)
    for key, kotlin in (("min", "TEXT_SIZE_MIN"), ("max", "TEXT_SIZE_MAX"), ("step", "TEXT_SIZE_STEP"),
                        ("def", "TEXT_SIZE_DEFAULT")):
        assert _num(rf"\b{key}: (\d+)", js) == _num(rf"const val {kotlin} = ([\d.]+)f", settings), key
    for button in ("prevs", "nexts", "smaller", "larger"):
        assert f'id="{button}"' in html and f"$('#{button}').onclick" in js, button
    assert "var(--text-size" in (root / "desktop" / "web" / "app.css").read_text(encoding="utf-8")
