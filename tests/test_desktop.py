import json
from pathlib import Path

import numpy as np

from desktop import build
from desktop.segment import MAX_CHARS, split_paragraph, split_text
from desktop.tts import SAMPLE_RATE


def test_abbreviations_and_quotes():
    s = split_paragraph('Mr. Smith went to Washington. "Is it far?" she asked. He said... no.')
    assert s[0] == "Mr. Smith went to Washington."
    assert s[1] == '"Is it far?" she asked.'
    assert len(s) == 3


def test_punctuation_only_attached_not_spoken_alone():
    s = split_paragraph("The end. * * *")
    assert all(any(c.isalnum() for c in x) for x in s)


def test_long_sentence_split():
    long = ", ".join(["the quick brown fox jumps over the lazy dog"] * 30) + "."
    parts = split_paragraph(long)
    assert len(parts) > 1 and all(len(p) <= MAX_CHARS for p in parts)
    assert " ".join(parts).replace("  ", " ") == long


def test_paragraphs():
    assert split_text("One. Two.\n\nThree.") == [["One.", "Two."], ["Three."]]


class FakeTTS:
    voice, speed = "af_heart", 1.0

    def synth(self, text):  # 10 ms of audio per character
        return np.full(len(text) * SAMPLE_RATE // 100, 0.1, dtype=np.float32)


def test_timestamps_cover_audio_exactly():
    paras = [["Hello there.", "General."], ["New paragraph here."]]
    audio, sents = build.assemble_chapter(paras, FakeTTS().synth)
    total_ms = round(len(audio) * 1000 / SAMPLE_RATE)
    assert sents[0]["start_ms"] == build.CHAPTER_LEAD_S * 1000
    assert sents[-1]["end_ms"] == total_ms
    for a, b in zip(sents, sents[1:]):
        assert a["end_ms"] == b["start_ms"]
    # second sentence starts after first audio + sentence gap
    assert sents[1]["start_ms"] == 300 + len("Hello there.") * 10 + 250
    assert [s["p"] for s in sents] == [0, 0, 1]


def test_build_txt_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    src = tmp_path / "story.txt"
    src.write_text("Chapter 1\n\nIt was a dark night. The wind howled loudly.\n\n"
                   "Chapter 2\n\nMorning came at last. Everyone was relieved.\n", encoding="utf-8")
    out = build.build_book(src, tmp_path / "lib", tts=FakeTTS())
    m = json.loads((out / "book.json").read_text(encoding="utf-8"))
    assert m["complete"] and len(m["chapters"]) == 2
    assert m["chapters"][0]["sentences"][0]["text"] == "Chapter 1"
    for ch in m["chapters"]:
        assert (out / ch["audio"]).stat().st_size > 0
        assert ch["sentences"][-1]["end_ms"] == ch["duration_ms"]
