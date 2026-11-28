"""EPUB parser tests on synthetic books (tests/epub_factory.py). IDs refer to desktop/docs/test-cases.md."""
import json
import warnings

import pytest
from bs4 import XMLParsedAsHTMLWarning

from desktop.core.parse import load_book
from desktop.tts import build
from tests.epub_factory import (
    JPG_BYTES, PNG_BYTES, build_epub, empty_spec, guide_spec, novel_spec, single_file_spec, untitled_spec,
)
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


def test_par07_note_links_without_sup_removed_cross_references_kept():
    from desktop.core.parse import body_blocks, clean_body

    html = ("<html><body>"
            '<p>The mill stopped at noon. <a href="#page_3"><span class="c9">2</span></a> It was quiet.</p>'
            '<p>Nobody came back<a href="notes.xhtml#n4">4</a>, not even the miller<a href="#n5">[5]</a>.</p>'
            '<p><a href="#n2">2</a> A note at the end of the chapter, opening with its backlink.</p>'
            '<p>See Chapters <a href="c9.xhtml">9</a> through <a href="c11.xhtml">11</a>, '
            '<a href="c24.xhtml">24</a>, and <a href="c33.xhtml">33</a>, Figure <a href="#f5">5</a>, '
            'page <a href="#p12">12</a> and Lens #<a href="#l3">3</a>.</p>'
            '<p><a href="c12.xhtml">12</a></p>'  # a link alone on its line: a contents entry or page number
            '<p>Read it at <a href="https://example.com/7">7</a> today.</p>'
            "</body></html>").encode()
    text = "\n".join(" ".join(lines) for _, lines in body_blocks(clean_body(html)))
    assert "The mill stopped at noon. It was quiet." in text
    assert "Nobody came back, not even the miller." in text
    assert "A note at the end of the chapter" not in text  # the whole footnote paragraph goes (PAR-07c)
    assert "See Chapters 9 through 11, 24, and 33, Figure 5, page 12 and Lens #3." in text
    assert "\n12\n" in text and "example.com" not in text and "at 7 today" in text


def test_par07_footnote_paragraphs_removed():
    from desktop.core.parse import body_blocks, clean_body

    html = ("<html><body><div class='calibre'>"
            '<p>The mill stopped at noon.<a href="#n1">1</a> The miller went home.</p>'
            '<p>\xa0<span class="c4"><a href="#r1">1</a></span> A made-up note about the mill and its history.</p>'
            '<p class="c3">\xa0</p>'
            '<p><a href="#r2"><span class="c9">[2]</span></a>Another note, glued to its backlink, that runs</p>'
            '<p><span class="c9">on over a second line and</span></p><p><span class="c9">a third.</span></p>'
            '<p class="c3"> </p>'  # the empty paragraph ends the note
            '<p>Body text resumes after the notes.</p>'
            '<aside epub:type="footnote"><p>A labelled note with no number.</p></aside>'
            '<div role="doc-endnote">An endnote labelled by role.</div>'
            '<p><a href="c3.xhtml">3</a></p>'  # a lone number link (page list, contents): kept
            '<p>3 rivers meet here, and the text goes on.</p>'  # a number that is not a link: kept
            "</div><div><a href='#top'>4</a><p>A container opening with a link is never dropped.</p></div>"
            "</body></html>").encode()
    stats = {}
    text = "\n".join(" ".join(lines) for _, lines in body_blocks(clean_body(html, stats)))
    assert "The mill stopped at noon. The miller went home." in text
    for gone in ("made-up note", "Another note", "second line", "a third", "labelled note", "endnote labelled"):
        assert gone not in text
    assert "Body text resumes after the notes." in text
    assert "\n3\n" in text and "3 rivers meet here" in text and "container opening" in text
    assert stats == {"note paragraphs": 4}


def test_par07_note_without_an_end_keeps_following_lines():
    from desktop.core.parse import MAX_NOTE_LINES, body_blocks, clean_body

    lines = "".join(f"<p>Body line {i} of a long passage.</p>" for i in range(MAX_NOTE_LINES + 3))
    small = "".join(f'<p><span class="c9">Small line {i} of a long passage.</span></p>' for i in range(MAX_NOTE_LINES + 3))
    for following in (lines, small):  # body-style lines; small print with no end within MAX_NOTE_LINES
        html = f'<html><body><p><a href="#r1"><span class="c9">1</span></a> A note.</p>{following}</body></html>'
        text = "\n".join(" ".join(ls) for _, ls in body_blocks(clean_body(html.encode())))
        assert "A note." not in text
        assert "line 0 of" in text and f"line {MAX_NOTE_LINES + 2} of" in text  # nothing after the note lost


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


@pytest.mark.parametrize("variant", ["labelled", "toc-title", "guide"])
def test_par17_single_file_book_keeps_chapters(tmp_path, variant):
    """Skipping is per page: front matter sharing a file with chapter 1 must not drop the chapter."""
    book = load_book(build_epub(tmp_path / f"{variant}.epub", single_file_spec(variant)))
    assert [c.title for c in book.chapters] == ["Chapter One"]  # real title, never "Title Page"
    assert "The river ran quietly" in book.chapters[0].text
    if variant == "labelled":
        assert "All rights reserved" not in book.chapters[0].text  # labelled section removed


def test_par15_unlabelled_book_unchanged(untitled):
    assert [c.title for c in load_book(untitled).chapters] == ["Opening Heading", "Section 2"]


def test_par16_no_xml_parser_warning(novel):
    with warnings.catch_warnings():
        warnings.simplefilter("error", XMLParsedAsHTMLWarning)
        load_book(novel)


def test_bld09_epub_build_writes_cover_and_toc_titles(novel, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    out = build.build_book(novel, tmp_path / "lib", backend=FakeTTS())
    m = json.loads((out / "book.json").read_text(encoding="utf-8"))
    assert m["complete"] and m["title"] == "The Quiet Mill"
    assert m["cover"] == "cover.jpg" and (out / "cover.jpg").read_bytes() == JPG_BYTES
    assert [c["title"] for c in m["chapters"]][-3:] == ["1 The River", "2 The Mill", "3 The Storm"]
