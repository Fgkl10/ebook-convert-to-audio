"""EPUB parser tests on synthetic books (tests/epub_factory.py). IDs refer to desktop/docs/test-cases.md."""
import json
import warnings

import pytest
from bs4 import XMLParsedAsHTMLWarning

from desktop import build
from desktop.parse import load_book
from tests.epub_factory import JPG_BYTES, PNG_BYTES, build_epub, empty_spec, guide_spec, novel_spec, untitled_spec
from tests.test_desktop import FakeTTS

@pytest.fixture
def novel(tmp_path):
    return build_epub(tmp_path / "novel.epub", novel_spec())


@pytest.fixture
def untitled(tmp_path):
    return build_epub(tmp_path / "untitled.epub", untitled_spec())


def test_par05_metadata_spine_order_and_toc_titles(novel):
    book = load_book(novel)
    assert book.title == "The Quiet Mill"
    assert book.author == "Ada Fictional"
    # Nested (Section, [Link...]) TOC with hrefs under Text/ still maps to every chapter.
    assert [c.title for c in book.chapters] == ["Preface", "1 The River", "2 The Mill", "3 The Storm"]
    assert book.chapters[1].text.startswith("One\nThe river remembered")


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


def test_par14_short_pages_dropped(untitled):
    assert len(load_book(untitled).chapters) == 2  # "Tiny." page removed


def test_par15_front_matter_not_spoken(novel):
    """Labelled half title (with blurb) and copyright page, plus a page titled exactly "Contents"."""
    book = load_book(novel)
    assert [c.title for c in book.chapters] == ["Preface", "1 The River", "2 The Mill", "3 The Storm"]
    assert all("million readers" not in c.text for c in book.chapters)


def test_par15_front_matter_from_opf_guide(tmp_path):
    book = load_book(build_epub(tmp_path / "guide.epub", guide_spec()))
    titles = [c.title for c in book.chapters]
    assert "Legal Notice" not in titles  # guide type copyright-page
    assert titles == ["Copyright Law", "Contents of the Heart"]  # title match is exact only


def test_par15_preface_and_pagebreak_chapters_kept(novel):
    """Regression guard: other labels (preface, chapter, pagebreak spans) never cause skipping."""
    titles = [c.title for c in load_book(novel).chapters]
    assert "Preface" in titles and "2 The Mill" in titles


def test_par15_unlabelled_book_unchanged(untitled):
    assert [c.title for c in load_book(untitled).chapters] == ["Opening Heading", "Section 2"]


def test_par16_no_xml_parser_warning(novel):
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
