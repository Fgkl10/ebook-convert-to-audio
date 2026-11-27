"""EPUB parser tests on synthetic books (tests/epub_factory.py). IDs refer to desktop/docs/test-cases.md."""
import json
import warnings

import pytest

from desktop import build
from desktop.parse import load_book
from tests.epub_factory import JPG_BYTES, PNG_BYTES, build_epub, empty_spec, novel_spec, untitled_spec
from tests.test_desktop import FakeTTS

FRONT_MATTER = {"Half Title", "Copyright", "Contents"}


@pytest.fixture
def novel(tmp_path):
    return build_epub(tmp_path / "novel.epub", novel_spec())


@pytest.fixture
def untitled(tmp_path):
    return build_epub(tmp_path / "untitled.epub", untitled_spec())


def body_chapters(book):
    return [c for c in book.chapters if c.title not in FRONT_MATTER]


def test_par05_metadata_spine_order_and_toc_titles(novel):
    book = load_book(novel)
    assert book.title == "The Quiet Mill"
    assert book.author == "Ada Fictional"
    # Nested (Section, [Link...]) TOC with hrefs under Text/ still maps to every chapter.
    assert [c.title for c in body_chapters(book)] == ["1 The River", "2 The Mill", "3 The Storm"]
    assert body_chapters(book)[0].text.startswith("One\nThe river remembered")


def test_par06_title_fallbacks_without_toc(untitled):
    book = load_book(untitled)
    assert [c.title for c in book.chapters] == ["Opening Heading", "Section 2"]


def test_par07_footnote_markers_removed(novel):
    text = "\n".join(c.text for c in load_book(novel).chapters)
    assert "everything that had ever fallen" in text
    assert "everything1" not in text and "everything 1" not in text
    assert "Thunder rolled over" in text  # bare-digit <sup>2</sup> removed too


def test_par08_cover_from_cover_item(novel):
    book = load_book(novel)
    assert book.cover == JPG_BYTES and book.cover_ext == ".jpg"


def test_par08_cover_from_image_named_cover(untitled):
    book = load_book(untitled)
    assert book.cover == PNG_BYTES and book.cover_ext == ".png"


def test_par13_epub_without_text_raises(tmp_path):
    with pytest.raises(ValueError, match="No readable text"):
        load_book(build_epub(tmp_path / "empty.epub", empty_spec()))


def test_par14_short_pages_dropped(novel, untitled):
    assert "Half Title" not in [c.title for c in load_book(novel).chapters]
    assert len(load_book(untitled).chapters) == 2  # "Tiny." page removed


@pytest.mark.xfail(strict=True, reason="PAR-15 gap: front matter is read aloud as chapters")
def test_par15_front_matter_not_spoken(novel):
    titles = [c.title for c in load_book(novel).chapters]
    assert not FRONT_MATTER & set(titles)


@pytest.mark.xfail(strict=True, reason="PAR-16 gap: XHTML parsed with the HTML parser warns per chapter")
def test_par16_no_xml_parser_warning(novel):
    from bs4 import XMLParsedAsHTMLWarning

    with warnings.catch_warnings():
        warnings.simplefilter("error", XMLParsedAsHTMLWarning)
        load_book(novel)


def test_bld09_epub_build_writes_cover_and_toc_titles(novel, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    out = build.build_book(novel, tmp_path / "lib", tts=FakeTTS())
    m = json.loads((out / "book.json").read_text(encoding="utf-8"))
    assert m["complete"] and m["title"] == "The Quiet Mill"
    assert m["cover"] == "cover.jpg" and (out / "cover.jpg").read_bytes() == JPG_BYTES
    assert [c["title"] for c in m["chapters"]][-3:] == ["1 The River", "2 The Mill", "3 The Storm"]
