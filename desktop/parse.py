"""Read EPUB / TXT / PDF into a uniform Book structure.

Chapter text uses one paragraph per line ("\n"-separated), which is what
segment.split_text expects.
"""
from __future__ import annotations

import posixpath
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chapter:
    title: str
    text: str


@dataclass
class Book:
    title: str
    author: str
    chapters: list[Chapter] = field(default_factory=list)
    cover: bytes | None = None
    cover_ext: str = ".jpg"
    language: str = ""  # from metadata if the format has it; only a hint (see desktop/language.py)
    normalized: bool = False  # written by desktop.normalize (a standard EPUB)
    source_hash: str = ""  # for a standard EPUB: sha1 of the original file, so book_id stays stable


MIN_CHAPTER_CHARS = 40  # skip cover pages, blank separators, etc.


def load_book(path: str | Path) -> Book:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".epub":
        book = _load_epub(path)
    elif ext == ".pdf":
        book = _load_pdf(path)
    elif ext in (".txt", ".md"):
        book = _load_txt(path)
    else:
        raise ValueError(f"Unsupported file type: {ext} (use .epub, .pdf or .txt)")
    book.chapters = [c for c in book.chapters if len(c.text.strip()) >= MIN_CHAPTER_CHARS]
    if not book.chapters:
        raise ValueError("No readable text found in this book.")
    return book


# ---------------------------------------------------------------- EPUB

_BLOCK_TAGS = ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "dd", "dt", "td", "figcaption"]
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

# Front matter that is never read aloud (decision D-016). Detected from the book's own labels
# (epub:type / ARIA role on page-level elements, OPF <guide> types) or exact TOC titles.
# Decisions are per page, not per file: one XHTML file can hold front matter and real chapters.
_FRONT_MATTER_TYPES = {"cover", "titlepage", "halftitlepage", "copyright-page", "toc"}
_FRONT_MATTER_ROLES = {"doc-cover", "doc-toc"}
_FRONT_MATTER_GUIDE = {"cover", "title-page", "copyright-page", "toc"}
_FRONT_MATTER_TITLES = {"copyright", "copyright page", "contents", "table of contents", "title page", "half title",
                        "half title page", "cover", "dedication", "dedication page"}
_PAGE_LEVEL_TAGS = ["body", "section", "div", "nav", "article"]


def _is_front_matter_element(el) -> bool:
    return bool(set((el.get("epub:type") or "").split()) & _FRONT_MATTER_TYPES
                or set((el.get("role") or "").split()) & _FRONT_MATTER_ROLES)


def _is_front_matter_title(title: str | None) -> bool:
    norm = re.sub(r"[\s\-_]+", " ", (title or "").lower()).strip(" .:")
    return norm in _FRONT_MATTER_TITLES


def parse_html(html: bytes):
    """BeautifulSoup for one EPUB XHTML file. Every EPUB parse goes through here."""
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

    # EPUB chapters are XHTML. The lenient HTML parser is deliberate (malformed markup is common in
    # real books, and a strict XML parse can lose text), so silence its "this looks like XML" warning
    # (decision D-015).
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        return BeautifulSoup(html, "lxml")


_NOTE_MARK = re.compile(r"\[?\d{1,3}\]?|[*†‡§]{1,3}")
# A number right after one of these words is a cross-reference ("Chapters 9 through 11, 24, and 33",
# "Figure 5", "page 12"), not a note: it stays.
_POINTER = re.compile(r"(?:\b(?:chapters?|ch\.|sections?|parts?|figures?|figs?\.|tables?|pages?|pp?\.|lens(?:es)?|"
                      r"steps?|rules?|tips?|appendix|appendices|volumes?|vol\.|nos?\.|numbers?)|#)"
                      r"(?:[\s,()–\-]|\d|\band\b|\bor\b|\bthrough\b|\bto\b)*$", re.IGNORECASE)


def _is_note_ref(a) -> bool:
    """A link to a note: its text is only a short number or a note symbol, and it sits in running text
    (not alone on its line, as a contents entry or page number is) without a pointer word before it."""
    from bs4 import NavigableString

    text = a.get_text(strip=True)
    if not _NOTE_MARK.fullmatch(text) or a["href"].startswith(("http:", "https:", "mailto:")):
        return False
    if "index" in (a.get("epub:type") or ""):  # index locators: the index is removed as back matter anyway
        return False
    block = a.find_parent(["p", "li", "div", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"])
    if block is None or block.get_text(strip=True) == text:
        return False
    before = ""
    for prev in a.previous_elements:
        if isinstance(prev, NavigableString):
            before = str(prev) + before
            if len(before) > 60:
                break
        if prev is block:
            break
    return not _POINTER.search(before[-60:])


_NOTE_TYPES = {"footnote", "footnotes", "endnote", "endnotes", "rearnote", "rearnotes", "note"}
_NOTE_ROLES = {"doc-footnote", "doc-endnote", "doc-endnotes"}
_INLINE_WRAPPERS = {"span", "sup", "b", "strong", "em", "i", "small", "font"}


def _opening_link(el):
    """The link a block opens with, looking through inline wrappers ('<p>\xa0<span><a>1</a></span> The…'),
    or None when the block opens with text or another element."""
    from bs4 import NavigableString, Tag

    for child in el.children:
        if isinstance(child, NavigableString):
            if child.strip():
                return None
            continue
        if isinstance(child, Tag):
            if child.name == "a":
                return child
            return _opening_link(child) if child.name in _INLINE_WRAPPERS else None
    return None


def _is_note_paragraph(el) -> bool:
    """A footnote or endnote text: labelled as one, or a paragraph opening with a number-only link back
    to its reference ('1 The research on willpower…') followed by the note itself (D-027)."""
    if set((el.get("epub:type") or "").split()) & _NOTE_TYPES or set((el.get("role") or "").split()) & _NOTE_ROLES:
        return True
    if el.name not in ("p", "li", "div", "aside"):
        return False
    if el.name in ("div", "aside") and el.find(["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"]):
        return False  # a container (a whole Calibre chapter can open with a link): never drop it
    a = _opening_link(el)
    if a is None or not a.get("href") or not _NOTE_MARK.fullmatch(a.get_text(strip=True)):
        return False
    return len(el.get_text(" ", strip=True)) > len(a.get_text(strip=True)) + 2  # more than the number itself


MAX_NOTE_LINES = 8  # a note may run on over this many following <p> lines (Calibre: one per printed line)


def _inline_classes(el) -> set[str]:
    return {c for d in el.find_all(True) for c in (d.get("class") or [])}


def _all_in_style(line, classes: set[str]) -> bool:
    """Nearly all of the line's text sits in inline elements styled like the note (its small print)."""
    marked = [d for d in line.find_all(True) if set(d.get("class") or []) & classes]
    ids = {id(d) for d in marked}
    # count each styled run once: skip elements nested inside another styled element
    top = [d for d in marked if not any(id(p) in ids for p in d.parents)]
    styled = sum(len(d.get_text(strip=True)) for d in top)
    return styled >= 0.9 * len(line.get_text(strip=True))


def _note_continuation(el) -> list:
    """The <p> lines that continue a footnote paragraph (Calibre: one per printed line): following
    siblings styled like the note's own number (its small print), up to an empty paragraph, the next
    note, another kind of element or the end of the parent. Without such an end within MAX_NOTE_LINES,
    nothing is taken, and a line in body style is never taken: body text must never be lost with a note."""
    from bs4 import Tag

    classes = _inline_classes(el)
    lines, sib = [], el.next_sibling
    while sib is not None:
        if isinstance(sib, Tag):
            if sib.name != el.name or not sib.get_text(strip=True) or _is_note_paragraph(sib):
                return lines
            if not classes or not _all_in_style(sib, classes):
                return []  # a line in another style before the note ended: take nothing
            lines.append(sib)
            if len(lines) > MAX_NOTE_LINES:
                return []
        elif str(sib).strip():
            return lines  # loose text between paragraphs: stop
        sib = sib.next_sibling
    return lines


def clean_body(html: bytes, stats: dict | None = None):
    """Parse one XHTML file and strip what is never read aloud. Returns the <body> (or None when the
    whole file is labelled front matter). Shared with normalize.py so both see the same text.
    `stats`, when given, counts what was removed ('note paragraphs')."""
    soup = parse_html(html)
    body = soup.body or soup
    if body.name == "body" and _is_front_matter_element(body):
        return None
    # Remove only the labelled front-matter elements; the rest of the file is still read.
    for el in body.find_all(_PAGE_LEVEL_TAGS):
        if not el.decomposed and _is_front_matter_element(el):
            el.decompose()
    for tag in soup(["script", "style", "head", "nav"]):
        tag.decompose()
    # Footnote and endnote texts (before the markers go: a note is recognised by its opening backlink).
    notes = 0
    for el in body.find_all(["p", "li", "div", "aside", "section", "ol", "ul"]):
        if not el.decomposed and _is_note_paragraph(el):
            for line in _note_continuation(el) if el.name == "p" else []:
                line.decompose()
            el.decompose()
            notes += 1
    if stats is not None:
        stats["note paragraphs"] = stats.get("note paragraphs", 0) + notes
    # Footnote reference markers like <sup><a href="#fn1">1</a></sup> read badly.
    for sup in soup.find_all("sup"):
        if sup.find("a") or sup.get_text(strip=True).isdigit():
            sup.decompose()
    # The same markers without <sup> (Calibre styles them with a class): "…the community. 2 It was"
    for a in soup.find_all("a", href=True):
        if not a.decomposed and _is_note_ref(a):
            a.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return body


def _lines(text: str) -> list[str]:
    out = []
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            out.append(line)
    return out


def body_blocks(body) -> list[tuple[object, list[str]]]:
    """Leaf text blocks of a cleaned body in reading order: (element, its paragraph lines).
    A body without block tags becomes one pseudo-block (element = body)."""
    leaf = [b for b in body.find_all(_BLOCK_TAGS) if not b.find(_BLOCK_TAGS)]
    if not leaf:
        lines = _lines(body.get_text("\n"))
        return [(body, lines)] if lines else []
    out = []
    for b in leaf:
        lines = _lines(b.get_text(""))
        if lines:
            out.append((b, lines))
    return out


def _html_to_paragraphs(html: bytes) -> tuple[list[str], str | None]:
    body = clean_body(html)
    if body is None:
        return [], None
    heading = None
    paragraphs: list[str] = []
    for el, lines in body_blocks(body):
        paragraphs.extend(lines)
        if heading is None and getattr(el, "name", None) in _HEADINGS:
            heading = lines[0]
    return paragraphs, heading


def _flatten_toc(toc, out: dict[str, list[str]], anchored: set[str]) -> None:
    """out: file name -> every TOC title pointing into it, in order (fragments stripped).
    anchored: files that some TOC entry points into the middle of (href has a #fragment)."""
    from ebooklib import epub

    def add(href: str, title: str) -> None:
        name, _, frag = href.partition("#")
        out.setdefault(name, []).append(title)
        if frag:
            anchored.add(posixpath.basename(name))

    for entry in toc:
        if isinstance(entry, tuple):  # (Section, [children])
            section, children = entry
            if getattr(section, "href", None):
                add(section.href, section.title)
            _flatten_toc(children, out, anchored)
        elif isinstance(entry, epub.Link):
            add(entry.href, entry.title)


def _load_epub(path: Path) -> Book:
    import ebooklib
    from ebooklib import epub

    eb = epub.read_epub(str(path), options={"ignore_ncx": False})

    def meta(name: str) -> str:
        vals = eb.get_metadata("DC", name)
        return vals[0][0].strip() if vals else ""

    creators = [v[0].strip() for v in eb.get_metadata("DC", "creator") if v[0]]
    book = Book(title=meta("title") or path.stem, author=", ".join(creators), language=meta("language"))
    opf = {attrs.get("name"): attrs.get("content", "") for _, attrs in eb.get_metadata("OPF", "meta")}
    book.normalized = opf.get("ebook-audio:normalized") == "1"
    book.source_hash = opf.get("ebook-audio:source-sha1", "")

    toc_titles: dict[str, list[str]] = {}
    toc_anchored: set[str] = set()
    _flatten_toc(eb.toc, toc_titles, toc_anchored)
    # TOC hrefs are relative to the nav file; normalise to basenames for matching.
    toc_by_name: dict[str, list[str]] = {}
    for k, v in toc_titles.items():
        toc_by_name.setdefault(posixpath.basename(k), []).extend(v)
    # Guide entries with a #fragment point at part of a file, so they never skip a whole file.
    guide_front = {posixpath.basename(g.get("href", "")) for g in eb.guide
                   if g.get("type", "").lower() in _FRONT_MATTER_GUIDE and "#" not in g.get("href", "")}

    for idref, _linear in eb.spine:
        item = eb.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        paragraphs, heading = _html_to_paragraphs(item.get_content())
        if not paragraphs:
            continue  # empty, or only labelled front matter
        name = item.get_name()
        titles = toc_titles.get(name) or toc_by_name.get(posixpath.basename(name)) or []
        real_titles = [t for t in titles if not _is_front_matter_title(t)]
        if titles and not real_titles:
            continue  # every TOC entry into this file is front matter
        base = posixpath.basename(name)
        if base in guide_front and base not in toc_anchored:
            continue  # guide marks the whole file; no TOC entry points into the middle of it
        title = real_titles[0] if real_titles else heading
        book.chapters.append(Chapter(title=title or "", text="\n".join(paragraphs)))

    for i, ch in enumerate(book.chapters):
        if not ch.title:
            ch.title = f"Section {i + 1}"

    cover = None
    for item in eb.get_items_of_type(ebooklib.ITEM_COVER):
        cover = item
        break
    if cover is None:
        for item in eb.get_items_of_type(ebooklib.ITEM_IMAGE):
            if "cover" in item.get_name().lower() or "cover" in (item.get_id() or "").lower():
                cover = item
                break
    if cover is not None:
        book.cover = cover.get_content()
        book.cover_ext = Path(cover.get_name()).suffix.lower() or ".jpg"
    return book


# ---------------------------------------------------------------- TXT

_CHAPTER_LINE = re.compile(
    r"^\s*((chapter|part|book)\s+([0-9]+|[ivxlcdm]+|[a-z\-]+)\b.*|prologue|epilogue)\s*$",
    re.IGNORECASE,
)
_TXT_PART_CHARS = 20000


def _load_txt(path: Path) -> Book:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    text = text.replace("\r\n", "\n")
    # Paragraphs are separated by blank lines; single newlines are hard wraps.
    paragraphs = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    paragraphs = [p for p in paragraphs if p]

    book = Book(title=path.stem, author="")
    current: Chapter | None = None
    for p in paragraphs:
        if len(p) < 80 and _CHAPTER_LINE.match(p):
            current = Chapter(title=p, text=p)
            book.chapters.append(current)
        else:
            if current is None:
                current = Chapter(title="Opening", text="")
                book.chapters.append(current)
            current.text = f"{current.text}\n{p}" if current.text else p

    if len(book.chapters) <= 1:  # no headings found: chunk into parts
        book.chapters = []
        buf: list[str] = []
        size = 0
        for p in paragraphs:
            buf.append(p)
            size += len(p)
            if size >= _TXT_PART_CHARS:
                book.chapters.append(Chapter(f"Part {len(book.chapters) + 1}", "\n".join(buf)))
                buf, size = [], 0
        if buf:
            book.chapters.append(Chapter(f"Part {len(book.chapters) + 1}", "\n".join(buf)))
    return book


# ---------------------------------------------------------------- PDF

_PDF_PAGES_PER_PART = 15


def _pdf_page_paragraphs(page) -> list[str]:
    out = []
    for block in page.get_text("blocks"):
        if block[6] != 0:  # image block
            continue
        txt = block[4]
        txt = re.sub(r"-\n(?=[a-z])", "", txt)  # de-hyphenate line breaks
        txt = re.sub(r"\s*\n\s*", " ", txt).strip()
        if not txt or re.fullmatch(r"\d+", txt):  # skip bare page numbers
            continue
        out.append(txt)
    return out


def _load_pdf(path: Path) -> Book:
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    md = doc.metadata or {}
    book = Book(title=(md.get("title") or "").strip() or path.stem, author=(md.get("author") or "").strip())

    toc = [(title, page) for level, title, page in doc.get_toc() if level == 1 and page >= 1]
    if len(toc) >= 2:
        bounds = [(t, p - 1) for t, p in toc]
        if bounds[0][1] > 0:
            bounds.insert(0, ("Front matter", 0))
        for i, (title, start) in enumerate(bounds):
            end = bounds[i + 1][1] if i + 1 < len(bounds) else doc.page_count
            paras = [p for n in range(start, max(start, end)) for p in _pdf_page_paragraphs(doc[n])]
            book.chapters.append(Chapter(title.strip(), "\n".join(paras)))
    else:
        for start in range(0, doc.page_count, _PDF_PAGES_PER_PART):
            end = min(start + _PDF_PAGES_PER_PART, doc.page_count)
            paras = [p for n in range(start, end) for p in _pdf_page_paragraphs(doc[n])]
            book.chapters.append(Chapter(f"Pages {start + 1}–{end}", "\n".join(paras)))

    pix = doc[0].get_pixmap(dpi=60) if doc.page_count else None
    if pix is not None:
        book.cover = pix.tobytes("png")
        book.cover_ext = ".png"
    return book
