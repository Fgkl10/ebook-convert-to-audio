"""EPUB cleaner (desktop/normalize.py, D-019/D-020). IDs refer to desktop/docs/test-cases.md."""
import pytest

from desktop import build
from desktop.build import make_book_id
from desktop.normalize import normalize
from desktop.parse import load_book
from tests.epub_factory import build_epub, calibre_spec, novel_spec, untitled_spec
from tests.test_language import HU


@pytest.fixture
def calibre(tmp_path):
    return build_epub(tmp_path / "calibre.epub", calibre_spec())


def chapters(path):
    return [(c.title, c.text) for c in load_book(path).chapters]


def test_norm01_calibre_book_cut_at_confirmed_headings(calibre):
    out, _ = normalize(calibre)
    book = load_book(out)
    assert [c.title for c in book.chapters] == ["PREFACE", "1 The River", "2 The Mill", "3 The Storm"]
    text = {c.title: c.text for c in book.chapters}
    assert text["1 The River"].startswith("1 The River\nThe river remembered")  # heading split off its paragraph
    assert "1.1 Morning" in text["1 The River"]  # subsection stays inside its chapter
    assert text["2 The Mill"].startswith("PART TWO\n2 The Mill")  # short part heading read with chapter 2
    assert text["3 The Storm"].startswith("3 The\nStorm")  # heading split over two paragraphs
    assert "The preface ends with a long look" in text["PREFACE"]  # a page anchor is not a cut point
    assert text["2 The Mill"].endswith("for the night.")


def test_norm01_removed_and_ignored_are_reported(calibre):
    out, report = normalize(calibre)
    all_text = "\n".join(t for _, t in chapters(out))
    for gone in ("All rights reserved", "CONTENTS", "Nowhere Press"):
        assert gone not in all_text
    reasons = [r for r, _ in report.removed]
    assert "contents page" in reasons and "back matter: BIBLIOGRAPHY" in reasons
    assert "before the first chapter (front matter)" in reasons
    for junk in (",1", "1997)11", "address.”12"):
        assert junk in report.unconfirmed
    assert any(t.startswith("chapter and show how") for t in report.unconfirmed)
    assert (out.parent / "calibre.std.report.txt").read_text(encoding="utf-8").startswith("Normalized:")


def test_norm02_well_formed_book_unchanged(tmp_path):
    src = build_epub(tmp_path / "novel.epub", novel_spec())  # labelled front matter, one file per chapter
    out, _ = normalize(src)
    assert chapters(out) == chapters(src)


def test_norm03_round_trip_and_idempotent(calibre, tmp_path):
    out, report = normalize(calibre)
    book = load_book(out)
    assert book.normalized and report.chapters == [(c.title, len(c.text)) for c in book.chapters]
    again, _ = normalize(out, tmp_path / "again.std.epub")
    assert chapters(again) == chapters(out)
    assert (book.title, book.author) == ("The Quiet Mill", "Ada Fictional")


def test_norm04_book_id_stable_across_runs(calibre, tmp_path):
    a, _ = normalize(calibre, tmp_path / "a.std.epub")
    b, _ = normalize(calibre, tmp_path / "b.std.epub")
    ids = {make_book_id(load_book(p), p) for p in (a, b, calibre)}
    assert len(ids) == 1  # same id for the original and every cleaned copy


def test_norm05_no_confirmed_toc_falls_back_to_files(tmp_path):
    src = build_epub(tmp_path / "untitled.epub", untitled_spec())
    out, report = normalize(src)
    assert "fallback" in report.method
    assert chapters(out) == chapters(src)


def test_norm06_txt_repackaged(tmp_path):
    src = tmp_path / "story.txt"
    src.write_text("Chapter 1\n\nIt was a dark night. The wind howled loudly.\n\n"
                   "Chapter 2\n\nMorning came at last. Everyone was relieved.\n", encoding="utf-8")
    out, _ = normalize(src)
    assert out.name == "story.std.epub" and chapters(out) == chapters(src)


def test_norm07_language_refused_before_review(tmp_path):
    src = tmp_path / "hu.txt"
    src.write_text("\n\n".join([HU] * 8), encoding="utf-8")
    with pytest.raises(ValueError, match="doesn't look like English"):
        normalize(src)
    assert not (tmp_path / "hu.std.epub").exists()
    out, _ = normalize(src, ignore_language=True)
    assert out.exists()


def test_norm08_cli_build_refuses_uncleaned_book(calibre, capsys):
    with pytest.raises(SystemExit) as e:
        build.main([str(calibre), "--chapters", "1"])
    assert "has not been cleaned yet" in str(e.value) and "desktop.normalize" in str(e.value)
    build.main([str(calibre), "--list-chapters"])  # listing is still allowed on any file
    out, _ = normalize(calibre)
    capsys.readouterr()
    build.main([str(out), "--list-chapters"])
    assert "3 The Storm" in capsys.readouterr().out


def _spec(pages):
    from tests.epub_factory import Page, Spec, para

    return Spec(pages=[Page(f, f"<h1>{h}</h1>" + para() + extra, toc_title=t) for f, h, t, extra in pages])


def test_norm13_sparse_toc_keeps_untitled_chapter_files(tmp_path):
    src = build_epub(tmp_path / "sparse.epub",
                     _spec([(f"c{i}.xhtml", f"Chapter {i}", "Chapter 1" if i == 1 else None, "") for i in range(1, 5)]))
    out, _ = normalize(src)
    assert [t for t, _ in chapters(out)] == ["Chapter 1", "Chapter 2", "Chapter 3", "Chapter 4"]


def test_norm13_toc_with_only_parts_keeps_chapters(tmp_path):
    src = build_epub(tmp_path / "parts.epub", _spec([
        ("p1.xhtml", "Part One", "Part One", ""), ("c1.xhtml", "The Arrival", None, ""),
        ("c2.xhtml", "The Departure", None, ""), ("p2.xhtml", "Part Two", "Part Two", ""),
        ("c3.xhtml", "The Return", None, "")]))
    out, _ = normalize(src)
    assert [t for t, _ in chapters(out)] == ["Part One", "The Arrival", "The Departure", "Part Two", "The Return"]


def test_norm14_repeated_titles_are_separate_chapters(tmp_path):
    src = build_epub(tmp_path / "repeat.epub", _spec([
        ("a.xhtml", "Interlude", "Interlude", ""), ("b.xhtml", "Chapter Two", "Chapter Two", ""),
        ("c.xhtml", "Interlude", "Interlude", "")]))
    out, _ = normalize(src)
    assert [t for t, _ in chapters(out)] == ["Interlude", "Chapter Two", "Interlude"]


def test_norm15_endnotes_with_backlinks_are_kept(tmp_path):
    notes = "".join(f'<p><a href="ch1.xhtml#r{i}">{i}</a> This is the text of note number {i}, which explains '
                    "a detail from the chapter.</p>" for i in range(1, 7))
    src = build_epub(tmp_path / "notes.epub", _spec([
        ("ch1.xhtml", "Chapter One", "Chapter One", ""), ("notes.xhtml", "Notes", "Notes", notes)]))
    out, report = normalize(src)
    assert [t for t, _ in chapters(out)] == ["Chapter One", "Notes"]
    assert "contents page" not in [r for r, _ in report.removed]


def test_norm16_std_epub_never_rewritten_in_place(calibre):
    out, _ = normalize(calibre)
    before = out.read_bytes()
    same, report = normalize(out)
    assert same == out and out.read_bytes() == before and "nothing written" in report.method


def test_norm18_nested_toc_sections_stay_in_their_chapter(tmp_path):
    from tests.epub_factory import textbook_spec

    out, report = normalize(build_epub(tmp_path / "textbook.epub", textbook_spec()))
    got = dict(chapters(out))
    assert list(got) == ["Hello", "1 The River Begins", "2 The Mill Turns"]  # TOC titles, not 'CHAPTER ONE'
    one = got["1 The River Begins"]
    assert one.startswith("CHAPTER ONE\nThe River Begins\n")
    assert "\nMorning\n" in one and "\nNoon\n" in one and "#3 The Lens of Tide" in one  # sections, boxes inside
    everything = "\n".join(got.values())
    assert "All rights reserved" not in everything and "Special Edition" not in everything
    assert "front matter: Copyright Page" in [r for r, _ in report.removed]
    # sections and contents-page links are not candidates at all; only front-matter entries stay unmatched
    assert report.unconfirmed == ["Half Title", "Table of Contents", "Table of Lenses"]


def test_norm18_chapter_label_matches_toc_number():
    from desktop.normalize import _key, _unlabel

    assert _unlabel(_key("CHAPTER ONE In the Beginning")) == _unlabel(_key("1 In the Beginning")) == "in the beginning"
    assert _unlabel(_key("Part 2 The Mill")) == "the mill" and _unlabel(_key("1984")) == "1984"
