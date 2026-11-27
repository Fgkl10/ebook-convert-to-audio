"""Build small synthetic EPUBs for parser tests.

All text is made up, so nothing copyrighted ends up in this public repository (see
desktop/docs/decisions.md D-014). Each builder mirrors a structure seen in real commercial
EPUBs: front matter, nested TOC, files in a Text/ subfolder, footnote markers, covers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ebooklib import epub

from desktop.parse import MIN_CHAPTER_CHARS

FILLER = "The river ran quietly past the old mill while the morning light grew warmer. "
# 1x1 PNG / minimal JPEG header bytes: enough for the parser, which only copies cover bytes.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)
JPG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16 + b"\xff\xd9"


@dataclass
class Page:
    file_name: str
    body: str  # inner HTML of <body>
    toc_title: str | None = None  # None: not in the TOC
    allow_short: bool = False  # set for pages meant to be dropped by MIN_CHAPTER_CHARS
    epub_type: str | None = None  # label on a wrapping <section>, e.g. "copyright-page"
    guide_type: str | None = None  # OPF <guide> reference type for this page, e.g. "copyright-page"


@dataclass
class Spec:
    title: str = "Synthetic Book"
    author: str = "Test Author"
    language: str = "en"  # dc:language metadata
    pages: list[Page] = field(default_factory=list)
    nested_toc: bool = False  # wrap TOC entries in a Section, like (Section, [Link, ...])
    cover: str | None = None  # "item": proper cover item; "named-image": image called cover.png
    toc: list[tuple[str, str]] | None = None  # explicit (href, title) entries, e.g. "book.xhtml#c1"


def para(n: int = 2) -> str:
    return "<p>" + FILLER * n + "</p>"


def _text_len(body: str) -> int:
    from bs4 import BeautifulSoup

    return len(BeautifulSoup(body, "lxml").get_text(" ", strip=True))


def build_epub(path: Path, spec: Spec) -> Path:
    book = epub.EpubBook()
    book.set_identifier(f"synthetic-{spec.title}")
    book.set_title(spec.title)
    book.set_language(spec.language)
    if spec.author:
        book.add_author(spec.author)

    if spec.cover == "item":
        book.set_cover("images/cover.jpg", JPG_BYTES, create_page=False)
    elif spec.cover == "named-image":
        book.add_item(epub.EpubImage(uid="img-cover", file_name="images/cover.png",
                                     media_type="image/png", content=PNG_BYTES))

    items = []
    for i, page in enumerate(spec.pages):
        # Guard against fixtures that the parser would silently drop.
        if not page.allow_short and _text_len(page.body) < MIN_CHAPTER_CHARS:
            raise ValueError(f"page {page.file_name} is shorter than MIN_CHAPTER_CHARS; set allow_short")
        item = epub.EpubHtml(title=page.toc_title or f"p{i}", file_name=page.file_name, lang="en")
        body = f'<section epub:type="{page.epub_type}">{page.body}</section>' if page.epub_type else page.body
        item.content = f"<html><body>{body}</body></html>"
        book.add_item(item)
        items.append((page, item))

    if spec.toc is not None:
        links = [epub.Link(href, title, f"toc{i}") for i, (href, title) in enumerate(spec.toc)]
    else:
        links = [epub.Link(item.file_name, page.toc_title, f"toc{i}")
                 for i, (page, item) in enumerate(items) if page.toc_title]
    if spec.nested_toc and links:
        book.toc = [(epub.Section("Part One", href=links[0].href), links)]
    else:
        book.toc = links

    book.guide = [{"href": item.file_name, "title": page.toc_title or "", "type": page.guide_type}
                  for page, item in items if page.guide_type]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + [item for _, item in items]
    epub.write_epub(str(path), book)
    return path


# ---------------------------------------------------------------- ready-made specs

BLURB = ("<p>Over a million readers have followed the river.</p><p>" + FILLER * 2 + "</p>")


def novel_spec() -> Spec:
    """Labelled front matter + preface + three chapters in Text/, nested TOC, footnotes, cover item.

    Front matter is found three ways: a labelled half title holding a long blurb (like real books),
    a labelled copyright page, and an unlabelled page titled exactly "Contents".
    """
    return Spec(
        title="The Quiet Mill",
        author="Ada Fictional",
        nested_toc=True,
        cover="item",
        pages=[
            Page("Text/halftitle.xhtml", BLURB, toc_title="Half Title", epub_type="halftitlepage"),
            Page("Text/copyright.xhtml",
                 "<p>Copyright 2026 Ada Fictional. All rights reserved. No part of this book may be "
                 "reproduced without permission. First published 2026.</p>",
                 toc_title="Copyright", epub_type="copyright-page"),
            Page("Text/contents.xhtml",
                 "<p>Contents</p><p>1 The River</p><p>2 The Mill</p><p>3 The Storm</p>"
                 "<p>Notes and acknowledgements follow the final chapter.</p>",
                 toc_title="Contents"),
            Page("Text/preface.xhtml", "<h1>Preface</h1>" + para(), toc_title="Preface", epub_type="preface"),
            Page("Text/ch1.xhtml",
                 "<h1>One</h1><p>The river remembered everything<sup><a href=\"#fn1\">1</a></sup> "
                 "that had ever fallen into it.</p>" + para(),
                 toc_title="1 The River"),
            Page("Text/ch2.xhtml",
                 '<h1>Two</h1><span epub:type="pagebreak" role="doc-pagebreak" id="p7"/>' + para(3),
                 toc_title="2 The Mill", epub_type="chapter"),
            Page("Text/ch3.xhtml",
                 "<h1>Three</h1><p>Thunder rolled<sup>2</sup> over the hills.</p>" + para(),
                 toc_title="3 The Storm"),
        ],
    )


def untitled_spec() -> Spec:
    """No TOC at all: titles must come from headings, then "Section N"."""
    return Spec(
        title="No Contents",
        cover="named-image",
        pages=[
            Page("a.xhtml", "<h2>Opening Heading</h2>" + para()),
            Page("b.xhtml", para()),  # no heading → "Section 2"
            Page("c.xhtml", "<p>Tiny.</p>", allow_short=True),  # dropped
        ],
    )


def guide_spec() -> Spec:
    """No epub:type labels: front matter known only from the OPF guide; near-miss titles are kept."""
    return Spec(
        title="Guide Only",
        pages=[
            Page("legal.xhtml", "<p>All rights reserved by the imaginary publisher of this book.</p>",
                 toc_title="Legal Notice", guide_type="copyright-page"),
            Page("law.xhtml", "<h1>Copyright Law</h1>" + para(), toc_title="Copyright Law"),
            Page("contents-of-the-heart.xhtml", para(), toc_title="Contents of the Heart"),
        ],
    )


def single_file_spec(variant: str) -> Spec:
    """Whole book in one XHTML file, as Word/Calibre conversions often produce.

    "labelled": a labelled copyright <section> before chapter 1 in the same file.
    "toc-title": the first TOC entry into the file is "Title Page" (anchor), then "Chapter One".
    "guide": the OPF guide marks the file as copyright-page, but the TOC points to #c1 inside it.
    """
    chapter = f'<section id="c1"><h1>Chapter One</h1>{para()}</section>'
    copyright_text = "<p>All rights reserved by the imaginary publisher of this book.</p>"
    if variant == "labelled":
        body = f'<section epub:type="copyright-page">{copyright_text}</section>{chapter}'
        page, toc = Page("book.xhtml", body), [("book.xhtml#c1", "Chapter One")]
    elif variant == "toc-title":
        body = f'<div id="t"><p>Single</p></div>{chapter}'
        page, toc = Page("book.xhtml", body), [("book.xhtml#t", "Title Page"), ("book.xhtml#c1", "Chapter One")]
    elif variant == "guide":
        body = f"<div>{copyright_text}</div>{chapter}"
        page, toc = Page("book.xhtml", body, guide_type="copyright-page"), [("book.xhtml#c1", "Chapter One")]
    else:
        raise ValueError(variant)
    return Spec(title="Single File", pages=[page], toc=toc)


def empty_spec() -> Spec:
    return Spec(title="Empty", pages=[Page("a.xhtml", "<p>   </p>", allow_short=True)])
