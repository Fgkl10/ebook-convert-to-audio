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
| `desktop/core/` | Book text: parsing, chapter splitting, cleaning (no web or GPU code) |
| `desktop/ocr/` | Scanned-PDF OCR (optional, docTR) |
| `desktop/tts/` | Kokoro speech, sentence timing, the converter |
| `desktop/server/` | Backend and the JSON API under `/api/v1` |
| `desktop/web/` | The web page (HTML/JS/CSS) |
| `android/` | Kotlin app (Media3 player, sentence sync) — *coming in M4/M5* |

## Setup (Windows)
Requires Python 3.10–3.12, ffmpeg on PATH, NVIDIA GPU recommended.
```powershell
py -3.10 -m venv .venv
.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu124
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .            # installs the commands below (ebook-server, ebook-normalize, ebook-convert)
# Optional, only for scanned PDFs (OCR with docTR, keeps the CUDA torch):
.venv\Scripts\pip install -r requirements-ocr.txt
```
The models (Kokoro ~313 MB, docTR ~120 MB) download on first use into `models/` inside the project.
Set `HF_HOME` / `DOCTR_CACHE_DIR` to use another folder.

## Usage
Activate the venv first (`.venv\Scripts\activate`), or prefix each command with `.venv\Scripts\`.
```powershell
# Run the server and use the web UI (also reachable from the phone)
ebook-server
# open http://localhost:8000: upload a book, it is cleaned, review it (or tick "skip review"), then Approve & convert

# Or from the command line: clean first, check the result, then convert
ebook-normalize path\to\book.epub                 # writes book.std.epub + book.std.report.txt
ebook-convert path\to\book.std.epub --voice af_heart
ebook-convert path\to\book.std.epub --chapters 1  # quick test: one chapter
```

### API
The web page does everything through a JSON API, and the Android app uses the same one. All endpoints are under
`/api/v1`: upload and clean, review report, approve, conversion progress, the library and audio download. See
<http://localhost:8000/docs> for the interactive reference, or `desktop/docs/architecture.md` for the table.
Set `EBOOK_AUDIO_DATA=<folder>` to keep `library/`, `cache/` and `drafts/` somewhere other than the project.

### Connecting a phone
Other devices need pairing: scan the QR code on the PC's page (`http://localhost:8000`) with the phone. The QR code
holds the server's address and a token, kept in `server-token` in the data folder; without the token the API answers
401. The PC's own browser needs no token. `ebook-server --new-token` makes a new token, which unpairs every phone.

The QR code starts on the PC's local network address. If the phone can't reach it (for example a router with AP
isolation), connect both through a VPN such as **ZeroTier One**. Then open "Other addresses" on the page and click
the ZeroTier address, or type any address and press **Show QR**. `ebook-server --advertise 10.x.x.x` (or
`EBOOK_AUDIO_ADVERTISE`) makes another address the default.

## Roadmap
- M1 TTS proof · M2 converter CLI · M3 server + web UI
- M4 Android player (Media3, background / lock screen) · M5 sentence sync · M6 polish
