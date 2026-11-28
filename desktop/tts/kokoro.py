"""Thin wrapper around Kokoro-82M (https://huggingface.co/hexgrad/Kokoro-82M) and, when installed, Kokoro-82M-v1.1-zh."""
from __future__ import annotations

import re
import threading

import numpy as np

from .. import MODELS
from .models import V10_REPO, ZH_REPO, ZH_VOICES, repo_of, zh_installed

SAMPLE_RATE = 24000
REPO = V10_REPO

# Voices by the language they speak (D-043). The voice's first letter is its language: a = American English,
# b = British English, z = Mandarin Chinese; f/m = female/male. The language codes match desktop/core/language.py.
V10_VOICES = {
    "en": ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
           "am_michael", "am_fenrir", "am_puck", "am_adam",
           "bf_emma", "bf_isabella", "bm_george", "bm_fable", "bm_lewis"],
    "zh": ["zf_xiaoxiao", "zf_xiaobei", "zf_xiaoni", "zf_xiaoyi", "zm_yunxi", "zm_yunjian", "zm_yunxia", "zm_yunyang"],
}
LANGUAGES = list(V10_VOICES)
DEFAULT_VOICES = {"en": "af_heart", "zh": "zf_xiaoxiao"}
ZH_DEFAULT_V11 = "zf_001"
DEFAULT_VOICE = DEFAULT_VOICES["en"]


def voice_language(voice: str) -> str | None:
    return {"a": "en", "b": "en", "z": "zh"}.get(voice[:1])


def voices(lang: str | None = None) -> dict[str, list[str]] | list[str]:
    """The voices on offer: v1.0's, except that Chinese uses v1.1-zh's once it is installed (D-044)."""
    out = dict(V10_VOICES)
    if zh_installed():
        out["zh"] = list(ZH_VOICES)
    return out[lang] if lang else out


def all_voices() -> list[str]:
    return [v for vs in voices().values() for v in vs]


def default_voice(lang: str) -> str:
    return ZH_DEFAULT_V11 if lang == "zh" and zh_installed() else DEFAULT_VOICES[lang]


def voice_for(voice: str, lang: str) -> str:
    """The voice to read a book in `lang` with: the chosen one when it speaks that language, else the language's
    default voice (an English voice was picked at upload, and the book turned out Chinese; D-043)."""
    return voice if voice_language(voice) == lang else default_voice(lang)


_t2s = None


def to_simplified(text: str) -> str:
    """Traditional -> Simplified characters, for pronunciation only: jieba's word list is Simplified, and its word
    splits choose the reading of characters with several (行, 了). The text shown on the phone stays as printed."""
    global _t2s
    if _t2s is None:
        import opencc

        _t2s = opencc.OpenCC("t2s")
    return _t2s.convert(text)


class KokoroTTS:
    """One Kokoro model on the GPU, with one text pipeline per voice language that shares it (D-031). Chinese voices
    of v1.1-zh load that second model on first use (D-044). synth() is locked, so a voice sample can be made between
    two sentences of a conversion."""

    def __init__(self, voice: str = DEFAULT_VOICE, speed: float = 1.0, device: str | None = None):
        import torch

        self.voice = voice
        self.speed = speed
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.models: dict = {}
        self.pipelines: dict = {}
        self.lock = threading.Lock()
        self._model(V10_REPO)

    def _model(self, repo: str):
        from kokoro import KModel

        if repo not in self.models:
            self.models[repo] = KModel(repo_id=repo).to(self.device).eval()
        return self.models[repo]

    @property
    def model(self):
        return self.models[V10_REPO]

    def unload(self, repo: str) -> None:
        """Forget a model (and its pipelines), e.g. after v1.1-zh is removed."""
        with self.lock:
            self.models.pop(repo, None)
            for key in [k for k in self.pipelines if k[1] == repo]:
                del self.pipelines[key]

    def _english_phonemes(self, text: str) -> str:
        """Latin words inside Chinese text ('eBay') are read in English, through a pipeline that only does G2P."""
        from kokoro import KPipeline

        key = ("g2p-a", None)
        if key not in self.pipelines:
            self.pipelines[key] = KPipeline(lang_code="a", repo_id=V10_REPO, model=False)
        return next(self.pipelines[key](text)).phonemes

    def _pipeline(self, voice: str):
        from kokoro import KPipeline

        lang = voice[0] if voice[:1] in ("a", "b", "z") else "a"
        repo = repo_of(voice)
        if (lang, repo) not in self.pipelines:
            if lang == "z":
                _jieba_cache_in_project()
            pipeline = KPipeline(lang_code=lang, repo_id=repo, model=self._model(repo), device=self.device,
                                 en_callable=self._english_phonemes if lang == "z" else None)
            if lang == "z" and repo == V10_REPO:
                pipeline.g2p = _v10_zh_g2p(pipeline.g2p, self._english_phonemes)
            self.pipelines[(lang, repo)] = pipeline
        return self.pipelines[(lang, repo)]

    def synth(self, text: str, voice: str | None = None, speed: float | None = None) -> np.ndarray:
        """Return mono float32 audio at SAMPLE_RATE for one sentence (in this voice, or the current one)."""
        voice, speed = voice or self.voice, speed or self.speed
        with self.lock:
            return self._synth(text, voice, speed)

    def _synth(self, text: str, voice: str, speed: float) -> np.ndarray:
        if voice_language(voice) == "zh":
            text = to_simplified(text)
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


_LATIN_OR_NOT = re.compile(r"([A-Za-z '-]*[A-Za-z][A-Za-z '-]*)|([^A-Za-z]+)")  # misaki's own split (zh.py, v1.1)


def _v10_zh_g2p(g2p, english):
    """misaki reads Latin words inside Chinese ('eBay', 'Gamification') in English only for v1.1-zh; for v1.0 it
    passes the letters to the model as if they were phonemes. Do v1.1's split for v1.0 too: Chinese runs through
    v1.0's own G2P, Latin runs through the English one. Left as it is if misaki changes its internals."""
    from misaki import zh

    legacy, punct = getattr(zh.ZHG2P, "legacy_call", None), getattr(zh.ZHG2P, "map_punctuation", None)
    if legacy is None or punct is None:
        return g2p

    def call(text: str):
        import cn2an

        if not text.strip():
            return "", None
        text = punct(cn2an.transform(text, "an2cn"))
        parts = []
        for latin, chinese in _LATIN_OR_NOT.findall(text):
            if chinese.strip():
                parts.append(legacy(chinese.strip()))
            elif latin.strip():
                parts.append(english(latin.strip()))
        return " ".join(p for p in parts if p), None

    return call


def _jieba_cache_in_project() -> None:
    """jieba (Chinese word splitting) writes its ~9 MB dictionary cache to the system temp folder by default; keep it
    with the other model caches inside the project (D-028)."""
    import jieba

    (MODELS / "jieba").mkdir(parents=True, exist_ok=True)
    jieba.dt.tmp_dir = str(MODELS / "jieba")
