"""Refuse books in a language the TTS voices cannot speak (decision D-018).

The check looks at the text, not the metadata: internet EPUBs often carry a wrong dc:language,
and PDF/TXT files usually have none. English is recognised by how often its most common
function words appear. Measured on real books: English 0.32-0.44 (the low end is a noisy OCR
scan), Hungarian 0.00, and German/French/Spanish/Dutch prose 0.00-0.08.
"""
from __future__ import annotations

import re

from .parse import Book
from .tts import SUPPORTED_LANGUAGES

# Common English function words. Words that are also common in other languages ("a" and "is" in
# Hungarian, "i", "in", "die", "so"...) are left out so they cannot inflate a non-English score.
_EN_WORDS = frozenset("""
the and of to that it you was for on are with as his he be at by this have from or one had not but
what all were when we there can an your which their if do will each about how up out them she many
some these would other into has more her two like him see time could no make than been its who now
my over did down only way find use may long
""".split())
_WORD = re.compile(r"[^\W\d_]+")

THRESHOLD = 0.15  # share of words that must be English function words
MIN_WORDS = 100  # below this there is too little text to judge, so the book is accepted
_SAMPLE_CHAPTERS = 6
_WORDS_PER_CHAPTER = 400


def english_score(book: Book) -> tuple[float, int]:
    """(share of English function words, words sampled) over chapters spread across the book."""
    chapters = book.chapters
    step = max(1, len(chapters) // _SAMPLE_CHAPTERS)
    words: list[str] = []
    for ch in chapters[::step][:_SAMPLE_CHAPTERS]:
        words += _WORD.findall(ch.text.lower())[:_WORDS_PER_CHAPTER]
    if not words:
        return 0.0, 0
    return sum(w in _EN_WORDS for w in words) / len(words), len(words)


def check_language(book: Book) -> None:
    """Raise ValueError if the book's text is not in a supported language."""
    score, n = english_score(book)
    if n < MIN_WORDS or score >= THRESHOLD:
        return
    hint = f" Its metadata says language '{book.language}'." if book.language else ""
    supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
    raise ValueError(
        f"This book doesn't look like English (English word score {score:.2f}, needs {THRESHOLD}).{hint} "
        f"The voices can only speak: {supported}."
    )
