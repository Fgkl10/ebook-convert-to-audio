"""Desktop component. Importing it points the model caches into the project (D-028).

Kokoro (Hugging Face) and docTR read these variables when they are first imported, so they are set here,
before any desktop module imports them. A value already set in the environment wins.

Packages (D-033): core (book text) <- ocr, tts <- server; web holds the page files the server serves.
"""
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent  # the repository folder; paths below never depend on module depth
MODELS = PROJECT / "models"
os.environ.setdefault("HF_HOME", str(MODELS / "huggingface"))
os.environ.setdefault("DOCTR_CACHE_DIR", str(MODELS / "doctr"))
