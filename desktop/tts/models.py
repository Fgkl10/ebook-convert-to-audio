"""The TTS models: Kokoro v1.0 (always there) and the optional Kokoro v1.1-zh for better Chinese voices (D-044).

v1.1-zh is a second model (~330 MB) the user installs from the web page's Settings, or removes again. It downloads into
the Hugging Face cache inside the project (models/huggingface/, D-028), like v1.0. Its voices are listed here, so the
voice list never needs the network; each voice file (~0.5 MB) downloads on first use, as with v1.0.
"""
from __future__ import annotations

import shutil
import threading
from pathlib import Path

V10_REPO = "hexgrad/Kokoro-82M"
ZH_REPO = "hexgrad/Kokoro-82M-v1.1-zh"
ZH_FILES = ("config.json", "kokoro-v1_1-zh.pth")
ZH_SIZE = 327_247_856  # bytes of kokoro-v1_1-zh.pth, for the progress line

_ZH_NUMBERS_F = ("001 002 003 004 005 006 007 008 017 018 019 021 022 023 024 026 027 028 032 036 038 039 040 042 043 "
                 "044 046 047 048 049 051 059 060 067 070 071 072 073 074 075 076 077 078 079 083 084 085 086 087 088 "
                 "090 092 093 094 099")
_ZH_NUMBERS_M = ("009 010 011 012 013 014 015 016 020 025 029 030 031 033 034 035 037 041 045 050 052 053 054 055 056 "
                 "057 058 061 062 063 064 065 066 068 069 080 081 082 089 091 095 096 097 098 100")
ZH_VOICES = [f"zf_{n}" for n in _ZH_NUMBERS_F.split()] + [f"zm_{n}" for n in _ZH_NUMBERS_M.split()]


def repo_of(voice: str) -> str:
    """The model a voice belongs to: v1.1-zh voices are numbered (zf_001), v1.0 voices are named (zf_xiaoxiao)."""
    return ZH_REPO if voice in ZH_VOICES else V10_REPO


def _repo_dir(repo: str) -> Path:
    import os

    # The hub's own layout: $HF_HOME/hub/models--<org>--<name> (HF_HOME is set by desktop/__init__.py, D-028).
    return Path(os.environ["HF_HOME"]) / "hub" / ("models--" + repo.replace("/", "--"))


def zh_installed() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:  # CI installs no TTS packages (D-013)
        return False
    return all(isinstance(try_to_load_from_cache(ZH_REPO, f), str) for f in ZH_FILES)


class ZhModel:
    """Install / remove Kokoro v1.1-zh, one install at a time, in a background thread."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.installing = False
        self.error: str | None = None

    def status(self) -> dict:
        done = 0
        if self.installing:  # the .pth is the bulk: count what has arrived so far (*.incomplete while downloading)
            blobs = _repo_dir(ZH_REPO) / "blobs"
            done = sum(f.stat().st_size for f in blobs.glob("*") if f.is_file()) if blobs.exists() else 0
        return {"id": "kokoro-v1.1-zh", "installed": not self.installing and zh_installed(),
                "installing": self.installing, "done_bytes": min(done, ZH_SIZE), "total_bytes": ZH_SIZE,
                "error": self.error}

    def install(self) -> bool:
        """Start the download. False when it is already installed or installing."""
        with self.lock:
            if self.installing or zh_installed():
                return False
            self.installing, self.error = True, None
        threading.Thread(target=self._download, daemon=True).start()
        return True

    def _download(self) -> None:
        from huggingface_hub import hf_hub_download

        try:
            for f in ZH_FILES:
                hf_hub_download(ZH_REPO, f)
        except Exception as e:  # noqa: BLE001 - shown on the Settings page
            self.error = f"Download failed: {e}"
        finally:
            self.installing = False

    def remove(self) -> None:
        with self.lock:
            if self.installing:
                raise RuntimeError("The model is still downloading")
            shutil.rmtree(_repo_dir(ZH_REPO), ignore_errors=True)
            self.error = None
