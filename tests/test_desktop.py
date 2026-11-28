import json
from pathlib import Path

import numpy as np
import pytest

from desktop.core.segment import MAX_CHARS, split_paragraph, split_text
from desktop.tts import build
from desktop.tts.kokoro import SAMPLE_RATE


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


def test_bld12_parse_chapter_spec():
    assert build.parse_chapter_spec("3", 5) == [2]
    assert build.parse_chapter_spec("2-4", 5) == [1, 2, 3]
    assert build.parse_chapter_spec("1, 3,5-5,3", 5) == [0, 2, 4]
    for bad in ("0", "6", "4-2", "x", "1-", ""):
        with pytest.raises(ValueError):
            build.parse_chapter_spec(bad, 5)


def test_bld12_build_selected_chapters_into_separate_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    src = tmp_path / "story.txt"
    src.write_text("Chapter 1\n\nIt was a dark night. The wind howled.\n\n"
                   "Chapter 2\n\nMorning came at last. Everyone was relieved.\n\n"
                   "Chapter 3\n\nThe end came quietly. Nobody noticed at all.\n", encoding="utf-8")
    full = build.build_book(src, tmp_path / "lib", tts=FakeTTS())
    part = build.build_book(src, tmp_path / "lib", tts=FakeTTS(), chapters="2")
    assert part.name == f"{full.name}-ch2"
    m = json.loads((part / "book.json").read_text(encoding="utf-8"))
    assert m["complete"] and m["chapter_selection"] == "2"
    assert [c["title"] for c in m["chapters"]] == ["Chapter 2"]
    full_m = json.loads((full / "book.json").read_text(encoding="utf-8"))
    assert len(full_m["chapters"]) == 3 and full_m["chapter_selection"] is None  # full book untouched
    with pytest.raises(ValueError, match="out of range"):
        build.build_book(src, tmp_path / "lib", tts=FakeTTS(), chapters="4")


# ---------------------------------------------------------------- chosen chapters added to one book (D-035)

FOUR = "".join(f"Chapter {n}\n\nWord {n} came first. Then word {n} again.\n\n" for n in range(1, 5))


def _four(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    src = tmp_path / "four.txt"
    src.write_text(FOUR, encoding="utf-8")
    return src


def _manifest(folder: Path) -> dict:
    return json.loads((folder / "book.json").read_text(encoding="utf-8"))


class CountingTTS(FakeTTS):
    def __init__(self, voice="af_heart", fail_after=None):
        self.voice, self.calls, self.fail_after = voice, [], fail_after

    def synth(self, text):
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise KeyboardInterrupt  # like Ctrl+C in the middle of a chapter
        self.calls.append(text)
        return super().synth(text)


def test_bld16_select_chapters():
    assert build.select_chapters(None, 3) == [0, 1, 2]
    assert build.select_chapters("2-3", 3) == [1, 2]
    assert build.select_chapters([3, 1], 3) == [0, 2]
    for bad in ([], [0], [4], [1, 1], ["1"], [True]):
        with pytest.raises(ValueError):
            build.select_chapters(bad, 3)


def test_bld14_chapters_added_into_one_book(tmp_path, monkeypatch):
    src = _four(tmp_path, monkeypatch)
    lib = tmp_path / "lib"
    out = build.build_book(src, lib, tts=FakeTTS(), chapters=[2], merge=True)
    m = _manifest(out)
    assert out.name == build.make_book_id(build.load_book(src), src)  # the book's own folder, no -ch suffix
    assert [(c["number"], c["audio"], c["index"]) for c in m["chapters"]] == [(2, "ch001.m4a", 0)]
    assert m["complete"] is False and m["chapters_total"] == 4 and m["chapter_selection"] is None
    first = (out / "ch001.m4a").stat().st_mtime_ns
    m["created"] = 123
    (out / "book.json").write_text(json.dumps(m), encoding="utf-8")

    assert build.build_book(src, lib, tts=FakeTTS(), chapters=[4, 1], merge=True) == out
    m = _manifest(out)
    assert [(c["number"], c["audio"], c["index"]) for c in m["chapters"]] == [
        (1, "ch000.m4a", 0), (2, "ch001.m4a", 1), (4, "ch003.m4a", 2)]
    assert m["complete"] is False and m["created"] == 123  # kept: the book doesn't jump to the top of the library
    assert (out / "ch001.m4a").stat().st_mtime_ns == first  # chapter 2 untouched
    assert m["duration_ms"] == sum(c["duration_ms"] for c in m["chapters"])
    assert m["chapters"][0]["text_sha1"] == build.chapter_text_sha1(build.load_book(src).chapters[0].text)

    build.build_book(src, lib, tts=FakeTTS(), chapters=[3], merge=True)
    m = _manifest(out)
    assert [c["number"] for c in m["chapters"]] == [1, 2, 3, 4] and m["complete"] is True
    assert not (tmp_path / "cache" / out.name).exists()  # complete: the sentence cache is removed


def test_bld15_reconvert_one_chapter_in_another_voice(tmp_path, monkeypatch):
    src = _four(tmp_path, monkeypatch)
    lib = tmp_path / "lib"
    out = build.build_book(src, lib, tts=FakeTTS(), chapters=[1, 2], merge=True)
    build.build_book(src, lib, tts=CountingTTS(voice="bf_emma"), chapters=[2], merge=True)
    m = _manifest(out)
    assert [(c["number"], c["voice"]) for c in m["chapters"]] == [(1, "af_heart"), (2, "bf_emma")]
    assert m["voice"] == "bf_emma"  # the latest run


def test_bld16_cli_selection_keeps_original_numbers(tmp_path, monkeypatch):
    src = _four(tmp_path, monkeypatch)
    out = build.build_book(src, tmp_path / "lib", tts=FakeTTS(), chapters="2")
    m = _manifest(out)
    assert out.name.endswith("-ch2") and m["chapter_selection"] == "2"
    assert [(c["number"], c["audio"]) for c in m["chapters"]] == [(2, "ch001.m4a")]
    assert m["complete"] is True and m["chapters_total"] == 1  # a test folder is complete when its selection is


def test_bld17_old_manifest_merges_by_audio_name(tmp_path, monkeypatch):
    """A full book from before D-035: no numbers, no hashes, and chapter 2 was skipped (empty) when it was made."""
    src = _four(tmp_path, monkeypatch)
    out = tmp_path / "lib" / build.make_book_id(build.load_book(src), src)
    out.mkdir(parents=True)
    old = [{"index": i, "title": f"Chapter {n}", "audio": f"ch{n - 1:03d}.m4a", "duration_ms": 1, "sentences": []}
           for i, n in enumerate((1, 3, 4))]
    for c in old:
        (out / c["audio"]).write_bytes(b"old")
    (out / "book.json").write_text(json.dumps({"id": out.name, "title": "Four", "complete": True, "created": 5,
                                               "chapter_selection": None, "chapters": old}), encoding="utf-8")
    assert [build.chapter_number(c, i, {"chapter_selection": None}) for i, c in enumerate(old)] == [1, 3, 4]
    # an old --chapters test folder: the number comes from its spec when it matches the chapters it holds
    assert build.chapter_number(old[0], 0, {"chapter_selection": "4", "chapters": old[:1]}) == 4
    assert build.chapter_number(old[1], 1, {"chapter_selection": "2-4", "chapters": old}) == 3
    assert build.chapter_number(old[1], 1, {"chapter_selection": "2-5", "chapters": old}) == 2  # a skip: position
    assert build.chapter_number(old[1], 1, {"chapter_selection": "bad", "chapters": old}) == 2

    build.build_book(src, tmp_path / "lib", tts=FakeTTS(), chapters=[3], merge=True)
    m = _manifest(out)
    assert [(c["number"], c["audio"]) for c in m["chapters"]] == [(1, "ch000.m4a"), (3, "ch002.m4a"), (4, "ch003.m4a")]
    assert (out / "ch002.m4a").read_bytes() != b"old" and (out / "ch000.m4a").read_bytes() == b"old"
    assert m["complete"] is False and m["created"] == 5  # chapter 2 still missing


def test_bld19_interrupted_cache_write_leaves_no_half_entry(tmp_path, monkeypatch):
    synth = build.CachedSynth(FakeTTS(), tmp_path / "cache")
    entry = synth.path("Hello there.")
    real_save = np.save

    def save_then_ctrl_c(fh, audio):
        fh.write(b"\x93NUMPY half")  # some bytes reach the disk, then Ctrl+C
        raise KeyboardInterrupt

    monkeypatch.setattr(np, "save", save_then_ctrl_c)
    with pytest.raises(KeyboardInterrupt):
        synth("Hello there.")
    assert not entry.exists()  # a resumed run will not load a half-written entry
    assert [f.name for f in (tmp_path / "cache").iterdir()] == [entry.name + ".tmp"]
    assert build.remove_leftovers(tmp_path / "cache") == [entry.with_name(entry.name + ".tmp")]

    monkeypatch.setattr(np, "save", real_save)
    expected = FakeTTS().synth("Hello there.")
    assert np.array_equal(synth("Hello there."), expected) and entry.exists()
    assert np.array_equal(synth("Hello there."), expected)  # now from the cache
    assert [f.name for f in (tmp_path / "cache").iterdir()] == [entry.name]

    entry.write_bytes(b"\x93NUMPY half")  # a cut-off entry from a version before atomic writes
    assert np.array_equal(synth("Hello there."), expected)  # made again instead of breaking the conversion
    assert np.array_equal(np.load(entry), expected)


def test_bld20_chapter_size_and_time_change_when_reconverted(tmp_path, monkeypatch):
    src = _four(tmp_path, monkeypatch)
    out = build.build_book(src, tmp_path / "lib", tts=FakeTTS(), chapters=[1, 2], merge=True)
    first = {c["number"]: c for c in _manifest(out)["chapters"]}
    for c in first.values():
        st = (out / c["audio"]).stat()
        assert c["size_bytes"] == st.st_size > 0 and c["updated_ms"] == st.st_mtime_ns // 1_000_000
    # FakeTTS makes the same length in any voice, so the size alone can't tell; the millisecond time does
    build.build_book(src, tmp_path / "lib", tts=CountingTTS(voice="bf_emma"), chapters=[2], merge=True)
    again = {c["number"]: c for c in _manifest(out)["chapters"]}
    assert again[1] == first[1]  # untouched chapter: same version
    assert again[2]["size_bytes"] == first[2]["size_bytes"] and again[2]["voice"] == "bf_emma"
    assert again[2]["updated_ms"] > first[2]["updated_ms"]


def test_bld21_cancel_stops_between_sentences_and_resumes(tmp_path, monkeypatch):
    import threading
    src = _four(tmp_path, monkeypatch)
    lib, stop = tmp_path / "lib", threading.Event()

    class StopAfter(CountingTTS):
        def synth(self, text):
            audio = super().synth(text)
            if len(self.calls) == 5:  # in chapter 2: chapter 1 (3 sentences) is finished
                stop.set()
            return audio

    with pytest.raises(build.Cancelled):
        build.build_book(src, lib, tts=StopAfter(), merge=True, cancel=stop)
    out = lib / build.make_book_id(build.load_book(src), src)
    assert [c["number"] for c in _manifest(out)["chapters"]] == [1]
    assert not list(out.glob("*.tmp.m4a"))  # stopped between sentences, never inside ffmpeg
    assert len(list((tmp_path / "cache" / out.name).glob("*.npy"))) == 5
    resumed = CountingTTS()
    build.build_book(src, lib, tts=resumed, merge=True, cancel=threading.Event())
    assert "Word 2 came first." not in resumed.calls and len(resumed.calls) == 12 - 5
    assert _manifest(out)["complete"] is True


def test_bld18_interrupted_selection_keeps_its_cache(tmp_path, monkeypatch):
    src = _four(tmp_path, monkeypatch)
    lib = tmp_path / "lib"
    with pytest.raises(KeyboardInterrupt):  # stops after 2 sentences of chapter 3
        build.build_book(src, lib, tts=CountingTTS(fail_after=2), chapters=[3, 4], merge=True)
    out = lib / build.make_book_id(build.load_book(src), src)
    assert not (out / "book.json").exists()

    build.build_book(src, lib, tts=FakeTTS(), chapters=[1], merge=True)  # another selection finishes meanwhile
    assert [c["number"] for c in _manifest(out)["chapters"]] == [1]
    assert len(list((tmp_path / "cache" / out.name).glob("*.npy"))) == 2  # chapter 3's sentences are still there

    resumed = CountingTTS()
    build.build_book(src, lib, tts=resumed, chapters=[3, 4], merge=True)
    assert "Chapter 3" not in resumed.calls and "Word 3 came first." not in resumed.calls
    assert "Then word 3 again." in resumed.calls
    assert [c["number"] for c in _manifest(out)["chapters"]] == [1, 3, 4]
