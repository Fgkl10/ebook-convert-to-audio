"""The TTS backend interface and the setting that picks one (D-045). IDs: TTS-1x in desktop/docs/test-cases.md."""
import hashlib

import pytest

from desktop.core.language import SUPPORTED_LANGUAGES
from desktop.tts import backend, build
from desktop.tts.kokoro import KokoroBackend


def test_tts10_kokoro_cache_key_unchanged(tmp_path):
    """Sentences cached before D-045 must still hit: Kokoro's key is exactly the old "voice|speed|text"."""
    k = KokoroBackend()
    assert k.cache_key("af_heart", 1.0, "It was a dark night.") == "af_heart|1.0|It was a dark night."
    path = build.CachedSynth(k, "af_heart", 1.0, tmp_path).path("It was a dark night.")
    assert path.name == hashlib.sha1(b"af_heart|1.0|It was a dark night.").hexdigest() + ".npy"
    assert backend.Backend.cache_key(k, "af_heart", 1.0, "x") == "kokoro|af_heart|1.0|x"  # other engines: prefixed


def test_tts11_every_backend_speaks_only_known_languages():
    for name in backend.BACKENDS:
        b = backend.create(name)
        assert set(b.languages()) <= SUPPORTED_LANGUAGES, name
        for lang in b.languages():
            assert b.default_voice(lang) in b.voice_ids(lang)
            assert all(v.language == lang for v in b.voices(lang))
        assert len(set(b.voice_ids())) == len(b.voice_ids())  # ids are unique


def test_tts12_kokoro_voices_from_their_ids(monkeypatch):
    k = KokoroBackend()
    heart, george, xiao = k.voice("af_heart"), k.voice("bm_george"), k.voice("zf_xiaoxiao")
    assert (heart.language, heart.gender, heart.accent, heart.name) == ("en", "female", "us", "Heart")
    assert (george.language, george.gender, george.accent, george.name) == ("en", "male", "gb", "George")
    assert (xiao.language, xiao.gender, xiao.accent, xiao.name) == ("zh", "female", None, "Xiaoxiao")
    from desktop.tts import kokoro

    monkeypatch.setattr(kokoro, "zh_installed", lambda: True)
    v = k.voice("zm_012")
    assert (v.gender, v.name, v.number) == ("male", None, 12)
    assert k.voice("zf_xiaoxiao") is None and k.voice_language("zf_xiaoxiao") == "zh"  # still readable by id


def test_tts13_unknown_backend_refused(tmp_path):
    with pytest.raises(ValueError, match="choose one of kokoro"):
        backend.create("nope")
