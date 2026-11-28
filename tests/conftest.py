"""Point the data folder away from the project before anything imports desktop.tts.build (D-032).

desktop/server/service.py loads drafts/ when it is imported. Without this, a test run would read the real drafts/ folder and
rewrite drafts that a running server is converting.
"""
import os
import tempfile

import pytest

os.environ["EBOOK_AUDIO_DATA"] = tempfile.mkdtemp(prefix="ebook-audio-test-")


@pytest.fixture(autouse=True)
def _no_zh_model(monkeypatch):
    """Tests see Kokoro v1.0's voices only, whether or not this PC has v1.1-zh installed (D-044). A test that wants
    it installed patches this back."""
    from desktop.tts import kokoro, models

    monkeypatch.setattr(kokoro, "zh_installed", lambda: False)
    monkeypatch.setattr(models, "zh_installed", lambda: False)
