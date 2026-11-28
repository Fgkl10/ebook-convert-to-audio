"""Measured pitch and pace of every Kokoro voice, for the voice names (D-046).

Kokoro publishes no description of its voices (v1.1-zh's are only numbered), so each voice reads the same sentences
and two things are measured from its audio: the median pitch (F0) of its voiced frames, and how fast it speaks (the
language's syllables per second of speech). Then each voice is ranked against the others it is listed with (the same
model, language and gender for pitch; the same model and language for pace): the lowest third gets "low", the
highest third "high", and the same for "slow"/"fast"; the middle third gets no word. The words are relative: a "low"
woman's voice is low for a woman's voice of that model.

The results are kept in voice_traits.json next to this file, so the app never synthesizes to name a voice.
Regenerate (GPU, a few minutes; v1.1-zh voices only when that model is installed):
    python -m desktop.tts.voice_traits
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

DATA = Path(__file__).with_name("voice_traits.json")
TEXTS = {
    "en": ["The old lighthouse keeper climbed the stairs every evening.",
           "Nobody in the village knew where he had come from, or why he stayed.",
           "One stormy night, a small boat appeared on the horizon."],
    "zh": ["老灯塔看守人每天傍晚都会爬上楼梯。",
           "村里没有人知道他从哪里来，也不知道他为什么留下。",
           "一个暴风雨的夜晚，一条小船出现在海平线上。"],
}
F0_MIN, F0_MAX = 60.0, 500.0


def pitch_hz(audio: np.ndarray, sr: int) -> float:
    """Median F0 over voiced frames. Checked on generated tones (TTS-17)."""
    f0 = pitch_frames(audio, sr)
    return float(np.median(f0)) if f0 else 0.0


def pitch_frames(audio: np.ndarray, sr: int) -> list[float]:
    """F0 of each voiced frame: normalized autocorrelation per 40 ms frame (10 ms hop); a frame is voiced when it is
    loud enough and its best period correlates >= 0.6 with itself."""
    frame, hop = int(0.04 * sr), int(0.01 * sr)
    lo, hi = int(sr / F0_MAX), int(sr / F0_MIN)
    loud = 0.05 * float(np.max(np.abs(audio))) if audio.size else 0.0
    f0 = []
    for start in range(0, len(audio) - frame - hi, hop):
        x = audio[start:start + frame + hi].astype(np.float64)
        x = x - x.mean()
        if np.sqrt(np.mean(x[:frame] ** 2)) < loud:
            continue
        a = x[:frame]
        energy = np.dot(a, a)
        best, best_lag = 0.0, 0
        for lag in range(lo, hi):
            b = x[lag:lag + frame]
            r = np.dot(a, b) / np.sqrt(energy * np.dot(b, b) + 1e-12)
            if r > best:
                best, best_lag = r, lag
        if best >= 0.6:
            # prefer the shortest period that is nearly as good (avoids octave errors at 2x the period)
            for div in (3, 2):
                lag = round(best_lag / div)
                if lag >= lo:
                    b = x[lag:lag + frame]
                    if np.dot(a, b) / np.sqrt(energy * np.dot(b, b) + 1e-12) >= 0.9 * best:
                        best_lag = lag
                        break
            f0.append(sr / best_lag)
    return f0


def speech_seconds(audio: np.ndarray, sr: int) -> float:
    """Time with speech in it: 20 ms frames louder than 2 % of the peak (pauses between words don't count)."""
    frame = int(0.02 * sr)
    if not audio.size:
        return 0.0
    peak = float(np.max(np.abs(audio)))
    frames = audio[: len(audio) // frame * frame].reshape(-1, frame)
    return float(np.sum(np.sqrt(np.mean(frames ** 2, axis=1)) > 0.02 * peak)) * frame / sr


def syllables(text: str, lang: str) -> int:
    if lang == "zh":
        return len(re.findall(r"[一-鿿]", text))
    return sum(max(1, len(re.findall(r"[aeiouy]+", w.lower().rstrip("e")))) for w in re.findall(r"[A-Za-z']+", text))


def label(values: dict[str, float], low: str, high: str) -> dict[str, str]:
    """The lowest third -> low, the highest third -> high, the middle -> nothing (ties keep their order)."""
    ranked = sorted(values, key=lambda v: values[v])
    n = len(ranked)
    third = n // 3
    out = {}
    for i, v in enumerate(ranked):
        if third and i < third:
            out[v] = low
        elif third and i >= n - third:
            out[v] = high
    return out


def traits(measured: dict[str, dict]) -> dict[str, list[str]]:
    """voice -> ["low"|"high"] + ["slow"|"fast"], from {voice: {"group", "gender", "pitch_hz", "rate"}}."""
    words: dict[str, list[str]] = {v: [] for v in measured}
    for key, word in (("pitch", ("low", "high")), ("pace", ("slow", "fast"))):
        groups: dict[tuple, dict[str, float]] = {}
        for v, m in measured.items():
            g = (m["group"], m["gender"]) if key == "pitch" else (m["group"],)
            groups.setdefault(g, {})[v] = m["pitch_hz"] if key == "pitch" else m["rate"]
        for values in groups.values():
            for v, w in label(values, *word).items():
                words[v].append(w)
    return words


_cache: dict | None = None


def load() -> dict[str, list[str]]:
    """voice id -> its trait words; empty when the file is missing."""
    global _cache
    if _cache is None:
        try:
            _cache = {v: m["traits"] for v, m in json.loads(DATA.read_text(encoding="utf-8")).items()}
        except (OSError, ValueError, KeyError):
            _cache = {}
    return _cache


def main() -> None:
    from .kokoro import V10_VOICES, KokoroBackend
    from .models import ZH_VOICES, zh_installed

    k = KokoroBackend()
    sets = [("v1.0", lang, vs) for lang, vs in V10_VOICES.items()]
    if zh_installed():
        sets.append(("v1.1-zh", "zh", ZH_VOICES))
    measured = {}
    for model, lang, voices in sets:
        for voice in voices:
            audio = [k.synth(t, voice, 1.0) for t in TEXTS[lang]]
            pitch = float(np.median([pitch_hz(a, k.sample_rate) for a in audio]))
            speech = sum(speech_seconds(a, k.sample_rate) for a in audio)
            rate = sum(syllables(t, lang) for t in TEXTS[lang]) / speech
            measured[voice] = {"group": f"{model}-{lang}", "gender": voice[1], "pitch_hz": round(pitch, 1),
                               "rate": round(rate, 2)}
            print(f"{voice:12} {pitch:6.1f} Hz {rate:5.2f} syl/s", flush=True)
    for v, words in traits(measured).items():
        measured[v]["traits"] = words
    DATA.write_text(json.dumps(measured, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {DATA}")


if __name__ == "__main__":
    main()
