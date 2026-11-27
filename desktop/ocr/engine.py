"""OCR for scanned PDFs (decision D-021).

docTR is optional. It is installed from requirements-ocr.txt, never from requirements.txt or
requirements-ci.txt, so it is imported only when a scanned PDF is cleaned. Tests replace
`make_engine` with a fake engine.

Each page image is rendered, split into its two book pages when the scan is a two-page spread,
and read into lines of words with boxes in coordinates relative to that page (0..1).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

INSTALL_HINT = ("This PDF is a scan, and reading it needs OCR. Install it once with:\n"
                "  pip install -r requirements-ocr.txt")
SCAN_DPI = 200
MIN_IMAGE_COVER = 0.85  # a scanned page is one image covering at least this share of the page
MIN_SCANNED_PAGES = 0.8  # a scanned book has at least this share of such pages
SPREAD_RATIO = 1.15  # an image this much wider than tall holds two book pages


@dataclass
class Word:
    text: str
    box: tuple[float, float, float, float]  # x0, y0, x1, y1, relative to the book page
    conf: float = 1.0

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]


@dataclass
class Line:
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (min(w.box[0] for w in self.words), min(w.box[1] for w in self.words),
                max(w.box[2] for w in self.words), max(w.box[3] for w in self.words))


Page = list[Line]  # one book page (half of a spread), lines in reading order
Engine = Callable[[np.ndarray], Page]


def is_scanned(path: str | Path) -> bool:
    """True when nearly every page is a single full-page image (a scan), with or without a text layer."""
    import pymupdf

    with pymupdf.open(str(path)) as doc:
        if not doc.page_count:
            return False
        scanned = 0
        for page in doc:
            area = page.rect.width * page.rect.height
            covered = max((abs(pymupdf.Rect(i["bbox"]) & page.rect) for i in page.get_image_info()), default=0)
            scanned += area > 0 and covered >= MIN_IMAGE_COVER * area
        return scanned >= MIN_SCANNED_PAGES * doc.page_count


def render(page, dpi: int = SCAN_DPI) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return np.ascontiguousarray(img[:, :, :3])


def split_spread(img: np.ndarray) -> list[np.ndarray]:
    """Split a two-page spread at the gutter: the widest ink-free column band near the middle.
    The exact centre can cut through text when the book sat off-centre on the scanner."""
    h, w = img.shape[:2]
    if w < SPREAD_RATIO * h:
        return [img]
    ink = (img.mean(axis=2) < 128).sum(axis=0)
    lo, hi = int(0.35 * w), int(0.65 * w)
    empty = ink[lo:hi] <= max(2, 0.004 * h)
    best, start = (0, w // 2 - lo), None
    for x, e in enumerate(list(empty) + [False]):
        if e and start is None:
            start = x
        elif not e and start is not None:
            if x - start > best[0]:
                best = (x - start, (start + x) // 2)
            start = None
    cut = lo + best[1]
    return [img[:, :cut], img[:, cut:]]


class DoctrEngine:
    """docTR text detection + recognition, on the GPU when available."""

    def __init__(self) -> None:
        try:
            import torch
            from doctr.models import ocr_predictor
        except ImportError as e:
            raise ValueError(INSTALL_HINT) from e
        self._torch = torch
        self.model = ocr_predictor(pretrained=True)
        if torch.cuda.is_available():
            self.model = self.model.cuda()

    def __call__(self, img: np.ndarray) -> Page:
        with self._torch.no_grad():
            result = self.model([img]).pages[0]
        lines = []
        for block in result.blocks:
            for line in block.lines:
                words = [Word(w.value, (w.geometry[0][0], w.geometry[0][1], w.geometry[1][0], w.geometry[1][1]),
                              float(w.confidence)) for w in line.words if w.value.strip()]
                if words:
                    lines.append(Line(words))
        return lines

    def close(self) -> None:
        """Free GPU memory before the TTS model loads (both share one GPU)."""
        del self.model
        if self._torch.cuda.is_available():
            self._torch.cuda.empty_cache()


def make_engine() -> Engine:
    return DoctrEngine()


def ocr_pdf(path: str | Path, progress: Callable[[int, int], None] | None = None) -> tuple[list[Page], bytes]:
    """OCR every book page. Returns (pages in reading order, cover PNG). Raises ValueError if OCR is missing."""
    import pymupdf

    engine = make_engine()
    pages: list[Page] = []
    cover = b""
    try:
        with pymupdf.open(str(path)) as doc:
            for n, pdf_page in enumerate(doc):
                halves = split_spread(render(pdf_page))
                if n == 0:  # the front cover is the right half of a cover spread
                    cover = _png(halves[-1])
                pages.extend(engine(np.ascontiguousarray(h)) for h in halves)
                if progress:
                    progress(n + 1, doc.page_count)
    finally:
        close = getattr(engine, "close", None)
        if close:
            close()
    return pages, cover


def _png(img: np.ndarray) -> bytes:
    import pymupdf

    small = img[::4, ::4]  # 50 dpi is plenty for a cover thumbnail
    pix = pymupdf.Pixmap(pymupdf.csRGB, small.shape[1], small.shape[0], np.ascontiguousarray(small).tobytes(), False)
    return pix.tobytes("png")
