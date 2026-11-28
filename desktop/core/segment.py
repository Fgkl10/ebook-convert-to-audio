"""Split chapter text into paragraphs of sentences.

Each sentence becomes one TTS call and one highlightable unit on the phone,
so units should be natural sentences: not too long (coarse highlighting,
TTS quality drops) and never empty/punctuation-only.

English uses pysbd. Chinese (D-042) uses a rule of its own: a sentence ends after 。！？ together with the closing
quotes and brackets that follow them (pysbd cuts 。” apart); …… does not end one (好……再见). Chinese has no spaces, so long sentences are
split at Chinese punctuation, and shorter ones count as long: a Chinese character takes about as long to say as an
English word.
"""
from __future__ import annotations

import re

import pysbd

from .parse import CJK

MAX_CHARS = 350  # English: longer sentences are split at commas/semicolons/spaces
MAX_CHARS_ZH = 120  # Chinese: ~120 characters is ~25 s of speech, like 350 English letters

_segmenter = pysbd.Segmenter(language="en", clean=False)
_HAS_WORD = re.compile(rf"[A-Za-z0-9{CJK}]")
_SOFT_BREAK = re.compile(r"[,;:—–)]\s+|\s+[—–(]")
_SOFT_BREAK_ZH = re.compile(r"[，；：、]|——|…+|[,;:]\s+")
_ZH_SENTENCE = re.compile(r".*?[。！？!?]+[”’」』）)\]】》\"']*|.+$")
# A piece that starts like this continues the one before: the cut fell inside 《a title！：its subtitle》.
_ZH_CONTINUES = re.compile(r"[：:，,、；;）)》」』”’]")


def _zh_sentences(paragraph: str) -> list[str]:
    out: list[str] = []
    for s in _ZH_SENTENCE.findall(paragraph):
        if out and _ZH_CONTINUES.match(s.lstrip()):
            out[-1] += s
        else:
            out.append(s)
    return out


def _split_long(sentence: str, max_chars: int = MAX_CHARS, soft: re.Pattern = _SOFT_BREAK) -> list[str]:
    parts: list[str] = []
    rest = sentence
    while len(rest) > max_chars:
        window = rest[:max_chars]
        # Prefer the last punctuation break in the second half of the window.
        cut = -1
        for m in soft.finditer(window):
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


def _sentences(paragraph: str, lang: str) -> list[str]:
    if lang == "zh":
        return _zh_sentences(paragraph)
    return _segmenter.segment(paragraph)


def split_paragraph(paragraph: str, lang: str = "en") -> list[str]:
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    if not paragraph:
        return []
    out: list[str] = []
    limit, soft = (MAX_CHARS_ZH, _SOFT_BREAK_ZH) if lang == "zh" else (MAX_CHARS, _SOFT_BREAK)
    for s in _sentences(paragraph, lang):
        s = s.strip()
        if not s:
            continue
        if not _HAS_WORD.search(s):
            # "* * *", "…", lone quote marks: attach to previous sentence (keeps
            # the text faithful) or drop if it starts the paragraph.
            if out:
                out[-1] = f"{out[-1]}{'' if lang == 'zh' else ' '}{s}"
            continue
        out.extend(_split_long(s, limit, soft))
    return out


def split_text(text: str, lang: str = "en") -> list[list[str]]:
    """Text with paragraphs separated by newlines -> list of paragraphs, each a list of sentences."""
    paragraphs = []
    for para in re.split(r"\n+", text):
        sents = split_paragraph(para, lang)
        if sents:
            paragraphs.append(sents)
    return paragraphs
