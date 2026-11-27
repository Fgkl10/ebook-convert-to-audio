"""Thin wrapper around Kokoro-82M (https://huggingface.co/hexgrad/Kokoro-82M)."""
from __future__ import annotations

import numpy as np

SAMPLE_RATE = 24000

# A useful subset of Kokoro's English voices. Prefix: a=American, b=British; f/m=female/male.
VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_michael", "am_fenrir", "am_puck", "am_adam",
    "bf_emma", "bf_isabella", "bm_george", "bm_fable", "bm_lewis",
]
DEFAULT_VOICE = "af_heart"
# Languages the voices above can speak; desktop/language.py refuses books in any other language.
SUPPORTED_LANGUAGES = {"en"}


class KokoroTTS:
    def __init__(self, voice: str = DEFAULT_VOICE, speed: float = 1.0, device: str | None = None):
        import torch
        from kokoro import KPipeline

        self.voice = voice
        self.speed = speed
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        lang_code = voice[0] if voice[:1] in ("a", "b") else "a"
        self.pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M", device=self.device)

    def synth(self, text: str) -> np.ndarray:
        """Return mono float32 audio at SAMPLE_RATE for one sentence."""
        chunks = []
        # split_pattern=None: we already split into sentences; Kokoro still
        # chunks internally if the phoneme sequence is too long.
        for result in self.pipeline(text, voice=self.voice, speed=self.speed, split_pattern=None):
            audio = result.audio
            if audio is None:
                continue
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)
