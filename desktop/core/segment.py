"""Split chapter text into paragraphs of sentences.

Each sentence becomes one TTS call and one highlightable unit on the phone,
so units should be natural sentences: not too long (coarse highlighting,
TTS quality drops) and never empty/punctuation-only.
"""
from __future__ import annotations

import re

import pysbd

MAX_CHARS = 350  # longer sentences are split at commas/semicolons/spaces

_segmenter = pysbd.Segmenter(language="en", clean=False)
_HAS_WORD = re.compile(r"[A-Za-z0-9]")
_SOFT_BREAK = re.compile(r"[,;:—–)]\s+|\s+[—–(]")


def _split_long(sentence: str, max_chars: int = MAX_CHARS) -> list[str]:
    parts: list[str] = []
    rest = sentence
    while len(rest) > max_chars:
        window = rest[:max_chars]
        # Prefer the last punctuation break in the second half of the window.
        cut = -1
        for m in _SOFT_BREAK.finditer(window):
            if m.end() >= max_chars // 2:
                cut = m.end()
        if cut == -1:
            cut = window.rfind(" ")
            if cut < max_chars // 2:
                cut = max_chars
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        parts.append(rest)
    return [p for p in parts if p]


def split_paragraph(paragraph: str) -> list[str]:
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    if not paragraph:
        return []
    out: list[str] = []
    for s in _segmenter.segment(paragraph):
        s = s.strip()
        if not s:
            continue
        if not _HAS_WORD.search(s):
            # "* * *", "…", lone quote marks: attach to previous sentence (keeps
            # the text faithful) or drop if it starts the paragraph.
            if out:
                out[-1] = f"{out[-1]} {s}"
            continue
        out.extend(_split_long(s))
    return out


def split_text(text: str) -> list[list[str]]:
    """Text with paragraphs separated by newlines -> list of paragraphs, each a list of sentences."""
    paragraphs = []
    for para in re.split(r"\n+", text):
        sents = split_paragraph(para)
        if sents:
            paragraphs.append(sents)
    return paragraphs
