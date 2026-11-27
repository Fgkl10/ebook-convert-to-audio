"""Synthetic OCR output and scanned PDFs for the scanned-book tests (D-014: made-up text only).

`line()` builds an ocr.Line the way docTR returns one: words with boxes relative to the book page.
`quiz_book()` is a small quiz book laid out like the real scan that motivated D-021/D-022: a title
page, a contents page, running headers, page numbers, drop caps, a quiz whose numbered items are
separate questions, a multiple-choice quiz, "KEY TO" answer sections and a back cover.
"""
from __future__ import annotations

import numpy as np

from desktop.ocr import Line, Word

LH = 0.022  # body line height
STEP = 0.026  # line spacing


def line(text: str, y: float, x: float = 0.08, h: float = LH, cap: bool = False) -> Line:
    """One OCR line. cap=True makes the first word a big drop-cap letter, as docTR reads 'T he'."""
    words, cx = [], x
    for i, w in enumerate(text.split(" ")):
        wh = 0.034 if cap and i == 0 else h
        width = 0.012 * len(w)
        words.append(Word(w, (cx, y, cx + width, y + wh), 0.95))
        cx += width + 0.01
    return Line(words)


def body(lines: list[str], y: float = 0.29, x: float = 0.08, indent_first: bool = False) -> list[Line]:
    out = []
    for i, t in enumerate(lines):
        out.append(line(t, y + i * STEP, x + (0.05 if indent_first and i == 0 else 0.0)))
    return out


def header(n: int) -> Line:
    """Running header; OCR sometimes splits it ('W ORD GAME'), which must still count as the same."""
    return line("W ORD GAME" if n == 6 else "WORD GAME", 0.07, 0.12 if n % 2 == 0 else 0.55)


def number(n: int) -> Line:
    return line(str(n), 0.94, 0.88 if n % 2 else 0.03, h=0.013)


def quiz_book() -> list[list[Line]]:
    """Book pages (already split from spreads) in reading order."""
    return [
        # 0 cover / title page: front matter, no page number
        [line("THE WORD GAME", 0.40, 0.2), line("Ada Fictional", 0.50, 0.25)],
        # 1 contents (OCR glued two words of the first title, as it does)
        [line("CONTENTS", 0.16, 0.37), line("A MORNINGWALK", 0.25), line("3", 0.25, 0.40),
         line("THE LOST KEY", 0.28), line("5", 0.28, 0.40), number(1)],
        # 2 quiz with separate questions; big first letter, a hyphenated line break
        [line("A MORNING WALK", 0.16, 0.28),
         line("T he path through the hills is quiet at dawn, and the mo-", 0.29, 0.10, cap=True),
         line("mentary chill makes every step feel new.", 0.29 + STEP, 0.16),
         line("Take a breath and begin the walk.", 0.29 + 2 * STEP),
         line("1. A bird lands on the fence beside you. What colour is the bird?", 0.29 + 4 * STEP),
         line("2. You find a coin on the path. What do you do with it?", 0.29 + 6 * STEP),
         number(3)],
        # 3 the quiz continues on the next page, under a running header
        [header(4), line("3. The walk ends at a river. How deep is the water?", 0.11), number(4)],
        # 4 the key: numbered answers in the same order; a self-confidence line keeps its hyphen
        [header(5), line("KEY TO A MORNING WALK", 0.16, 0.20),
         line("T he walk stands for the way you meet a new day and its", 0.29, 0.10, cap=True),
         line("small surprises, with self-", 0.29 + STEP, 0.16),
         line("confidence or with doubt.", 0.29 + 2 * STEP),
         line("1. The colour of the bird shows the mood you wake up in.", 0.29 + 4 * STEP),
         line("2. What you did with the coin shows how you treat small luck.", 0.29 + 6 * STEP),
         line("3. The depth of the river is how much you worry about SO little.", 0.29 + 8 * STEP),
         number(5)],
        # 5 multiple choice: the numbered items are choices; a quoted question is not a question
        [header(6), line("THE LOST KEY", 0.16, 0.30),
         line("Y ou come home late and the key is gone. Which thought comes", 0.29, 0.10, cap=True),
         line("first to your mind?", 0.29 + STEP, 0.16),
         line('1. "Where did I put it?"', 0.29 + 3 * STEP),
         line('2. "Someone must have taken it."', 0.29 + 4 * STEP),
         line("3. I will sleep on the porch", 0.29 + 5 * STEP),
         line("tonight.", 0.29 + 6 * STEP, 0.11),  # hanging indent of a wrapped choice
         number(6)],
        # 6 its key, with a heading wrapped over two lines
        [header(7), line("KEY TO THE LOST", 0.16, 0.20), line("Key", 0.16 + STEP, 0.36),
         line("Losing a key is losing control for a moment, and your thought", 0.29),
         line("shows how you take it back.", 0.29 + STEP),
         line("1. You blame yourself first and look for the mistake.", 0.29 + 3 * STEP),
         line("2. You look for someone else to blame.", 0.29 + 4 * STEP),
         line("3. You accept what happened and rest.", 0.29 + 5 * STEP),
         number(7)],
        # 7 back cover: no page number
        [line("A GAME FOR EVERY MIND", 0.10, 0.2), line("Price 9.99", 0.93, 0.6)],
    ]


def spread_image(width: int = 1200, height: int = 800, gutter: float = 0.44) -> np.ndarray:
    """A white two-page scan with text blocks on both pages and an empty gutter off-centre at `gutter`."""
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    g = int(gutter * width)
    for x0, x1 in ((int(0.05 * width), g - 40), (g + 40, int(0.95 * width))):
        for y in range(100, height - 100, 30):
            img[y:y + 12, x0:x1] = 0
    return img
