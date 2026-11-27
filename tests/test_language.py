"""Language check (desktop/language.py, D-018). All non-English text here is written for these tests."""
import pytest

from desktop import build
from desktop.language import MIN_WORDS, check_language, english_score
from desktop.parse import Book, Chapter, load_book
from tests.epub_factory import build_epub, novel_spec

EN = ("The river ran quietly past the old mill while the morning light grew warmer. The old miller got up "
      "early every day to look at the wheels, and he said that the water remembers everything that has ever "
      "fallen into it. ")
HU = ("A kis malom mellett csendesen folyt a folyó, és a reggeli fény lassan melegebb lett. Az öreg molnár "
      "minden nap korán kelt, hogy megnézze a kerekeket. Azt mondta, a víz mindig emlékszik arra, ami "
      "beleesett. ")
DE = ("Der Fluss floss ruhig an der alten Mühle vorbei, während das Morgenlicht wärmer wurde. Der alte Müller "
      "stand jeden Tag früh auf, um nach den Rädern zu sehen, und er sagte, das Wasser erinnert sich an alles. ")


def book(text, chapters=3, language=""):
    return Book("T", "A", [Chapter(f"C{i}", text) for i in range(chapters)], language=language)


def test_lang01_english_accepted():
    check_language(book(EN * 6))


@pytest.mark.parametrize("text", [HU, DE])
def test_lang02_non_english_refused(text):
    with pytest.raises(ValueError, match="doesn't look like English"):
        check_language(book(text * 6, language="hu"))


def test_lang02_message_mentions_metadata_and_voices():
    with pytest.raises(ValueError, match=r"metadata says language 'hu'.*can only speak: en"):
        check_language(book(HU * 6, language="hu"))


def test_lang03_too_short_to_judge_is_accepted():
    short = book(HU, chapters=1)
    assert english_score(short)[1] < MIN_WORDS
    check_language(short)


def test_lang04_text_wins_over_wrong_metadata(tmp_path):
    spec = novel_spec()
    spec.language = "hu"  # wrong metadata, English text
    b = load_book(build_epub(tmp_path / "novel.epub", spec))
    assert b.language == "hu"
    check_language(b)


class ExplodingTTS:
    voice, speed = "af_heart", 1.0

    def synth(self, text):
        raise AssertionError("TTS must not run for a refused book")


def test_lang05_build_refuses_before_tts(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    src = tmp_path / "hu.txt"
    src.write_text("\n\n".join([HU] * 8), encoding="utf-8")
    with pytest.raises(ValueError, match="doesn't look like English"):
        build.build_book(src, tmp_path / "lib", tts=ExplodingTTS())
    assert not (tmp_path / "lib").exists()  # nothing written


def test_lang07_ignore_language_overrides(tmp_path, monkeypatch):
    from tests.test_desktop import FakeTTS

    monkeypatch.setattr(build, "ROOT", tmp_path)
    src = tmp_path / "hu.txt"
    src.write_text("\n\n".join([HU] * 8), encoding="utf-8")
    out = build.build_book(src, tmp_path / "lib", tts=FakeTTS(), ignore_language=True)
    assert (out / "book.json").exists()
