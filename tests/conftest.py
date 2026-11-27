"""Point the data folder away from the project before anything imports desktop.build (D-032).

desktop/service.py loads drafts/ when it is imported. Without this, a test run would read the real drafts/ folder and
rewrite drafts that a running server is converting.
"""
import os
import tempfile

os.environ["EBOOK_AUDIO_DATA"] = tempfile.mkdtemp(prefix="ebook-audio-test-")
