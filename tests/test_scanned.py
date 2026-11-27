"""Scanned-PDF cleaner: OCR layout rebuild and quiz answers (desktop/ocr.py, desktop/scanned.py, D-021/D-022).
IDs refer to desktop/docs/test-cases.md. No docTR here: OCR output is synthetic (tests/scan_factory.py)."""
import sys
from collections import Counter

import numpy as np
import pymupdf
import pytest

from desktop import ocr, scanned, words
from desktop.normalize import normalize
from desktop.parse import load_book
from desktop.scanned import paragraphs, rebuild, strip_margins, title_case
from desktop.words import Lexicon
from tests.scan_factory import STEP, body, line, quiz_book, spread_image
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
    # no word list here (the CI case): 'self-' + 'confidence' joins unless the book spells it with a hyphen;
    # with a word list the hyphen stays (SCAN-18)
    assert "with selfconfidence or with doubt" in key_text
    assert "with self-confidence or with doubt" in "\n".join(chapter(rebuild(quiz_book(), LEX), "A Morning Walk"))
    assert "about so little" in key_text  # docTR's 'SO' inside lowercase text
    lost = chapter(result, "The Lost Key")
    assert "3. I will sleep on the porch tonight." in lost  # hanging indent continues the choice


def test_scan02_drop_cap_a_and_i():
    """A and I are words too: 'I magine' joins, 'A hospital' and 'I can't' stay apart when the book uses
    those words elsewhere (the drop-cap line's own word doesn't count)."""
    def opening(text, *elsewhere):
        pages = [[line("A TEST PAGE", 0.16, 0.3), line(text, 0.29, 0.10, cap=True)], body(list(elsewhere))]
        return paragraphs(pages)[1].text
    assert opening("I magine a clear sky over the sea.", "The sky is blue.").startswith("Imagine a clear sky")
    assert opening("A hospital is a busy place at night.", "The hospital was quiet.").startswith("A hospital is")
    assert opening("I can't believe it happened again.", "You can't stop now.").startswith("I can't believe")
    # docTR reads a big T as I; only the T form is a word in the book
    assert opening("I he river was wide.", "Look at the river by the hill.").startswith("The river")
    # a big letter boxed no taller than the line is still found right after a heading
    pages = [[line("A TEST PAGE", 0.16, 0.3), line("S ome days are long.", 0.29, 0.10)], body(["Some say so."])]
    assert paragraphs(pages)[1].text.startswith("Some days")


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


def test_scan10_missed_big_letter_listed_first_in_report(tmp_path, monkeypatch):
    pages = quiz_book()
    pages[5][2] = line("ou come home late and the key is gone. Which thought comes", 0.29, 0.16)  # 'Y' not read
    monkeypatch.setattr(ocr, "make_engine", lambda: _fake_engine(pages))
    _, report = normalize(_scanned_pdf(tmp_path / "game.pdf"))
    assert report.checks == ["The Lost Key: first word of the text (big first letter not read?): "
                             "'ou come home late and the key is gone. W'"]
    rendered = report.render()
    assert rendered.index("Check by hand (1):") < rendered.index("Chapters (2):")


def test_scan11_language_checked_on_ocr_text(tmp_path, monkeypatch):
    hu = [body([HU[i:i + 60] for i in range(0, len(HU), 60)] * 3, y=0.2)] * 4
    pages = [[line("ELSO FEJEZET", 0.16, 0.3)] + hu[0]] + hu[1:]
    monkeypatch.setattr(ocr, "make_engine", lambda: _fake_engine(pages))
    with pytest.raises(ValueError, match="doesn't look like English"):
        normalize(_scanned_pdf(tmp_path / "hu.pdf"))


def test_scan16_no_headings_keeps_text_as_one_chapter():
    text = [EN_TEXT[i:i + 60] for i in range(0, len(EN_TEXT), 60)]
    result = rebuild([body(text, y=0.2), body(text, y=0.2)])
    assert [c.title for c in result.chapters] == ["Full Text"]
    assert result.chapters[0].text.count("fallen into it.") == 2  # both pages kept
    assert result.checks == ["no chapter headings found: the whole text is one chapter"]
    assert not any(why.startswith("before the first chapter") for why, _ in result.removed)


def _text_pdf(path):
    doc = pymupdf.open()
    for n in range(3):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 520, 760), (EN_TEXT + " ") * 4)
    doc.set_metadata({"title": "The Word Game", "author": "Ada Fictional"})
    doc.save(str(path))
    return path


EN_TEXT = ("The river ran quietly past the old mill while the morning light grew warmer, and the miller "
           "said that the water remembers everything that has ever fallen into it.")


def test_scan15_ocr_always_reads_a_text_pdf_with_ocr(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ocr, "make_engine", lambda: calls.append(1) or _fake_engine(quiz_book()))
    _, report = normalize(_text_pdf(tmp_path / "text.pdf"), ocr="always")
    assert calls and "scanned PDF read with OCR" in report.method and "OCR forced on" in report.method
    assert report.chapters[0][0] == "A Morning Walk"  # the chapters come from the OCR text, not the text layer


def test_scan15_ocr_never_uses_the_text_layer(tmp_path, monkeypatch):
    def no_ocr():
        raise AssertionError("OCR must not run")
    monkeypatch.setattr(ocr, "make_engine", no_ocr)
    _, report = normalize(_text_pdf(tmp_path / "text.pdf"), ocr="never")
    assert "OCR turned off" in report.method and report.chapters
    with pytest.raises(ValueError, match="No readable text"):  # a scan has no text layer to fall back on
        normalize(_scanned_pdf(tmp_path / "scan.pdf"), ocr="never")
    txt = tmp_path / "story.txt"
    txt.write_text((EN_TEXT + "\n\n") * 4, encoding="utf-8")
    _, report = normalize(txt, ocr="always")  # ignored for anything but a PDF
    assert "OCR" not in report.method
    with pytest.raises(ValueError, match="ocr must be one of"):
        normalize(txt, ocr="sometimes")


def test_scan12_missing_ocr_package_explains_install(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "doctr", None)
    monkeypatch.setitem(sys.modules, "doctr.models", None)
    with pytest.raises(ValueError, match="requirements-ocr.txt"):
        normalize(_scanned_pdf(tmp_path / "scan.pdf"))


# ---------------------------------------------------------------- OCR word fixes (D-023)

LEX = Lexicon(["of", "the", "if", "you", "I", "i", "lost", "course", "a", "nuisance", "good", "luck", "half",
               "hour", "self", "confidence", "momentary", "most", "time", "wait", "nothing", "and", "it", "was",
               "zoo", "so", "as", "sleep", "often", "we", "went", "to", "then", "rest", "berry", "make", "case"])


@pytest.fixture(autouse=True)
def _test_lexicon(monkeypatch):
    """The real word list comes from Kokoro, which CI doesn't install: every test uses this small one."""
    monkeypatch.setattr(scanned, "load_lexicon", lambda: LEX)


def _para(lines, lex=LEX, fixes=None):
    return paragraphs([body(lines)], lex, fixes)[-1].text


def test_scan17_lexicon_knows_inflections():
    assert LEX.knows("berries") and LEX.knows("makes") and LEX.knows("good-luck") and LEX.knows("Of,")
    assert not LEX.knows("ofthe") and not LEX.knows("goodluck") and not Lexicon().knows("the")


def test_scan17_lexicon_empty_without_kokoro(monkeypatch):
    words.load_lexicon.cache_clear()
    monkeypatch.setitem(sys.modules, "misaki", None)
    assert not words.load_lexicon()
    words.load_lexicon.cache_clear()


def test_scan18_hyphen_kept_when_both_halves_are_words():
    assert _para(["It brings you good-", "luck for a half-", "hour."]) == "It brings you good-luck for a half-hour."
    assert _para(["It took self-", "confidence."]) == "It took self-confidence."
    assert _para(["A mo-", "mentary pause."]) == "A momentary pause."  # the joined form is a word
    assert _para(["It brings you good-", "luck."], lex=Lexicon()) == "It brings you goodluck."  # no list: as before


def test_scan19_glued_small_words_split():
    fixes = Counter()
    text = _para(["Most ofthe time ifyou wait, Ilost nothing. Ofcourse it was anuisance, ifI wait."], fixes=fixes)
    assert text == "Most of the time if you wait, I lost nothing. Of course it was a nuisance, if I wait."
    assert fixes["ofthe -> of the"] == 1 and sum(fixes.values()) == 6
    assert _para(['"Ilost it," we said.']) == '"I lost it," we said.'  # quote mark before the glued word
    assert _para(["Ioe often waits."]) == "Ioe often waits."  # too short to tell, a known word: left as read
    assert _para(["Most ofthe time."], lex=Lexicon()) == "Most ofthe time."  # no word list: no change


def test_scan20_capitals_and_stray_one():
    assert _para(["We went to the ZOO, then SO I'd rest by the CD case."]) == \
        "We went to the zoo, then so I'd rest by the CD case."  # CD is not a word in lowercase: kept
    assert _para(["AS you sleep we rest."]) == "As you sleep we rest."  # big first letter A beside S
    assert _para(['She said "stop." 1 Then we went.']) == 'She said "stop." Then we went.'
    assert _para(["Most of the time it was over. 1"]) == "Most of the time it was over."
    assert _para(["Scores 1-20 make page 1 Then rest."]) == "Scores 1-20 make page 1 Then rest."


def test_scan20_fixes_listed_in_report():
    pages = quiz_book()
    pages[2][3] = line("Take a breath ofthe hills and begin the walk.", 0.29 + 2 * STEP)
    result = rebuild(pages, LEX)
    assert "Take a breath of the hills" in "\n".join(chapter(result, "A Morning Walk"))
    assert any(n.startswith("OCR words fixed (") and "ofthe -> of the" in n for n in result.notes)
