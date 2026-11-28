"""The TTS backend interface (D-045): text + voice -> audio, the voices on offer, the languages they speak.

Kokoro (kokoro.py) is the only backend. The rest of the app goes through this interface, so another engine can be
added later as one more entry in BACKENDS. Nothing heavy is imported here: listing voices never loads a model (CI has
no torch), and a backend loads its model on the first synth().
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

DEFAULT_BACKEND = "kokoro"
SETTINGS_FILE = "settings.json"  # in the data folder, next to library/ (written by the server's page)
ENV = "EBOOK_AUDIO_TTS"


@dataclass(frozen=True)
class Voice:
    """One voice. `language` uses core/language.py's codes ("en", "zh"). `name` is the voice's own name ("Heart"),
    None for a numbered voice. `traits` are measured words ("low"/"high" pitch, "slow"/"fast" pace) that tell voices
    of the same language and gender apart (D-046)."""

    id: str
    language: str
    gender: str  # "female" | "male"
    accent: str | None = None  # "us" | "gb", for English
    name: str | None = None
    number: int | None = None
    traits: tuple[str, ...] = field(default=())

    def public(self) -> dict:
        return {"id": self.id, "gender": self.gender, "accent": self.accent, "name": self.name,
                "number": self.number, "traits": list(self.traits)}


class Backend:
    """A speech engine. Subclasses set `id`, `name`, `sample_rate` and implement the four methods marked below.
    synth() is called from the conversion worker and from voice samples at the same time, so it must be safe to call
    from two threads (Kokoro takes a lock)."""

    id = ""
    name = ""
    sample_rate = 24000

    def languages(self) -> list[str]:  # implement: the languages its voices speak (a subset of core's)
        raise NotImplementedError

    def voices(self, lang: str | None = None) -> list[Voice]:  # implement: every voice, or one language's
        raise NotImplementedError

    def default_voice(self, lang: str) -> str:  # implement
        raise NotImplementedError

    def synth(self, text: str, voice: str, speed: float = 1.0) -> np.ndarray:  # implement
        """Mono float32 audio at `sample_rate` for one sentence."""
        raise NotImplementedError

    def unload(self) -> None:
        """Free the model (another backend was picked). The next synth() loads it again."""

    def cache_key(self, voice: str, speed: float, text: str) -> str:
        """The text the sentence cache is keyed on (sha1 of it). Includes the backend, so two engines never share
        audio; Kokoro keeps its key from before backends existed, so old caches stay valid."""
        return f"{self.id}|{voice}|{speed}|{text}"

    # ---- shared helpers, built on the methods above

    def voice_ids(self, lang: str | None = None) -> list[str]:
        return [v.id for v in self.voices(lang)]

    def voice(self, voice_id: str) -> Voice | None:
        return next((v for v in self.voices() if v.id == voice_id), None)

    def voice_language(self, voice_id: str) -> str | None:
        v = self.voice(voice_id)
        return v.language if v else None

    def voice_for(self, voice_id: str, lang: str) -> str:
        """The voice to read a book in `lang` with: the chosen one when it speaks that language, else the language's
        default (an English voice was picked at upload and the book turned out Chinese, D-043)."""
        return voice_id if self.voice_language(voice_id) == lang else self.default_voice(lang)


def _kokoro() -> Backend:
    from .kokoro import KokoroBackend

    return KokoroBackend()


# name -> factory. Creating a backend is cheap: its model loads on the first synth().
BACKENDS: dict[str, Callable[[], Backend]] = {"kokoro": _kokoro}
NAMES = {"kokoro": "Kokoro-82M"}  # shown in the page's dropdown


def check_name(name: str) -> None:
    if name not in BACKENDS:
        raise ValueError(f"Unknown TTS backend {name!r}: choose one of {', '.join(BACKENDS)}")


def create(name: str) -> Backend:
    check_name(name)
    return BACKENDS[name]()


def chosen(root: Path, cli: str | None = None) -> tuple[str, str | None]:
    """The backend to use, and what fixed it: --tts on the command line, then EBOOK_AUDIO_TTS, then the choice saved
    from the page (<data>/settings.json), then Kokoro. The second value is "--tts" / "EBOOK_AUDIO_TTS" when one of
    those set it (the page can't change it then), else None. An unknown name raises ValueError."""
    for name, source in ((cli, "--tts"), (os.environ.get(ENV), ENV)):
        if name:
            check_name(name)
            return name, source
    saved = read_settings(root).get("tts")
    return (saved if saved in BACKENDS else DEFAULT_BACKEND), None


_settings_lock = threading.Lock()


def read_settings(root: Path) -> dict:
    try:
        data = json.loads((root / SETTINGS_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_setting(root: Path, key: str, value) -> None:
    with _settings_lock:
        data = {**read_settings(root), key: value}
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / (SETTINGS_FILE + ".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, root / SETTINGS_FILE)
