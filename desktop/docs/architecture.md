# Desktop component: architecture

The desktop component converts an ebook into a sentence-timestamped audiobook and serves the
library over the LAN. It is a Python package (`desktop/`) with two entry points:

- `python -m desktop.build <file>`: command-line converter
- `python -m desktop.server [--port 8000]`: FastAPI server + web UI

## Module diagram

```mermaid
flowchart LR
    subgraph Entry points
        CLI["build.main()<br/>CLI"]
        SRV["server.py<br/>FastAPI app"]
    end

    subgraph Conversion pipeline
        PARSE["parse.py<br/>load_book()"]
        SEG["segment.py<br/>split_text()"]
        BUILD["build.py<br/>build_book()"]
        TTS["tts.py<br/>KokoroTTS"]
        CACHE[("cache/&lt;book_id&gt;/<br/>*.npy")]
        FFMPEG[["ffmpeg<br/>(external)"]]
    end

    LIB[("library/&lt;book_id&gt;/<br/>book.json, chNNN.m4a, cover")]
    UP[("uploads/")]
    UI["static/index.html<br/>web UI + player"]
    PHONE["Phone / browser<br/>(Android app in M4+)"]
    MDNS["zeroconf<br/>_ebookaudio._tcp"]

    CLI --> BUILD
    SRV -- "Jobs worker thread" --> BUILD
    SRV --> UP
    BUILD --> PARSE
    BUILD --> SEG
    BUILD --> CACHE
    CACHE -. miss .-> TTS
    BUILD --> FFMPEG --> LIB
    BUILD --> LIB
    SRV -- "reads" --> LIB
    SRV -- "serves" --> UI
    UI -- "HTTP /api/*" --> SRV
    PHONE -- "HTTP /api/*" --> SRV
    SRV --> MDNS
    MDNS -. discovery .-> PHONE
```

## Modules

| Module | Responsibility | Key API |
|---|---|---|
| `parse.py` | Read EPUB / PDF / TXT (`.md` too) into a uniform `Book` of `Chapter`s. Chapter text is one paragraph per line. Drops chapters under 40 chars. Extracts the cover. | `load_book(path) -> Book` |
| `segment.py` | Split chapter text into paragraphs of sentences (pysbd). Splits sentences over 350 chars at soft breaks. Attaches punctuation-only fragments to the previous sentence. | `split_text(text) -> list[list[str]]` |
| `tts.py` | Wrapper around Kokoro-82M. One call per sentence, mono float32 at 24 kHz. Uses CUDA when available. | `KokoroTTS(voice, speed).synth(text)`, `VOICES`, `SAMPLE_RATE` |
| `build.py` | Orchestrates the pipeline: plan, synthesize (cached), stitch with silence gaps, compute timestamps, encode m4a with ffmpeg, write `book.json` after each chapter. | `build_book(source, out_root, voice, speed, progress, tts) -> Path` |
| `server.py` | REST API, single-worker conversion queue, static web UI, mDNS advertisement, QR code for the LAN URL. | FastAPI `app`, `Jobs`, `advertise()` |
| `static/index.html` | Single-page UI: upload/convert, job progress, library grid, reader with sentence highlighting and tap-to-seek. | served at `/` |

## On-disk layout

```
library/<book_id>/          book_id = <title-slug, max 40 chars>-<sha1(file)[:8]>
    book.json               manifest (below)
    ch000.m4a, ch001.m4a…   AAC 64 kbps mono 24 kHz, +faststart
    cover.<ext>             optional
cache/<book_id>/<sha1>.npy  per-sentence audio, key = sha1("voice|speed|text"); deleted when the book completes
uploads/<rand>_<name>       files uploaded through the server (never cleaned up)
```

## `book.json` manifest

```json
{
  "id": "my-book-1a2b3c4d",
  "title": "My Book",
  "author": "Someone",
  "cover": "cover.jpg",
  "voice": "af_heart",
  "speed": 1.0,
  "complete": true,
  "created": 1764230400,
  "duration_ms": 123456,
  "chapters": [
    {
      "index": 0,
      "title": "Chapter 1",
      "audio": "ch000.m4a",
      "duration_ms": 61728,
      "sentences": [
        { "i": 0, "p": 0, "text": "It was a dark night.", "start_ms": 300, "end_ms": 1850 }
      ]
    }
  ]
}
```

Invariants:
- `sentences[k].end_ms == sentences[k+1].start_ms`. The pause after a sentence belongs to that
  sentence, so every playback position maps to exactly one sentence.
- Last sentence `end_ms == chapter.duration_ms`. First `start_ms == 300` (chapter lead-in).
- `p` is the paragraph index within the chapter, and `i` is the sentence index within the chapter.
- `complete: false` means the book is still converting (or was interrupted), but the chapters listed so far are playable.

## HTTP API

| Method & path | Purpose |
|---|---|
| `GET /` | Web UI |
| `GET /api/info` | Host name, LAN URL, QR SVG, voice list, default voice |
| `GET /api/books` | Library summary (title, author, cover, chapters, duration, size, complete) |
| `GET /api/books/{id}` | Full `book.json` |
| `GET /api/books/{id}/files/{name}` | Audio/cover file, with HTTP Range support |
| `DELETE /api/books/{id}` | Delete a book folder |
| `POST /api/convert` | Multipart `file`, `voice`, `speed` (0.5–2.0) → `{job_id}` |
| `GET /api/jobs` | All jobs (queued/running/done/error, progress) |

Book IDs are validated against `^[a-z0-9\-]{1,80}$` and file names reject `/`, `\`, and a leading `.`
(path-traversal guard).

## Concurrency model
- One background daemon thread drains a `queue.Queue` of job IDs, so conversions run one at a time
  (one GPU model in memory).
- The loaded `KokoroTTS` is reused across jobs while the voice language prefix (`a`/`b`) is unchanged.
- Job state lives in memory only and is lost when the server restarts.

## External dependencies
Python 3.10–3.12, PyTorch (CUDA build recommended), `kokoro`, `ebooklib`, `beautifulsoup4`, `lxml`,
`pymupdf`, `pysbd`, `fastapi`, `uvicorn`, `python-multipart`, `zeroconf`, `qrcode`, and
**ffmpeg on PATH**.
