"""Scanned-PDF cleaner: OCR layout rebuild and quiz answers (desktop/ocr.py, desktop/scanned.py, D-021/D-022).
IDs refer to desktop/docs/test-cases.md. No docTR here: OCR output is synthetic (tests/scan_factory.py)."""
import sys

import numpy as np
import pymupdf
import pytest

from desktop import ocr
from desktop.normalize import normalize
from desktop.parse import load_book
from desktop.scanned import paragraphs, rebuild, strip_margins, title_case
from tests.scan_factory import body, line, quiz_book, spread_image
from tests.test_language import HU


def chapter(result, title):
    return next(c for c in result.chapters if c.title == title).text.split("\n")


def test_scan01_margins_and_back_cover_removed():
    removed = []
    pages = strip_margins(quiz_book(), removed)
    texts = [ln.text for page in pages for ln in page]
    assert "WORD GAME" not in texts and "W ORD GAME" not in texts  # running header, also when OCR splits it
    assert "THE WORD GAME" in texts  # the title page itself is not a header
    assert not any(ln.box[1] > 0.9 for page in pages for ln in page)  # page numbers (contents numbers stay)
    assert len(pages) == 7 and ("back cover (after the last numbered page)", "A GAME FOR EVERY MIND Price 9.99") in removed


def test_scan02_paragraph_rebuild():
    result = rebuild(quiz_book())
    walk = chapter(result, "A Morning Walk")
    # drop cap joined; the line indented around it continues; hyphenated line break rejoined
    assert walk[1] == ("The path through the hills is quiet at dawn, and the momentary chill makes every "
                       "step feel new. Take a breath and begin the walk.")
    key_text = "\n".join(walk)
    assert "with self-confidence or with doubt" not in key_text  # 'self-' + 'confidence': no unbroken form seen
    assert "about so little" in key_text  # docTR's 'SO' inside lowercase text
    lost = chapter(result, "The Lost Key")
    assert "3. I will sleep on the porch tonight." in lost  # hanging indent continues the choice


def test_scan02_hyphen_kept_when_book_spells_it_unbroken():
    pages = [body(["We admire her self-confidence in all things.", "It took self-", "confidence to try."])]
    assert paragraphs(pages)[-1].text.endswith("It took self-confidence to try.")


def test_scan02_ocr_number_glitch():
    pages = [body(["Intro text for the scene, long enough to read.", "1.0n a hill you see a house.", "2. Inside?"])]
    assert [p.numbered for p in paragraphs(pages)] == [None, 1, 2]


def test_scan03_chapters_confirmed_by_contents_page():
    result = rebuild(quiz_book())
    assert [c.title for c in result.chapters] == ["A Morning Walk", "The Lost Key"]  # 'A MORNINGWALK' matched
    assert not result.unconfirmed
    reasons = [r for r, _ in result.removed]
    assert "contents page" in reasons and "before the first chapter (front matter, contents)" in reasons
    assert "Key to The Lost Key" in chapter(result, "The Lost Key")  # wrapped key heading, spoken as printed


def test_scan03_unmatched_contents_entry_reported():
    pages = quiz_book()
    pages[1].insert(-1, line("A MISSING CHAPTER", 0.31))
    assert rebuild(pages).unconfirmed == ["A MISSING CHAPTER"]


def test_scan04_answers_after_each_question():
    result = rebuild(quiz_book())
    walk = chapter(result, "A Morning Walk")
    assert [t[:12] for t in walk] == [
        "A Morning Wa", "The path thr", "1. A bird la", "Key to A Mor", "The walk sta",
        "1. The colou", "2. You find ", "2. What you ", "3. The walk ", "3. The depth"]
    assert "A Morning Walk: answers read after each question" in result.notes


def test_scan05_multiple_choice_keeps_book_order():
    result = rebuild(quiz_book())
    lost = chapter(result, "The Lost Key")
    assert lost.index('2. "Someone must have taken it."') < lost.index("Key to The Lost Key") \
        < lost.index("1. You blame yourself first and look for the mistake.")
    assert "The Lost Key: book order (multiple choice)" in result.notes


def test_scan06_mismatched_numbers_keep_book_order():
    pages = quiz_book()
    pages[4] = [ln for ln in pages[4] if not ln.text.startswith("2.")]  # the key lost answer 2
    result = rebuild(pages)
    assert "A Morning Walk: book order (question and answer numbers differ)" in result.notes
    walk = chapter(result, "A Morning Walk")
    assert walk.index("3. The walk ends at a river. How deep is the water?") < walk.index("Key to A Morning Walk")


def test_scan07_title_case():
    assert title_case("YOU'RE ONLY HUMAN") == "You're Only Human"
    assert title_case("(NOT So) HAPPILY EVER AFTER") == "(Not So) Happily Ever After"
    assert title_case("A NIGHT AT THE SYMPHONY") == "A Night at the Symphony"


def test_scan08_gutter_split_off_centre():
    left, right = ocr.split_spread(spread_image(gutter=0.44))
    assert abs(left.shape[1] - 0.44 * 1200) < 40  # cut in the empty gutter, not at the centre (600)
    assert (left[:, -5:] == 255).all() and (right[:, :5] == 255).all()  # no text sliced
    assert len(ocr.split_spread(np.full((800, 600, 3), 255, dtype=np.uint8))) == 1  # single page


def _scanned_pdf(path, pages=4):
    doc = pymupdf.open()
    img = spread_image()
    pix = pymupdf.Pixmap(pymupdf.csRGB, img.shape[1], img.shape[0], img.tobytes(), False)
    for _ in range(pages):
        page = doc.new_page(width=600, height=400)
        page.insert_image(page.rect, pixmap=pix)
    doc.set_metadata({"title": "The Word Game", "author": "Ada Fictional"})
    doc.save(str(path))
    return path


def test_scan09_scan_detection(tmp_path):
    assert ocr.is_scanned(_scanned_pdf(tmp_path / "scan.pdf"))
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "A born-digital page with a real text layer.")
    doc.save(str(tmp_path / "text.pdf"))
    assert not ocr.is_scanned(tmp_path / "text.pdf")


def _fake_engine(pages):
    queue = iter(pages)

    def engine(img):
        return next(queue, [])
    return engine


def test_scan10_normalize_scanned_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "make_engine", lambda: _fake_engine(quiz_book()))
    out, report = normalize(_scanned_pdf(tmp_path / "game.pdf"))
    book = load_book(out)
    assert book.normalized and book.title == "The Word Game" and book.cover
    assert [c.title for c in book.chapters] == ["A Morning Walk", "The Lost Key"]
    assert book.chapters[0].text.split("\n")[3] == "Key to A Morning Walk"
    rendered = (tmp_path / "game.std.report.txt").read_text(encoding="utf-8")
    assert "scanned PDF read with OCR" in rendered and "answers read after each question" in rendered


def test_scan11_language_checked_on_ocr_text(tmp_path, monkeypatch):
    hu = [body([HU[i:i + 60] for i in range(0, len(HU), 60)] * 3, y=0.2)] * 4
    pages = [[line("ELSO FEJEZET", 0.16, 0.3)] + hu[0]] + hu[1:]
    monkeypatch.setattr(ocr, "make_engine", lambda: _fake_engine(pages))
    with pytest.raises(ValueError, match="doesn't look like English"):
        normalize(_scanned_pdf(tmp_path / "hu.pdf"))


def test_scan12_missing_ocr_package_explains_install(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "doctr", None)
    monkeypatch.setitem(sys.modules, "doctr.models", None)
    with pytest.raises(ValueError, match="requirements-ocr.txt"):
        normalize(_scanned_pdf(tmp_path / "scan.pdf"))
