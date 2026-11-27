"""Clean any supported ebook into a standard EPUB: one XHTML file per chapter (decisions D-019, D-020).

Usage:
    python -m desktop.normalize path/to/book.epub [--out path/to/book.std.epub] [--ignore-language]

Writes <name>.std.epub plus <name>.std.report.txt next to the source. Open the .std.epub in any
reader to check the chapters, fix it (e.g. in Sigil) if needed, then convert it:
    python -m desktop.build path/to/book.std.epub

Why: internet EPUBs (often Calibre conversions) split files by size, not by chapter, and their
tables of contents mix real chapters with footnote fragments. The cleaner finds real chapters by
confirming each TOC / contents-page entry against a heading in the text, cuts the book there,
drops front matter, contents pages, bibliography and index, and reports everything it removed.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import posixpath
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .language import check_language
from .ocr import is_scanned
from .parse import (MIN_CHAPTER_CHARS, Book, Chapter, _FRONT_MATTER_GUIDE, _is_front_matter_title, body_blocks,
                    clean_body, load_book, parse_html)
from .scanned import load_scanned_pdf

MARKER = "ebook-audio:normalized"
SOURCE_HASH = "ebook-audio:source-sha1"
MAX_TITLE_CHARS = 120  # longer "titles" are sentences that leaked into the TOC
MAX_JOIN = 3  # a heading may be split over this many consecutive lines ("THE SIX STEPS…" + "WRITING")
MIN_CONTENTS_LINKS = 5  # a contents page has at least this many paragraphs linking into other files
BACK_MATTER_TITLES = {"bibliography", "references", "index"}


@dataclass
class Block:
    file: str  # basename of the XHTML file
    lines: list[str]
    contents_entry: bool  # short paragraph that is (nearly) all link into another file
    lead: str = ""  # text of the element the block opens with, e.g. <span><b>1 Title</b></span> body…
    tag: str = ""  # element name, e.g. "h1" or "p"

    @property
    def text(self) -> str:
        return " ".join(self.lines)


@dataclass
class Report:
    source: str
    method: str = ""
    chapters: list[tuple[str, int]] = field(default_factory=list)  # (title, characters)
    removed: list[tuple[str, str]] = field(default_factory=list)  # (reason, first 80 chars)
    unconfirmed: list[str] = field(default_factory=list)  # TOC entries with no matching heading
    notes: list[str] = field(default_factory=list)  # decisions and things to check by hand

    def remove(self, reason: str, blocks: list[Block]) -> None:
        text = " ".join(b.text for b in blocks).strip()
        if text:
            self.removed.append((reason, text[:80] + ("…" if len(text) > 80 else "")))

    def render(self) -> str:
        out = [f"Normalized: {self.source}", f"Method: {self.method}", "", f"Chapters ({len(self.chapters)}):"]
        out += [f"  {i:3}. {t}  ({n} chars)" for i, (t, n) in enumerate(self.chapters, 1)]
        out += ["", f"Removed ({len(self.removed)}):"] + [f"  [{r}] {t}" for r, t in self.removed]
        if self.unconfirmed:
            out += ["", f"TOC entries ignored, no matching heading in the text ({len(self.unconfirmed)}):"]
            out += [f"  {t[:80]!r}" for t in self.unconfirmed]
        if self.notes:
            out += ["", f"Notes ({len(self.notes)}):"] + [f"  {n}" for n in self.notes]
        return "\n".join(out) + "\n"


def _key(text: str) -> str:
    """Comparison form of a title/heading: case-folded letters and digits only."""
    return " ".join(re.findall(r"[^\W_]+", text.casefold()))


_GLUED_FOOTNOTE = re.compile(r"[^\s\d]\d{1,3}$")  # 'address.”12', '1997)11': a footnote reference


def _plausible_title(title: str) -> bool:
    """Reject TOC entries that are really sentences or footnote fragments (Calibre leaks them)."""
    letters = re.findall(r"[^\W\d_]", title)
    return (len(title) <= MAX_TITLE_CHARS and len(letters) >= 3
            and not letters[0].islower()  # 'chapter and show how…', 'software': sentence fragments
            and not _GLUED_FOOTNOTE.search(title))


# ---------------------------------------------------------------- EPUB

def _epub_blocks(eb) -> tuple[list[Block], dict[str, int], dict[tuple[str, str], int], set[str]]:
    """All text blocks in spine order, plus: file -> first block index, (file, id) -> block index,
    and the set of files that are contents pages."""
    import ebooklib
    from bs4 import Tag

    blocks: list[Block] = []
    file_start: dict[str, int] = {}
    anchors: dict[tuple[str, str], int] = {}
    contents: set[str] = set()
    for idref, _ in eb.spine:
        item = eb.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        name = posixpath.basename(item.get_name())
        body = clean_body(item.get_content())
        if body is None:
            continue
        file_blocks = body_blocks(body)
        if not file_blocks:
            continue  # empty (e.g. only labelled front matter): it must not borrow the next file's start
        first = len(blocks)
        file_start.setdefault(name, first)
        order = {id(el): n for n, el in enumerate(body.descendants)}
        positions = []
        for el, lines in file_blocks:
            blocks.append(Block(name, lines, _is_contents_entry(el, lines), _lead(el), getattr(el, "name", "")))
            positions.append(order.get(id(el), -1))
        block_of = {id(el): first + k for k, (el, _) in enumerate(file_blocks)}
        for el in body.find_all(id=True):
            # The block containing the anchor, else the first block after it.
            idx = next((block_of[id(p)] for p in [el, *el.parents] if id(p) in block_of), None)
            if idx is None:
                pos = order.get(id(el), -1)
                idx = next((first + k for k, p in enumerate(positions) if p > pos), None)
            if idx is not None:
                anchors.setdefault((name, el["id"]), idx)
        linked = sum(b.contents_entry for b in blocks[first:])
        if linked >= MIN_CONTENTS_LINKS and linked >= 0.6 * (len(blocks) - first):
            contents.add(name)
    return blocks, file_start, anchors, contents


def _is_contents_entry(el, lines: list[str]) -> bool:
    """A contents-page line: short, and its text is (nearly) all link text pointing into another file.
    Endnotes that merely open with a backlink ("<a>1</a> long note text") are not."""
    from bs4 import Tag

    if not isinstance(el, Tag):
        return False
    text = " ".join(lines)
    if len(text) > 150:
        return False
    link_text = sum(len(a.get_text(" ", strip=True)) for a in el.find_all("a", href=True)
                    if not a["href"].startswith(("#", "http:", "https:", "mailto:")))
    return link_text >= 0.8 * len(text.replace(" ", "")) if text else False


def _lead(el) -> str:
    """Text of the first child element when the block starts with one (a heading inline with body text)."""
    from bs4 import NavigableString, Tag

    if not isinstance(el, Tag):
        return ""
    for child in el.children:
        if isinstance(child, NavigableString):
            if child.strip():
                return ""  # starts with plain text
            continue
        if isinstance(child, Tag):
            return re.sub(r"\s+", " ", child.get_text(" ")).strip()
    return ""


def _toc_entries(eb, blocks: list[Block], contents: set[str]) -> list[tuple[str, str]]:
    """(title, href) candidates from the navigation TOC and from links on contents pages."""
    import ebooklib
    from ebooklib import epub

    entries: list[tuple[str, str]] = []

    def walk(toc):
        for e in toc:
            if isinstance(e, tuple):
                if getattr(e[0], "href", None):
                    entries.append((e[0].title or "", e[0].href))
                walk(e[1])
            elif isinstance(e, epub.Link):
                entries.append((e.title or "", e.href))

    walk(eb.toc)
    for item in eb.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        if posixpath.basename(item.get_name()) not in contents:
            continue
        joined: list[tuple[str, str]] = []
        last_parent = None
        for a in parse_html(item.get_content()).find_all("a", href=True):
            text = re.sub(r"\s+", " ", a.get_text(" ")).strip()
            if not text:
                continue
            parent = a.find_parent(["p", "li", "div", "h1", "h2", "h3", "h4", "td"])
            # One title split over two links in the same paragraph; separate paragraphs are separate
            # entries even when they point at the same page anchor (part title + first chapter).
            if joined and joined[-1][1] == a["href"] and parent is last_parent:
                joined[-1] = (f"{joined[-1][0]} {text}", a["href"])
            else:
                joined.append((text, a["href"]))
            last_parent = parent
        entries += joined
    return entries


def _find_heading(blocks: list[Block], start: int, key: str, contents: set[str]) -> int | None:
    """First block at or after start that begins with key: its first line, or its first lines joined
    with the next block's (a heading split over lines/blocks, or sharing a block with body text)."""
    for i in range(start, len(blocks)):
        if blocks[i].file in contents:
            continue
        if blocks[i].lead and _key(blocks[i].lead) == key:
            return i
        lines = [ln for b in blocks[i:i + MAX_JOIN] if b.file not in contents for ln in b.lines][:MAX_JOIN]
        joined = ""
        for line in lines:
            joined = f"{joined} {line}".strip()
            k = _key(joined)
            if k == key:
                return i
            if len(k) >= len(key):
                break
    return None


_NUMBER = re.compile(r"^(\d+)(?:\.(\d+))?\s")


def _drop_subsections(entries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """'12.1 Develop Topics' is a section inside chapter '12 Develop Ideas', not a chapter of its own."""
    chapters = {m.group(1) for t, _ in entries if (m := _NUMBER.match(t.strip())) and not m.group(2)}
    return [(t, h) for t, h in entries
            if not ((m := _NUMBER.match(t.strip())) and m.group(2) and m.group(1) in chapters)]


def _normalize_epub(path: Path, report: Report) -> list[Chapter] | None:
    from ebooklib import epub

    eb = epub.read_epub(str(path), options={"ignore_ncx": False})
    blocks, file_start, anchors, contents = _epub_blocks(eb)
    guide_front = {posixpath.basename(g.get("href", "")) for g in eb.guide
                   if g.get("type", "").lower() in _FRONT_MATTER_GUIDE and "#" not in g.get("href", "")}

    starts: dict[int, str] = {}  # block index -> chapter title (entries landing on one block are deduped)
    for title, href in _drop_subsections(_toc_entries(eb, blocks, contents)):
        title = re.sub(r"\s+", " ", title).strip()
        key = _key(title)
        if not key:
            continue
        if not _plausible_title(title):
            report.unconfirmed.append(title)
            continue
        name, _, frag = href.partition("#")
        name = posixpath.basename(name)
        anchor = anchors.get((name, frag)) if frag else None
        idx = None
        if not frag and name in file_start and name not in contents and name not in guide_front:
            idx = file_start[name]  # a TOC entry for a whole file: the file is the chapter
        if idx is None:
            begin = anchor if anchor is not None else file_start.get(name, 0)
            idx = _find_heading(blocks, begin, key, contents)
            if idx is None:
                idx = _find_heading(blocks, 0, key, contents)
        if idx is None:
            report.unconfirmed.append(title)
            continue
        starts.setdefault(idx, title)

    if not starts:
        return None
    report.method = "chapters cut at headings confirmed from the table of contents / contents page"
    # A spine file that opens with a real <h1>-<h3> starts a chapter even when the TOC leaves it out
    # (sparse TOCs, or TOCs listing only parts). Files that start mid-text (Calibre splits) don't.
    for name, idx in file_start.items():
        block = blocks[idx]
        if idx not in starts and name not in contents and block.tag in {"h1", "h2", "h3"} \
                and _plausible_title(block.lines[0]):
            starts[idx] = block.lines[0]

    for name in contents:
        report.remove("contents page", [b for b in blocks if b.file == name])
    cuts = sorted(starts)
    report.remove("before the first chapter (front matter)",
                  [b for b in blocks[:cuts[0]] if b.file not in contents])
    chapters: list[Chapter] = []
    carry: list[str] = []
    for n, start in enumerate(cuts):
        end = cuts[n + 1] if n + 1 < len(cuts) else len(blocks)
        part = [b for b in blocks[start:end] if b.file not in contents]
        title = starts[start]
        if _is_front_matter_title(title):
            report.remove(f"front matter: {title}", part)
            continue
        if _key(title) in BACK_MATTER_TITLES:
            report.remove(f"back matter: {title}", part)
            continue
        lines = [line for b in part for line in b.lines]
        lead = part[0].lead if part else ""
        if lead and _key(lead) == _key(title) and lines[0].startswith(lead) and lines[0] != lead:
            lines[:1] = [lead, lines[0][len(lead):].strip()]  # heading gets its own line (and pause)
        lines = carry + lines
        if len("".join(lines)) < MIN_CHAPTER_CHARS and n + 1 < len(cuts):
            carry = lines  # a part heading with no text of its own: read it with the next chapter
            continue
        carry = []
        chapters.append(Chapter(title, "\n".join(lines)))
    return chapters


# ---------------------------------------------------------------- output

def write_std_epub(book: Book, out: Path, source_hash: str) -> None:
    from ebooklib import epub

    eb = epub.EpubBook()
    eb.set_identifier(f"ebook-audio-{source_hash}")
    eb.set_title(book.title)
    eb.set_language(book.language or "en")
    for name in [a.strip() for a in book.author.split(",") if a.strip()] or []:
        eb.add_author(name)
    eb.add_metadata(None, "meta", "", {"name": MARKER, "content": "1"})
    eb.add_metadata(None, "meta", "", {"name": SOURCE_HASH, "content": source_hash})
    if book.cover:
        eb.set_cover(f"images/cover{book.cover_ext}", book.cover, create_page=False)
    items = []
    for i, ch in enumerate(book.chapters):
        item = epub.EpubHtml(title=ch.title, file_name=f"text/ch{i:03d}.xhtml", lang=book.language or "en")
        paras = "".join(f"<p>{html.escape(line)}</p>" for line in ch.text.split("\n"))
        item.content = f"<html><head><title>{html.escape(ch.title)}</title></head><body>{paras}</body></html>"
        eb.add_item(item)
        items.append(item)
    eb.toc = [epub.Link(it.file_name, ch.title, f"ch{i:03d}") for i, (it, ch) in enumerate(zip(items, book.chapters))]
    eb.add_item(epub.EpubNcx())
    eb.add_item(epub.EpubNav())
    eb.spine = items
    tmp = out.with_suffix(".tmp")
    epub.write_epub(str(tmp), eb)
    tmp.replace(out)


def normalize(source: str | Path, out: str | Path | None = None, ignore_language: bool = False,
              progress=None) -> tuple[Path, Report]:
    """Write a standard EPUB for source. Returns (path written, report). Raises ValueError.
    progress(done_pages, total_pages) is called while a scanned PDF is read with OCR."""
    source = Path(source)
    out_arg = out
    out = Path(out) if out else source.with_name(source.name.rsplit(".", 1)[0].removesuffix(".std") + ".std.epub")
    report = Report(str(source))
    scanned = source.suffix.lower() == ".pdf" and is_scanned(source)
    if scanned:  # before load_book: an image-only scan has no text layer to load (D-021)
        book, scan = load_scanned_pdf(source, progress)
        report.removed += scan.removed
        report.unconfirmed += scan.unconfirmed
        report.notes += scan.notes
    else:
        book = load_book(source)  # metadata, cover, front matter rules, and the fallback chapters
    if not ignore_language:
        check_language(book)  # refuse before the user spends time reviewing
    if scanned:
        report.method = ("scanned PDF read with OCR (docTR), each two-page scan split at the gutter; chapters "
                         "cut at headings confirmed by the book's contents page (D-021, D-022)")
    elif book.normalized and out_arg is None:
        # Never rewrite a .std.epub in place: the user may have edited it in Sigil.
        report.method = "already a standard EPUB: nothing written"
        report.chapters = [(c.title, len(c.text)) for c in book.chapters]
        return source, report
    if scanned:
        pass  # chapters already rebuilt from the OCR
    elif book.normalized:
        report.method = "already a standard EPUB: chapters kept as they are"
    elif source.suffix.lower() == ".epub":
        chapters = _normalize_epub(source, report)
        if chapters is None:
            report.method = "no table-of-contents entry matched a heading: one chapter per file (fallback)"
        else:
            book.chapters = [c for c in chapters if len(c.text.strip()) >= MIN_CHAPTER_CHARS]
    else:
        report.method = f"{source.suffix.lower()} repackaged with the current parser (no cleaning yet)"
    # Same rule parse.py applies when reading the result, so the report shows what will be converted.
    kept = []
    for ch in book.chapters:
        if _is_front_matter_title(ch.title):
            report.removed.append((f"front matter: {ch.title}", ch.text[:80]))
        else:
            kept.append(ch)
    book.chapters = kept
    if not book.chapters:
        raise ValueError("No readable text left after cleaning.")
    report.chapters = [(c.title, len(c.text)) for c in book.chapters]
    source_hash = book.source_hash or hashlib.sha1(source.read_bytes()).hexdigest()
    write_std_epub(book, out, source_hash)
    out.with_name(out.name.removesuffix(".epub") + ".report.txt").write_text(report.render(), encoding="utf-8")
    return out, report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Clean an ebook into a standard EPUB for review before converting.")
    ap.add_argument("source")
    ap.add_argument("--out", help="output path (default: <name>.std.epub next to the source)")
    ap.add_argument("--ignore-language", action="store_true", help="skip the English check")
    args = ap.parse_args(argv)

    def progress(done: int, total: int) -> None:
        sys.stderr.write(f"\rReading scanned pages with OCR: {done}/{total}")
        if done == total:
            sys.stderr.write("\n")

    try:
        out, report = normalize(args.source, args.out, args.ignore_language, progress)
    except ValueError as e:
        sys.exit(f"error: {e}")
    print(report.render())
    if out == Path(args.source):
        print(f"{out} is already cleaned; nothing written. Convert it with: python -m desktop.build \"{out}\"")
        return
    print(f"Wrote {out}\nCheck it in an ebook reader, then: python -m desktop.build \"{out}\"")


if __name__ == "__main__":
    main()
