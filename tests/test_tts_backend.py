"""The TTS backend interface and the setting that picks one (D-045). IDs: TTS-1x in desktop/docs/test-cases.md."""
import hashlib

import numpy as np
import pytest

from desktop.core.language import SUPPORTED_LANGUAGES
from desktop.server import service
from desktop.tts import backend, build, voice_traits
from desktop.tts.kokoro import KokoroBackend
from tests.test_api import _approve
from tests.test_server import STORY, V1, _upload, _wait, api  # noqa: F401 - api is a fixture


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


# ---------------------------------------------------------------- voice names (D-046)

def test_tts17_pitch_and_pace_measures():
    sr = 24000
    t = np.arange(int(1.5 * sr)) / sr
    for f in (90, 180, 300):  # a voice-like tone: harmonics, a little vibrato, a pause
        phase = 2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * 5 * t)
        x = sum(np.sin(k * phase) / k for k in range(1, 6)).astype(np.float32)
        x[int(0.6 * sr):int(0.8 * sr)] = 0
        assert abs(voice_traits.pitch_hz(x, sr) - f) < 0.02 * f
        assert abs(voice_traits.speech_seconds(x, sr) - 1.3) < 0.03  # the pause doesn't count
    weak = (0.3 * np.sin(2 * np.pi * 110 * t) + np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 330 * t))
    assert abs(voice_traits.pitch_hz(weak.astype(np.float32), sr) - 110) < 3  # no octave error
    assert voice_traits.syllables("老灯塔看守人。", "zh") == 6 and voice_traits.syllables("The old keeper.", "en") == 4


def test_tts18_traits_are_relative_thirds():
    m = {v: {"group": "g", "gender": "f", "pitch_hz": p, "rate": r}
         for v, p, r in [("a", 100, 5), ("b", 150, 6), ("c", 200, 7), ("d", 250, 8), ("e", 300, 9), ("f", 350, 4)]}
    m["x"] = {"group": "g", "gender": "m", "pitch_hz": 100, "rate": 6.5}  # alone in its pitch group: no pitch word
    words = voice_traits.traits(m)
    # pitch: women a-f in thirds (a, b low; e, f high). Pace: all 7 voices (f, a slow; d, e fast)
    assert words == {"a": ["low", "slow"], "b": ["low"], "c": [], "d": ["fast"], "e": ["high", "fast"],
                     "f": ["high", "slow"], "x": []}


def test_tts19_every_kokoro_voice_is_measured(monkeypatch):
    from desktop.tts import kokoro, models

    data = voice_traits.load()
    for v in [*kokoro.V10_VOICES["en"], *kokoro.V10_VOICES["zh"], *models.ZH_VOICES]:
        assert v in data and set(data[v]) <= {"low", "high", "slow", "fast"}, v
    assert KokoroBackend().voice("af_nicole").traits == ("low", "slow")


def test_tts20_info_names_every_voice(api):  # noqa: F811
    for lang in api.get(f"{V1}/info").json()["languages"]:
        assert [d["id"] for d in lang["voice_details"]] == lang["voices"]
    en = api.get(f"{V1}/info").json()["languages"][0]["voice_details"]
    assert {"id": "af_nicole", "gender": "female", "accent": "us", "name": "Nicole", "number": None,
            "traits": ["low", "slow"]} in en


# ---------------------------------------------------------------- the setting (D-045)

class OtherTTS(backend.Backend):
    """A second engine for the tests only: one English voice, a flat tone."""

    id, name, sample_rate = "other", "Other TTS", 16000

    def __init__(self):
        self.unloaded = False

    def languages(self):
        return ["en"]

    def voices(self, lang=None):
        return [backend.Voice("ox_one", "en", "female")] if lang in (None, "en") else []

    def default_voice(self, lang):
        return "ox_one"

    def synth(self, text, voice, speed=1.0):
        return np.full(len(text) * self.sample_rate // 100, 0.1, dtype=np.float32)

    def unload(self):
        self.unloaded = True


@pytest.fixture
def other(monkeypatch):
    monkeypatch.setitem(backend.BACKENDS, "other", OtherTTS)
    monkeypatch.setitem(backend.NAMES, "other", "Other TTS")
    monkeypatch.delenv(backend.ENV, raising=False)


def test_tts14_which_backend(tmp_path, monkeypatch, other):
    monkeypatch.delenv(backend.ENV, raising=False)
    assert backend.chosen(tmp_path) == ("kokoro", None)  # nothing set
    backend.save_setting(tmp_path, "tts", "other")
    assert backend.chosen(tmp_path) == ("other", None)  # picked on the page
    monkeypatch.setenv(backend.ENV, "kokoro")
    assert backend.chosen(tmp_path) == ("kokoro", "EBOOK_AUDIO_TTS")
    assert backend.chosen(tmp_path, "other") == ("other", "--tts")  # the command line wins
    monkeypatch.setenv(backend.ENV, "nope")
    with pytest.raises(ValueError, match="Unknown TTS backend 'nope'"):
        backend.chosen(tmp_path)
    monkeypatch.delenv(backend.ENV)
    backend.save_setting(tmp_path, "tts", "gone")  # a backend that was removed from the code: back to Kokoro
    assert backend.chosen(tmp_path) == ("kokoro", None)


def test_tts15_switch_backend_on_the_page(api, other, monkeypatch):  # noqa: F811
    old, freed = service.jobs.tts, []
    monkeypatch.setattr(old, "unload", lambda repo=None: freed.append(repo), raising=False)
    s = api.get(f"{V1}/settings/tts").json()
    assert s == {"backend": "kokoro", "fixed_by": None,
                 "backends": [{"id": "kokoro", "name": "Kokoro-82M"}, {"id": "other", "name": "Other TTS"}]}
    draft_id = _upload(api, "story.txt", STORY.encode())  # af_heart, picked with Kokoro
    _wait(api, draft_id, "review")

    service.jobs.jobs["x"] = {"status": "running", "voice": "af_heart"}
    r = api.put(f"{V1}/settings/tts", json={"backend": "other"})
    assert r.status_code == 409 and "queued or running" in r.json()["detail"]
    del service.jobs.jobs["x"]
    assert api.put(f"{V1}/settings/tts", json={"backend": "nope"}).status_code == 400

    r = api.put(f"{V1}/settings/tts", json={"backend": "other"})
    assert r.status_code == 200 and r.json()["backend"] == "other"
    assert backend.read_settings(build.ROOT) == {"tts": "other"}  # kept for the next start
    info = api.get(f"{V1}/info").json()
    assert info["voices"] == ["ox_one"] and [lang["code"] for lang in info["languages"]] == ["en"]
    assert api.get(f"{V1}/voices/af_heart/sample").status_code == 404
    d = _approve(api, draft_id)  # the draft's Kokoro voice gives way to the new backend's default
    book = api.get(f"{V1}/books/{d['book_id']}").json()
    assert book["voice"] == "ox_one" and book["chapters"][0]["duration_ms"] > 0
    assert freed == [None]  # the whole Kokoro model was freed


def test_tts16_backend_fixed_at_start(api, other, monkeypatch):  # noqa: F811
    monkeypatch.setattr(service, "CLI_TTS", "kokoro")
    service.jobs.tts = None  # made again from the setting, as at server start
    assert api.get(f"{V1}/settings/tts").json()["fixed_by"] == "--tts"
    r = api.put(f"{V1}/settings/tts", json={"backend": "other"})
    assert r.status_code == 409 and "--tts" in r.json()["detail"]
    with pytest.raises(ValueError, match="Unknown TTS backend"):
        service.configure_tts("nope")
