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
