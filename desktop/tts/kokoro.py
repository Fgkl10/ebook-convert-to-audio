"""Thin wrapper around Kokoro-82M (https://huggingface.co/hexgrad/Kokoro-82M)."""
from __future__ import annotations

import threading

import numpy as np

SAMPLE_RATE = 24000

# A useful subset of Kokoro's English voices. Prefix: a=American, b=British; f/m=female/male.
VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_michael", "am_fenrir", "am_puck", "am_adam",
    "bf_emma", "bf_isabella", "bm_george", "bm_fable", "bm_lewis",
]
DEFAULT_VOICE = "af_heart"
# The languages these voices speak are listed in desktop/core/language.py (SUPPORTED_LANGUAGES).


REPO = "hexgrad/Kokoro-82M"


class KokoroTTS:
    """One Kokoro model on the GPU, with one text pipeline per voice language (a = American, b = British) that
    shares it (D-031). synth() is locked, so a voice sample can be made between two sentences of a conversion."""

    def __init__(self, voice: str = DEFAULT_VOICE, speed: float = 1.0, device: str | None = None):
        import torch
        from kokoro import KModel

        self.voice = voice
        self.speed = speed
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = KModel(repo_id=REPO).to(self.device).eval()
        self.pipelines: dict = {}
        self.lock = threading.Lock()

    def _pipeline(self, voice: str):
        from kokoro import KPipeline

        lang = voice[0] if voice[:1] in ("a", "b") else "a"
        if lang not in self.pipelines:
            self.pipelines[lang] = KPipeline(lang_code=lang, repo_id=REPO, model=self.model, device=self.device)
        return self.pipelines[lang]

    def synth(self, text: str, voice: str | None = None, speed: float | None = None) -> np.ndarray:
        """Return mono float32 audio at SAMPLE_RATE for one sentence (in this voice, or the current one)."""
        voice, speed = voice or self.voice, speed or self.speed
        with self.lock:
            return self._synth(text, voice, speed)

    def _synth(self, text: str, voice: str, speed: float) -> np.ndarray:
        chunks = []
        # split_pattern=None: we already split into sentences; Kokoro still
        # chunks internally if the phoneme sequence is too long.
        for result in self._pipeline(voice)(text, voice=voice, speed=speed, split_pattern=None):
            audio = result.audio
            if audio is None:
                continue
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)
