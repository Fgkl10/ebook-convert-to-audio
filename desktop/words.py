"""English word list for fixing OCR text (decision D-023).

The list is the pronunciation dictionary that ships with Kokoro's G2P, misaki (about 216,000 entries),
so nothing new is installed. It is only a yes/no check, "is this an English word?". It is never used
to guess a replacement. CI does not install Kokoro: without misaki the list is empty and the
dictionary-based fixes are skipped (tests pass their own small list).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

_FILES = ("us_gold.json", "us_silver.json", "gb_gold.json", "gb_silver.json")
# Inflections the dictionary often leaves out: (suffix, replacement) gives the base form to look up.
_INFLECTIONS = (("ies", "y"), ("es", ""), ("s", ""), ("ied", "y"), ("ed", ""), ("ed", "e"), ("d", ""),
                ("ing", ""), ("ing", "e"), ("ly", ""), ("ers", ""), ("er", ""))
_CLITICS = ("'s", "s'", "'ll", "'re", "'ve", "'d", "n't", "'m")


class Lexicon:
    def __init__(self, words: Iterable[str] = ()) -> None:
        self.keys = set(words)  # as spelled in the dictionary: 'IT' and 'it' are both entries
        self.lower = {w.lower() for w in self.keys}

    def __bool__(self) -> bool:
        return bool(self.keys)

    def knows(self, word: str) -> bool:
        """True for a dictionary word, its plural or other simple inflection, a possessive or
        contraction of one, or a hyphenated compound of known words."""
        w = word.lower().replace("’", "'").strip(".,;:!?\"'()")
        if not w:
            return False
        if w in self.lower:
            return True
        for clitic in _CLITICS:
            if w.endswith(clitic) and w[: -len(clitic)] in self.lower:
                return True
        for suffix, base in _INFLECTIONS:
            if w.endswith(suffix) and len(w) > len(suffix) + 1 and w[: -len(suffix)] + base in self.lower:
                return True
        parts = [p for p in w.split("-") if p]
        return len(parts) > 1 and all(self.knows(p) for p in parts)


@lru_cache(maxsize=1)
def load_lexicon() -> Lexicon:
    try:
        import misaki
    except ImportError:
        return Lexicon()
    data = Path(misaki.__file__).parent / "data"
    words: set[str] = set()
    for name in _FILES:
        path = data / name
        if path.exists():
            words |= set(json.loads(path.read_text(encoding="utf-8")))
    return Lexicon(words)
