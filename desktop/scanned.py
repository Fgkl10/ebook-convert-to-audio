"""Rebuild a scanned book from OCR lines (decisions D-021, D-022).

Pure functions over `ocr.Line`s, so they are tested without docTR:
  1. drop running headers, page numbers and the back cover (pages after the last printed page number)
  2. build paragraphs from indentation, vertical gaps and numbered items; join drop caps ("T he" ->
     "The") and hyphenated line breaks; fix clear OCR word errors ("ofthe" -> "of the", D-023)
  3. find chapter headings (capitals at the top of a page) confirmed by the book's own contents page,
     the same propose/confirm idea as EPUB (D-020)
  4. for quiz books: when every numbered item of a quiz is its own question and its "KEY TO ..."
     answers are numbered the same, read each answer right after its question (D-022)
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from .ocr import Line, Page
from .parse import Book, Chapter
from .words import Lexicon, load_lexicon

TOP, BOTTOM = 0.12, 0.90  # running headers / page numbers live above TOP or below BOTTOM
HEADER_ZONE = 0.10  # running headers sit above this; chapter headings lower (~0.15)
HEADING_ZONE = 0.30  # a chapter heading starts above this
INDENT = 0.04  # a first-line indent (~0.05) is at least this far right of the left margin; hanging indents (~0.03) are not
GAP = 1.7  # a vertical gap this many times the line spacing starts a new paragraph
TITLE_MATCH = 0.8  # fuzzy ratio between a contents entry and a heading (OCR noise)
ITEM = re.compile(r"^(\d{1,2})\.\s?(?=\S)(?!\d)")  # "1. You are", '2."I guess' but not "41-60." or "1.5"
_SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to"}
# Two-letter words docTR returns in capitals inside lowercase text ("not SO subtle").
_CAPS_FIX = {"SO", "OC", "OR", "ON", "NO", "TO", "OF", "IN", "IS", "IT", "AS", "AT", "SO,", "SO."}


@dataclass
class Para:
    text: str
    page: int
    heading: bool = False
    numbered: int | None = None


@dataclass
class ScanResult:
    chapters: list[Chapter]
    removed: list[tuple[str, str]] = field(default_factory=list)  # (reason, first 80 chars)
    unconfirmed: list[str] = field(default_factory=list)  # contents entries never found as headings
    notes: list[str] = field(default_factory=list)  # per-chapter decisions (answer placement)
    checks: list[str] = field(default_factory=list)  # things to look at by hand (missed big first letters)


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _short(text: str) -> str:
    return text[:80] + ("…" if len(text) > 80 else "")


def _is_caps(text: str) -> bool:
    letters = re.findall(r"[A-Za-z]", text)
    return len(letters) >= 3 and sum(c.isupper() for c in letters) >= 0.8 * len(letters)


def _is_page_number(text: str) -> bool:
    return re.fullmatch(r"\W*\d{1,4}\W*", text) is not None


# ---------------------------------------------------------------- 1. margins

def _matches_title(text: str, titles: list[str]) -> bool:
    k = _key(text)
    return bool(k) and any(SequenceMatcher(None, k, _key(t)).ratio() >= TITLE_MATCH for t in titles)


def strip_margins(pages: list[Page], removed: list[tuple[str, str]], titles: list[str] = ()) -> list[Page]:
    """Remove page numbers, running headers (the same text in the margin of many pages, spaces
    ignored so 'K OKOLOGY' counts, or a chapter title in the top margin, as on the intro pages)
    and every page after the last printed page number (back cover). Chapter headings sit lower
    than running headers, so a title in the top margin is a header, not a heading."""
    counts: dict[str, int] = {}
    for page in pages:
        for k in {_key(ln.text) for ln in page if ln.box[1] < TOP or ln.box[1] > BOTTOM}:
            counts[k] = counts.get(k, 0) + 1
    repeated = {k for k, n in counts.items() if k and n >= max(3, 0.1 * len(pages))}
    numbered, out = [], []
    for page in pages:
        kept, has_number = [], False
        for ln in page:
            in_margin = ln.box[1] < TOP or ln.box[1] > BOTTOM
            if in_margin and _is_page_number(ln.text):
                has_number = True
            elif not (in_margin and _key(ln.text) in repeated) \
                    and not (ln.box[1] < HEADER_ZONE and _matches_title(ln.text, titles)):
                kept.append(ln)
        numbered.append(has_number)
        out.append(kept)
    last = max((i for i, n in enumerate(numbered) if n), default=len(out) - 1)
    back = " ".join(ln.text for page in out[last + 1:] for ln in page)
    if back.strip():
        removed.append(("back cover (after the last numbered page)", _short(back)))
    return out[:last + 1]


# ---------------------------------------------------------------- 2. paragraphs

def _join(a: str, b: str, vocabulary: set[str], counts: Counter, lex: Lexicon) -> str:
    """Join two lines of one paragraph, undoing end-of-line hyphenation ('mo-' + 'mentary').
    The hyphen is kept when the book spells the word with a hyphen elsewhere ('self-confidence'), or
    when the joined form is not a word but both halves are ('good-' + 'luck', 'half-' + 'hour')."""
    m = re.search(r"(\w+)-$", a)
    if m and b[:1].islower():
        first = m.group(1)
        rest = re.match(r"[\w']+", b).group(0)
        joined = (first + rest).lower()
        if f"{first}-{rest}".lower() in vocabulary:
            return a + b
        if counts[joined] or lex.knows(joined):
            return a[:-1] + b
        if lex.knows(first) and lex.knows(rest):
            return a + b
        return a[:-1] + b
    return f"{a} {b}"


_GLUED = re.compile(r"^(of|if|I|a)([a-z][\w'’]*)$", re.IGNORECASE)  # 'ofthe', 'Ifyou', "Ican't", 'anuisance'
_LONE_ONE = re.compile(r"(?<=[.!?'\"”’]) 1(?= [A-Z\"“]| ?$)")  # a quote mark read as '1': "…puke.' 1 Rephrase"


def _unglue(word: str, lex: Lexicon) -> str | None:
    """'ofthe' -> 'of the': a small word glued to the next, when the glued form is not a word."""
    lead = word[: len(word) - len(word.lstrip("\"“‘'("))]  # '"Ican't' -> '"', "Ican't"
    word = word[len(lead):]
    core = word.rstrip(".,;:!?\"'”’)")
    m = _GLUED.match(core)
    if not m or lex.knows(core):
        return None
    head, rest = m.groups()
    short_ok = head.lower() in ("of", "if") and rest.lower() in ("a", "i")  # 'ofa', 'IfI'
    if head.lower() in ("i", "a") and (head == "i" or len(rest) < 3):
        return None  # 'Ioe', 'ift': too short to tell; lowercase 'i' is never the word I
    if (len(rest) >= 2 or short_ok) and lex.knows(rest):
        return f"{lead}{head} {rest}{word[len(core):]}"
    return None


def _fix_words(text: str, lex: Lexicon, fixes: Counter) -> str:
    """Fix clear OCR word errors and count each fix for the report. Only words the dictionary
    settles are changed; anything unsure is left as read."""
    text, n = _LONE_ONE.subn("", text)
    if n:
        fixes["quote mark read as '1' removed"] += n
    words = text.split(" ")
    for i, w in enumerate(words):
        prev = words[i - 1] if i else ""
        nxt = words[i + 1] if i + 1 < len(words) else ""
        core = w.rstrip(".,;:!?")
        caps = core.isalpha() and core.isupper() and 2 <= len(core) <= 4
        lower_next = nxt[:1].islower() or re.match(r"I\b", nxt) is not None  # 'SO I'd run'
        if caps and lower_next and (core in _CAPS_FIX or (lex.knows(core) and core not in lex.keys)):
            if i and prev[-1:].islower() or prev[-1:] in (",", ";", ":"):
                words[i] = w.lower()  # 'not SO subtle', 'at the ZOO, or'
            elif i == 0:
                words[i] = w[0] + w[1:].lower()  # 'AS you fall asleep' (big first letter A beside S)
            if words[i] != w:
                fixes[f"{core} -> {words[i].rstrip('.,;:!?')}"] += 1
            continue
        if lex:
            split = _unglue(w, lex)
            if split:
                fixes[f"{w.rstrip('.,;:!?')} -> {split.rstrip('.,;:!?')}"] += 1
                words[i] = split
    return " ".join(words)


def _drop_cap(line: Line) -> bool:
    """'T he candy…': the first word is one big capital letter set apart from its word."""
    if len(line.words) < 2:
        return False
    first, rest = line.words[0], line.words[1:]
    return (len(first.text) == 1 and first.text.isalpha() and first.text.isupper()
            and first.height > 1.2 * statistics.median(w.height for w in rest))


def _join_cap(letter: str, rest: list[str], counts: Counter) -> str:
    """Join a big first letter to its word, using the words the book itself uses:
    'S ome' -> 'Some', 'A ll' -> 'All', 'I t's' -> "It's" (the joined word appears in the book);
    'I he' -> 'The', 'I here's' -> "There's" (docTR reads a big T as I or L; only the T form appears);
    'A hospital', 'I can't' stay two words (A and I are words, and the next word appears on its own
    elsewhere: 2+ times, since this line counts once)."""
    nxt = rest[0].lower().strip(".,;:!?\"()")
    joined, alone, as_t = counts[letter.lower() + nxt], counts[nxt], counts["t" + nxt]
    # Frequencies, not mere presence: OCR glues words now and then ("Ican't" once vs "can't" 23 times).
    if letter in "IL" and as_t > max(joined, alone):
        return "T" + " ".join(rest)
    if letter in "AI" and alone >= 2 and alone > joined:
        return letter + " " + " ".join(rest)
    return letter + " ".join(rest)


def _merge_cap_lines(page: Page) -> Page:
    """docTR often returns a big first letter as a line of its own (['S'] beside ['ome', 'days', …]).
    Put it back at the start of the line it sits next to."""
    out: Page = []
    i = 0
    while i < len(page):
        ln = page[i]
        nxt = page[i + 1] if i + 1 < len(page) else None
        if (nxt is not None and len(ln.words) == 1 and len(ln.text) == 1 and ln.text.isupper()
                and abs(nxt.box[1] - ln.box[1]) < 0.015 and nxt.box[0] > ln.box[0]):
            out.append(Line(ln.words + nxt.words))
            i += 2
        else:
            out.append(ln)
            i += 1
    return out


def _cap_letter(line: Line, first_after_heading: bool) -> bool:
    """A big first letter: one capital set apart from its word. Its box is often taller than the line
    (_drop_cap), but not always, so the first line after a heading also counts when it opens with a
    lone capital followed by a lowercase fragment ('S ome days', 'A ll of us')."""
    if _drop_cap(line):
        return True
    w = line.words
    return (first_after_heading and len(w) > 1 and len(w[0].text) == 1 and w[0].text.isupper()
            and w[1].text[:1].islower())


def paragraphs(pages: list[Page], lex: Lexicon | None = None, fixes: Counter | None = None) -> list[Para]:
    """Paragraphs in reading order. A heading is a line of capitals at the top of a page, before any body text.
    `lex` settles hyphens and glued words (empty: book evidence only); `fixes` counts each word fixed."""
    lex = lex if lex is not None else Lexicon()
    fixes = fixes if fixes is not None else Counter()
    spacing = statistics.median(
        [b.box[1] - a.box[1] for page in pages for a, b in zip(page, page[1:]) if 0 < b.box[1] - a.box[1] < 0.1]
        or [0.025])
    all_words = [w.lower().strip(".,;:!?\"'()") for page in pages for ln in page for w in ln.text.split()]
    vocabulary = {w for w in all_words if "-" in w.strip("-")}  # hyphenated words seen unbroken
    counts = Counter(all_words)
    paras: list[Para] = []
    for n, page in enumerate(pages):
        if not page:
            continue
        page = _merge_cap_lines(page)
        body = [ln for ln in page if not (ln.box[1] < HEADING_ZONE and _is_caps(ln.text))] or page
        margin = statistics.median(ln.box[0] for ln in body) if len(body) >= 3 else min(ln.box[0] for ln in body)
        margin = min([margin] + [ln.box[0] for ln in body if abs(ln.box[0] - margin) < INDENT])
        prev, in_body, after_cap = None, False, False
        for ln in page:
            text = ln.text.strip()
            if not text:
                continue
            x0, y0 = ln.box[0], ln.box[1]
            wrapped = (not in_body and paras and paras[-1].heading and paras[-1].page == n and prev is not None
                       and y0 - prev.box[1] < 2 * spacing and len(text.split()) <= 3)  # "KEY TO … SEE" + "You Now"
            if not in_body and y0 < HEADING_ZONE and (_is_caps(text) or wrapped):
                if wrapped or (paras and paras[-1].heading and paras[-1].page == n and prev
                               and y0 - prev.box[1] < 2 * spacing):
                    paras[-1].text += " " + text  # heading wrapped over two lines
                else:
                    paras.append(Para(text, n, heading=True))
                prev = ln
                continue
            # Right after a heading the big first letter (read or not, e.g. 'ne day…') indents the
            # next line too, so that line continues the paragraph.
            first_after_heading = not in_body and bool(paras) and paras[-1].heading
            cap = _cap_letter(ln, first_after_heading)
            if cap:
                text = _join_cap(ln.words[0].text, [w.text for w in ln.words[1:]], counts)
            text = re.sub(r"^(\d{1,2})\.0(?=[a-z])", r"\1. O", text)  # '1.0n a stroll' -> '1. On a stroll'
            item = ITEM.match(text)
            indented = x0 > margin + INDENT and not after_cap
            gap = prev is not None and y0 - prev.box[1] > GAP * spacing
            starts = item or indented or gap or cap or not paras or paras[-1].heading
            if not in_body and not (item or indented or cap) and paras and not paras[-1].heading:
                starts = False  # first line of a page continues the paragraph from the previous page
            if starts:
                paras.append(Para(text, n, numbered=int(item.group(1)) if item else None))
            else:
                paras[-1].text = _join(paras[-1].text, text, vocabulary, counts, lex)
            in_body, after_cap, prev = True, bool(cap or first_after_heading), ln
    for p in paras:
        p.text = re.sub(r"\s+", " ", p.text).strip()
        if not p.heading:
            p.text = _fix_words(p.text, lex, fixes)
    return paras


# ---------------------------------------------------------------- 3. chapters

def contents_titles(pages: list[Page]) -> list[str]:
    """Entries of the book's contents pages: lines of capitals on pages headed CONTENTS."""
    titles = []
    for page in pages:
        if not any(_key(ln.text) == "contents" for ln in page):
            continue
        titles += [ln.text for ln in page if _is_caps(ln.text) and _key(ln.text) != "contents"]
    return titles


def _is_key_heading(text: str) -> bool:
    return _key(text).startswith("keyto")


def title_case(text: str) -> str:
    """'A DESERT JOURNEY' -> 'A Desert Journey', "YOU'RE ONLY HUMAN" -> "You're Only Human"."""
    words = text.lower().split()
    out = []
    for i, w in enumerate(words):
        lead = re.match(r"\W*", w).group(0)
        core = w[len(lead):]
        if i and core in _SMALL:
            out.append(w)
        else:
            out.append(lead + core[:1].upper() + core[1:])
    return " ".join(out)


@dataclass
class _Section:
    title: str
    quiz: list[Para] = field(default_factory=list)
    key_heading: str = ""
    key: list[Para] = field(default_factory=list)


def _sections(paras: list[Para], titles: list[str], result: ScanResult) -> list[_Section]:
    """Cut at headings confirmed by contents entries, in order. KEY TO headings open the answer part
    of the current section; any other heading stays in the text as a line."""
    keys = [_key(t) for t in titles]
    confirmed: dict[int, str] = {}
    pos = 0
    for title, k in zip(titles, keys):
        for i in range(pos, len(paras)):
            p = paras[i]
            if p.heading and not _is_key_heading(p.text) and SequenceMatcher(None, k, _key(p.text)).ratio() >= TITLE_MATCH:
                confirmed[i], pos = p.text, i + 1
                break
        else:
            result.unconfirmed.append(title)
    if len(confirmed) < 2:  # no usable contents page: every top-of-page heading starts a chapter
        result.unconfirmed.clear()
        confirmed = {i: p.text for i, p in enumerate(paras) if p.heading and not _is_key_heading(p.text)}
        result.notes.append("no contents page matched: chapters start at every heading in capitals")
    if not confirmed and paras:  # no heading at all: keep the whole text as one chapter rather than lose it
        result.checks.append("no chapter headings found: the whole text is one chapter")
        return [_Section("Full Text", quiz=list(paras))]
    sections: list[_Section] = []
    front = []
    for i, p in enumerate(paras):
        if i in confirmed:
            sections.append(_Section(title_case(p.text)))
        elif not sections:
            front.append(p.text)
        elif p.heading and _is_key_heading(p.text) and not sections[-1].key_heading:
            sections[-1].key_heading = f"Key to {sections[-1].title}"  # as printed; OCR glues words here
        elif sections[-1].key_heading:
            sections[-1].key.append(p)
        else:
            sections[-1].quiz.append(p)
    if front:
        result.removed.append(("before the first chapter (front matter, contents)", _short(" ".join(front))))
    return sections


# ---------------------------------------------------------------- 4. quiz answers

def _items(paras: list[Para]) -> tuple[list[Para], list[list[Para]]]:
    """(intro, numbered items); an item runs until the next numbered paragraph."""
    intro, items = [], []
    for p in paras:
        if p.numbered is not None and not p.heading:
            items.append([p])
        elif items:
            items[-1].append(p)
        else:
            intro.append(p)
    return intro, items


def _asks(item: list[Para]) -> bool:
    """A question outside quoted speech: choices like '"Where did I put it?"' don't count."""
    text = re.sub(r'["“][^"”]*["”]', "", " ".join(p.text for p in item))
    return "?" in text


def _text(paras: list[Para]) -> list[str]:
    return [p.text for p in paras]


def chapter_text(section: _Section) -> tuple[list[str], str]:
    """Lines of the chapter, and how its answers were placed."""
    lines = [section.title]
    if not section.key_heading:
        return lines + _text(section.quiz), ""
    intro, questions = _items(section.quiz)
    key_intro, answers = _items(section.key)
    numbers = [q[0].numbered for q in questions]
    same = numbers == [a[0].numbered for a in answers] == list(range(1, len(numbers) + 1)) and len(numbers) >= 2
    if same and 2 * sum(map(_asks, questions)) >= len(questions):
        lines += _text(intro)
        for n, (q, a) in enumerate(zip(questions, answers)):
            lines += _text(q)
            if n == 0:
                lines += [section.key_heading] + _text(key_intro)
            lines += _text(a)
        return lines, "answers read after each question"
    why = ("no numbered questions" if not numbers else "multiple choice" if same
           else "question and answer numbers differ")
    return lines + _text(section.quiz) + [section.key_heading] + _text(section.key), f"book order ({why})"


def rebuild(pages: list[Page], lex: Lexicon | None = None) -> ScanResult:
    """OCR pages -> chapters, with everything removed, decided or fixed recorded for the report."""
    result = ScanResult([])
    fixes: Counter = Counter()
    titles = contents_titles(pages)
    pages = strip_margins(pages, result.removed, titles)
    for page in [pg for pg in pages if any(_key(ln.text) == "contents" for ln in pg)]:
        result.removed.append(("contents page", _short(" ".join(ln.text for ln in page))))
    paras = paragraphs([pg for pg in pages if not any(_key(ln.text) == "contents" for ln in pg)], lex, fixes)
    if fixes:
        result.notes.append(f"OCR words fixed ({sum(fixes.values())}): "
                            + ", ".join(f"{f} ({n})" if n > 1 else f for f, n in sorted(fixes.items())))
    for section in _sections(paras, titles, result):
        lines, placement = chapter_text(section)
        if placement:
            result.notes.append(f"{section.title}: {placement}")
        for part, body in (("text", section.quiz), ("answers", section.key)):
            if body and not body[0].numbered and not re.match(r"[A-Z0-9\"“'‘(]", body[0].text):
                result.checks.append(f"{section.title}: first word of the {part} "
                                     f"(big first letter not read?): {body[0].text[:40]!r}")
        result.chapters.append(Chapter(section.title, "\n".join(lines)))
    return result


def load_scanned_pdf(path: Path, progress=None) -> tuple[Book, ScanResult]:
    """OCR a scanned PDF into a Book (title and author from metadata, or the file name)."""
    import pymupdf

    from .ocr import ocr_pdf

    with pymupdf.open(str(path)) as doc:
        md = doc.metadata or {}
    pages, cover = ocr_pdf(path, progress)
    result = rebuild(pages, load_lexicon())
    title = (md.get("title") or "").strip()
    if not title:  # file names from the internet carry "(Author) (site.com)" groups
        title = re.sub(r"\s*[(\[][^)\]]*[)\]]", "", path.stem).strip() or path.stem
    book = Book(title=title, author=(md.get("author") or "").strip(), chapters=result.chapters)
    if cover:
        book.cover, book.cover_ext = cover, ".png"
    return book, result
