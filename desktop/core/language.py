"""Tell which language a book is in, and refuse books the TTS voices cannot speak (decisions D-018, D-042).

The check looks at the text, not the metadata: internet EPUBs often carry a wrong dc:language,
and PDF/TXT files usually have none.
- Chinese (Simplified or Traditional): most letters are CJK ideographs, and there is next to no Japanese kana.
- English: how often its most common function words appear. Measured on real books: English 0.32-0.44
  (the low end is a noisy OCR scan), Hungarian 0.00, and German/French/Spanish/Dutch prose 0.00-0.08.
"""
from __future__ import annotations

import re

from .parse import CJK, Book

# Languages the TTS voices (desktop/tts/kokoro.py V10_VOICES) can speak; books in any other language are refused.
# Kept here, not in tts, so core imports nothing from the other packages (D-033).
SUPPORTED_LANGUAGES = {"en", "zh"}
LANGUAGE_NAMES = {"en": "English", "zh": "Chinese"}

# Common English function words. Words that are also common in other languages ("a" and "is" in
# Hungarian, "i", "in", "die", "so"...) are left out so they cannot inflate a non-English score.
_EN_WORDS = frozenset("""
the and of to that it you was for on are with as his he be at by this have from or one had not but
what all were when we there can an your which their if do will each about how up out them she many
some these would other into has more her two like him see time could no make than been its who now
my over did down only way find use may long
""".split())
_WORD = re.compile(r"[^\W\d_]+")
_HAN = re.compile(f"[{CJK}]")
_KANA = re.compile(r"[぀-ヿ]")
_LETTER = re.compile(r"[^\W\d_]")

THRESHOLD = 0.15  # share of words that must be English function words
MIN_WORDS = 100  # below this there is too little text to judge, so the book is accepted
ZH_SHARE = 0.3  # share of letters that must be Chinese characters (an English book quoting some Chinese stays English)
MIN_HAN = 100  # Chinese characters needed to call a book Chinese
_SAMPLE_CHAPTERS = 6
_WORDS_PER_CHAPTER = 400
_CHARS_PER_CHAPTER = 2000


def _sample_chapters(book: Book):
    chapters = book.chapters
    step = max(1, len(chapters) // _SAMPLE_CHAPTERS)
    return chapters[::step][:_SAMPLE_CHAPTERS]


def english_score(book: Book) -> tuple[float, int]:
    """(share of English function words, words sampled) over chapters spread across the book."""
    words: list[str] = []
    for ch in _sample_chapters(book):
        words += _WORD.findall(ch.text.lower())[:_WORDS_PER_CHAPTER]
    if not words:
        return 0.0, 0
    return sum(w in _EN_WORDS for w in words) / len(words), len(words)


def chinese_share(book: Book) -> tuple[float, int]:
    """(share of letters that are Chinese characters, Chinese characters sampled). Japanese, which also uses Chinese
    characters, scores 0: its kana are frequent in any Japanese prose."""
    sample = "".join(ch.text[:_CHARS_PER_CHAPTER] for ch in _sample_chapters(book))
    han, letters = len(_HAN.findall(sample)), len(_LETTER.findall(sample))
    if not letters or len(_KANA.findall(sample)) > 0.05 * han:
        return 0.0, han
    return han / letters, han


def detect_language(book: Book) -> str | None:
    """"zh", "en", or None for a language the voices cannot speak. Too little text to judge counts as the metadata's
    language when it is a supported one, else English (as before D-042)."""
    share, han = chinese_share(book)
    if han >= MIN_HAN and share >= ZH_SHARE:
        return "zh"
    score, n = english_score(book)
    if n >= MIN_WORDS:
        return "en" if score >= THRESHOLD else None
    if han >= MIN_HAN:  # little Latin text and real Chinese text, but not most of the letters: still not judgeable
        return None
    meta = (book.language or "").lower()[:2]
    return meta if meta in SUPPORTED_LANGUAGES else "en"


def check_language(book: Book) -> str:
    """The book's language code. Raise ValueError if the text is in a language the voices cannot speak."""
    lang = detect_language(book)
    if lang is not None:
        return lang
    score, _ = english_score(book)
    share, _ = chinese_share(book)
    hint = f" Its metadata says language '{book.language}'." if book.language else ""
    supported = ", ".join(LANGUAGE_NAMES[c] for c in sorted(SUPPORTED_LANGUAGES))
    raise ValueError(
        f"This book doesn't look like English or Chinese (English word score {score:.2f}, needs {THRESHOLD}; "
        f"Chinese characters {share:.0%}, needs {ZH_SHARE:.0%}).{hint} The voices can only speak: {supported}. "
        f"If this book really is in one of them, rerun with --ignore-language."
    )
