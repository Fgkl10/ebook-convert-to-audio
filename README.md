# Ebook → Audiobook

Convert ebooks (EPUB / PDF / TXT) into audiobooks on a Windows PC using a **local** TTS model
(Kokoro-82M on an NVIDIA GPU), then listen on Android with a music-player-style app that
**highlights the sentence being read** and lets you tap any sentence to jump to it.

## How it works
- Each sentence is synthesized separately, so exact per-sentence timestamps are known when the
  chapter audio is stitched together — no forced alignment needed.
- Output per book: `library/<book_id>/ch000.m4a, ch001.m4a, …` + `book.json`
  (chapters → sentences with `start_ms` / `end_ms`).
- A FastAPI server on the PC serves the library over Wi-Fi; the Android app downloads books from it.

## Components
| Folder | What |
|---|---|
| `desktop/` | Python converter (`build.py`), LAN server + web UI (`server.py`) |
| `android/` | Kotlin app (Media3 player, sentence sync) — *coming in M4/M5* |

## Setup (Windows)
Requires Python 3.10–3.12, ffmpeg on PATH, NVIDIA GPU recommended.
```powershell
py -3.10 -m venv .venv
.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu124
.venv\Scripts\pip install -r requirements.txt
```

## Usage
```powershell
# Convert from the command line: clean first, check the result, then convert
.venv\Scripts\python -m desktop.normalize path\to\book.epub      # writes book.std.epub + book.std.report.txt
.venv\Scripts\python -m desktop.build path\to\book.std.epub --voice af_heart
.venv\Scripts\python -m desktop.build path\to\book.std.epub --chapters 1   # quick test: one chapter

# Or run the server and use the web UI (also reachable from the phone)
.venv\Scripts\python -m desktop.server
# open http://localhost:8000
```

## Roadmap
- M1 TTS proof · M2 converter CLI · M3 server + web UI
- M4 Android player (Media3, background / lock screen) · M5 sentence sync · M6 polish
