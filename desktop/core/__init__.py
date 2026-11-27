"""Book text: parsing (EPUB/PDF/TXT), chapter splitting, sentence segmentation, cleaning and the language check.

No web, GPU or TTS code, and no imports from the other desktop packages. The one link to OCR is a lazy import in
normalize(), made only when a PDF is actually read with OCR (D-033).
"""
