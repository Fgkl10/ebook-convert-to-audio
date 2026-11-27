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
# (epub:type / ARIA role on page-level elements, OPF <guide> types) or an exact page title.
_FRONT_MATTER_TYPES = {"cover", "titlepage", "halftitlepage", "copyright-page", "toc"}
_FRONT_MATTER_ROLES = {"doc-cover", "doc-toc"}
_FRONT_MATTER_GUIDE = {"cover", "title-page", "copyright-page", "toc"}
_FRONT_MATTER_TITLES = {"copyright", "contents", "table of contents", "title page", "half title", "half title page"}
_PAGE_LEVEL_TAGS = ["body", "section", "div", "nav", "article"]


def _front_matter_labels(soup) -> set[str]:
    """epub:type / role tokens on page-level elements that mark the page as front matter."""
    found: set[str] = set()
    for el in soup.find_all(_PAGE_LEVEL_TAGS):
        found |= set((el.get("epub:type") or "").split()) & _FRONT_MATTER_TYPES
        found |= set((el.get("role") or "").split()) & _FRONT_MATTER_ROLES
    return found


def _is_front_matter_title(title: str | None) -> bool:
    norm = re.sub(r"[\s\-_]+", " ", (title or "").lower()).strip(" .:")
    return norm in _FRONT_MATTER_TITLES


def _html_to_paragraphs(html: bytes) -> tuple[list[str], str | None, set[str]]:
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

    # EPUB chapters are XHTML. The lenient HTML parser is deliberate (malformed markup is common in
    # real books, and a strict XML parse can lose text), so silence its "this looks like XML" warning
    # (decision D-015).
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")
    labels = _front_matter_labels(soup)
    for tag in soup(["script", "style", "head", "nav"]):
        tag.decompose()
    # Footnote reference markers like <sup><a href="#fn1">1</a></sup> read badly.
    for sup in soup.find_all("sup"):
        if sup.find("a") or sup.get_text(strip=True).isdigit():
            sup.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")

    body = soup.body or soup
    heading = None
    paragraphs: list[str] = []
    blocks = body.find_all(_BLOCK_TAGS)
    leaf_blocks = [b for b in blocks if not b.find(_BLOCK_TAGS)]
    if leaf_blocks:
        for b in leaf_blocks:
            for line in b.get_text("").split("\n"):
                line = re.sub(r"\s+", " ", line).strip()
                if line:
                    paragraphs.append(line)
                    if heading is None and b.name in _HEADINGS:
                        heading = line
    else:
        for line in body.get_text("\n").split("\n"):
            line = re.sub(r"\s+", " ", line).strip()
            if line:
                paragraphs.append(line)
    return paragraphs, heading, labels


def _flatten_toc(toc, out: dict[str, str]) -> None:
    from ebooklib import epub

    for entry in toc:
        if isinstance(entry, tuple):  # (Section, [children])
            section, children = entry
            if getattr(section, "href", None):
                out.setdefault(section.href.split("#")[0], section.title)
            _flatten_toc(children, out)
        elif isinstance(entry, epub.Link):
            out.setdefault(entry.href.split("#")[0], entry.title)


def _load_epub(path: Path) -> Book:
    import ebooklib
    from ebooklib import epub

    eb = epub.read_epub(str(path), options={"ignore_ncx": False})

    def meta(name: str) -> str:
        vals = eb.get_metadata("DC", name)
        return vals[0][0].strip() if vals else ""

    book = Book(title=meta("title") or path.stem, author=meta("creator"))

    toc_titles: dict[str, str] = {}
    _flatten_toc(eb.toc, toc_titles)
    # TOC hrefs are relative to the nav file; normalise to basenames for matching.
    toc_by_name = {posixpath.basename(k): v for k, v in toc_titles.items()}
    guide_front = {posixpath.basename(g.get("href", "").split("#")[0])
                   for g in eb.guide if g.get("type", "").lower() in _FRONT_MATTER_GUIDE}

    for idref, _linear in eb.spine:
        item = eb.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        paragraphs, heading, labels = _html_to_paragraphs(item.get_content())
        if not paragraphs:
            continue
        name = item.get_name()
        title = toc_titles.get(name) or toc_by_name.get(posixpath.basename(name)) or heading
        if labels or posixpath.basename(name) in guide_front or _is_front_matter_title(title):
            continue  # front matter: not read aloud
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
