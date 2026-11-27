"""Build small synthetic EPUBs for parser tests.

All text is made up, so nothing copyrighted ends up in this public repository (see
desktop/docs/decisions.md D-014). Each builder mirrors a structure seen in real commercial
EPUBs: front matter, nested TOC, files in a Text/ subfolder, footnote markers, covers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ebooklib import epub

from desktop.core.parse import MIN_CHAPTER_CHARS

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
    toc_tree: list | None = None  # explicit nested TOC: (href, title, [children]) tuples


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
    if spec.toc_tree is not None:
        count = iter(range(10_000))

        def node(href, title, kids):
            if not kids:
                return epub.Link(href, title, f"toc{next(count)}")
            return (epub.Section(title, href=href), [node(*k) for k in kids])
        book.toc = [node(*n) for n in spec.toc_tree]
    elif spec.nested_toc and links:
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


def calibre_spec() -> Spec:
    """Shaped like a Calibre conversion found online (see How to Take Smart Notes in D-020):
    files split by size, page-marker anchors that are not at the headings, a contents page whose
    links share anchors, headings that open a paragraph, a heading split over two paragraphs,
    footnote junk in the navigation TOC, a chapter missing from it, a short part heading,
    unlabelled front matter, and a bibliography. Class names are random on purpose."""
    link = '<span class="k2"><a href="split_001.xhtml" class="w5"><b class="v1">{}</b></a></span>'
    return Spec(
        title="The Quiet Mill",
        author="Ada Fictional",
        pages=[
            Page("Text/split_000.xhtml",
                 '<p class="q1">Ada Fictional</p><p class="q1">The Quiet Mill</p>'
                 '<p class="q3">All rights reserved by the imaginary publisher of this book.</p>'),
            Page("Text/split_001.xhtml",
                 '<h2 class="h7">CONTENTS</h2>'
                 '<p class="c4"><a href="split_002.xhtml#pg_1">PREFACE</a></p>'
                 '<p class="c4"><a href="split_002.xhtml#pg_3">1 The River</a></p>'
                 '<p class="c4"><a href="split_003.xhtml#pg_9">PART TWO</a></p>'
                 '<p class="c4"><a href="split_003.xhtml#pg_9">2 The Mill</a></p>'
                 '<p class="c4"><a href="split_003.xhtml#pg_12">3 The</a> <a href="split_003.xhtml#pg_12">Storm</a></p>'
                 '<p class="c4"><a href="split_004.xhtml">BIBLIOGRAPHY</a></p>'),
            Page("Text/split_002.xhtml",
                 f'<p class="z9" id="pg_1">{link.format("PREFACE")}</p>' + para()
                 + '<p class="b3">The preface ends <span id="pg_3"></span>with a long look at the water.</p>'
                 + f'<p class="z9">{link.format("1 The River")} The river remembered everything that had '
                   'ever fallen into it.</p>'
                 + '<p class="z9"><span class="k2"><b class="v1">1.1 Morning</b></span></p>' + para()
                 + '<p class="fn"><a href="#r1">1</a> A note about rivers and the mills built beside them.</p>'),
            Page("Text/split_003.xhtml",
                 '<p class="z9" id="pg_9">PART TWO</p>'
                 + f'<p class="z9">{link.format("2 The Mill")}</p>' + para()
                 + '<p class="b3">The mill went quiet <span id="pg_12"></span>for the night.</p>'
                 + '<p class="z9">3 The</p><p class="z9">Storm</p>' + para()),
            Page("Text/split_004.xhtml",
                 '<p class="z9">BIBLIOGRAPHY</p><p class="b3">Fictional, Ada. 2026. Rivers. Nowhere Press.</p>'
                 '<p class="b3">Writer, Imaginary. 2025. Mills and Water. Nowhere Press.</p>'),
        ],
        toc=[
            ("Text/split_002.xhtml", "PREFACE"),
            ("Text/split_002.xhtml#pg_3", "1 The River"),
            ("Text/split_002.xhtml", "chapter and show how the river can be followed from the mill to the sea, "
                                     "which is what the rest of this little book is about"),
            ("Text/split_002.xhtml#pg_3", ",1"),
            ("Text/split_003.xhtml#pg_12", "1997)11"),
            ("Text/split_003.xhtml#pg_12", "address.”12"),
            ("Text/split_003.xhtml#pg_12", "3 The Storm"),
            ("Text/split_004.xhtml", "BIBLIOGRAPHY"),
        ],  # "2 The Mill" is missing here, as chapters 5 and 9 were in the real book
    )


def flat_textbook_spec() -> Spec:
    """textbook_spec with a flat TOC: chapters and their sections side by side, as many books list them."""
    spec = textbook_spec()

    def flatten(nodes):
        for href, title, kids in nodes:
            yield href, title
            yield from flatten(kids)
    spec.toc, spec.toc_tree = list(flatten(spec.toc_tree)), None
    return spec


def single_file_parts_spec() -> Spec:
    """One file: <h1> part titles with no text of their own, <h2> chapters, <h3> sections, and a flat
    TOC that lists all three."""
    body, toc = "", []
    for p, part in enumerate(["PART ONE", "PART TWO"], 1):
        body += f'<h1 id="p{p}">{part}</h1>'
        toc.append((f"book.xhtml#p{p}", part))
        for c in (1, 2):
            n = 2 * (p - 1) + c
            body += f'<h2 id="c{n}">Chapter {n}</h2>' + para()
            toc.append((f"book.xhtml#c{n}", f"Chapter {n}"))
            for s in (1, 2):
                body += f'<h3 id="s{n}_{s}">Section {n}.{s} Detail</h3>' + para()
                toc.append((f"book.xhtml#s{n}_{s}", f"Section {n}.{s} Detail"))
    return Spec(title="One File", pages=[Page("book.xhtml", body)], toc=toc)


def textbook_spec() -> Spec:
    """A publisher textbook like the one that motivated NORM-18: one file per chapter, a nested TOC
    whose children are sections inside the chapter file, chapter pages printed as 'CHAPTER ONE' over
    the title (the TOC says '1 The River Begins'), a half-title page with its own <h1>, a 'Copyright
    Page' TOC entry, and a second contents page that lists boxes ('lenses') inside the chapters."""
    lens = [f'<p><a href="ch{1 + i % 2}.xhtml#lens{i}">#{i} The Lens of Tide {i}</a></p>' for i in range(1, 7)]
    contents = ['<p><a href="hello.xhtml">Hello</a></p>', '<p><a href="ch1.xhtml#c1">1 The River Begins</a></p>',
                '<p><a href="ch1.xhtml#s1_1">Morning</a></p>', '<p><a href="ch1.xhtml#s1_2">Noon</a></p>',
                '<p><a href="ch2.xhtml#c2">2 The Mill Turns</a></p>', '<p><a href="ch2.xhtml#s2_1">Gears</a></p>']

    def chapter(n: int, word: str, title: str, sections: list[str]) -> str:
        body = f'<h2 id="c{n}">CHAPTER {word}</h2><h2>{title}</h2>' + para()
        for k, s in enumerate(sections, 1):
            body += f'<h3 id="s{n}_{k}">{s}</h3>' + para()
            body += f'<div id="lens{2 * k - 2 + n}"><p>#{2 * k - 2 + n} The Lens of Tide</p>{para(1)}</div>'
        return body

    return Spec(
        title="The Craft Book",
        pages=[
            Page("halftitle.xhtml", '<h1 id="ht">Special Edition</h1><h1>The Craft Book</h1>', allow_short=True),
            Page("copyright.xhtml", "<p>Copyright 2020 Nowhere Press. All rights reserved.</p>" + para()),
            Page("contents.xhtml", "<h2>CONTENTS</h2>" + "".join(contents), allow_short=True),
            Page("lenses.xhtml", "<h2>TABLE OF LENSES</h2>" + "".join(lens), allow_short=True),
            Page("hello.xhtml", "<h2>HELLO</h2>" + para(3)),
            Page("ch1.xhtml", chapter(1, "ONE", "The River Begins", ["Morning", "Noon"])),
            Page("ch2.xhtml", chapter(2, "TWO", "The Mill Turns", ["Gears"])),
        ],
        toc_tree=[
            ("halftitle.xhtml#ht", "Half Title", []),
            ("copyright.xhtml", "Copyright Page", []),
            ("contents.xhtml", "Table of Contents", []),
            ("lenses.xhtml", "Table of Lenses", []),
            ("hello.xhtml", "Hello", []),
            ("ch1.xhtml#c1", "1 The River Begins", [
                ("ch1.xhtml#s1_1", "Morning", []),
                ("ch1.xhtml#s1_2", "Noon", [("ch1.xhtml#lens3", "#3 The Lens of Tide", [])])]),
            ("ch2.xhtml#c2", "2 The Mill Turns", [("ch2.xhtml#s2_1", "Gears", [])]),
        ],
    )
