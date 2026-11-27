# Desktop component: architecture

The desktop component converts an ebook into a sentence-timestamped audiobook and serves the
library over the LAN. It is a Python package (`desktop/`) split into five parts (D-033), in one project with one
venv:

| Package | Contents | May import |
|---|---|---|
| `desktop/core/` | Book text: parsing, chapter splitting, sentence segmentation, cleaning, language check. No web, GPU or TTS code | nothing else (only `desktop.ocr`, lazily, when `normalize()` reads a PDF) |
| `desktop/ocr/` | Scanned-PDF OCR: detection, page rendering, docTR, rebuilding chapters from OCR lines, word check | `core` |
| `desktop/tts/` | Kokoro speech and the converter that times every sentence and writes the library | `core` |
| `desktop/server/` | Backend service, JSON API v1, the FastAPI app | `core`, `ocr`, `tts` |
| `desktop/web/` | The page: `index.html`, `app.js`, `app.css` (static files, no Python) | `/api/v1` over HTTP only |

Nothing imports `server` or `web`. `desktop/__init__.py` only sets the model cache folders and `PROJECT`.
`tests/test_layers.py` enforces these rules.

Three commands, installed into the venv once with `pip install -e .` (`pyproject.toml`):

- `ebook-normalize <file> [--ocr auto|always|never]` (`desktop.core.normalize:main`): cleans any EPUB/PDF/TXT into
  `<name>.std.epub` plus `<name>.std.report.txt` for manual review (D-019). `--ignore-language` skips the English
  check.
- `ebook-convert <file.std.epub>` (`desktop.tts.build:main`): the command-line converter.
  - It only converts cleaned files, and refuses anything else with the `ebook-normalize` command to run.
  - `--list-chapters` prints numbered chapters, and `--ignore-language` skips the English check (D-018).
  - `--chapters 3` / `2-4` / `1,3,5-6` converts only those chapters (1-based, after front matter is skipped) into
    `library/<book_id>-ch<spec>/`. That is a separate folder, so test conversions never touch the full book.
- `ebook-server [--port 8000]` (`desktop.server.app:main`, also `python -m desktop.server`): one process with three
  layers (D-032):
  - the backend (`server/service.py`);
  - its JSON API under `/api/v1` (`server/api.py`);
  - the web page (`desktop/web/`), which only calls that API.

  Interactive API docs are at `/docs`, and the contract is at `/openapi.json`. `EBOOK_AUDIO_DATA=<folder>` moves
  `library/`, `cache/` and `drafts/` out of the project, for example for a second test server.

## Module diagram

```mermaid
flowchart LR
    subgraph server ["desktop/server (D-032)"]
        SRV["app.py<br/>app, /static, mDNS<br/>(ebook-server)"]
        API["api.py<br/>/api/v1 routes + schemas"]
        SVC["service.py<br/>Drafts, Jobs, library,<br/>voice samples (no HTTP)"]
    end
    SRV --> API --> SVC

    subgraph core ["desktop/core"]
        PARSE["parse.py<br/>load_book()"]
        SEG["segment.py<br/>split_text()"]
        NORM["normalize.py<br/>clean → .std.epub<br/>(ebook-normalize)"]
        LANG["language.py<br/>check_language()"]
    end

    subgraph tts ["desktop/tts"]
        BUILD["build.py<br/>build_book()<br/>(ebook-convert)"]
        TTS["kokoro.py<br/>KokoroTTS"]
    end
    CLI["ebook-convert CLI"] --> BUILD
    CACHE[("cache/&lt;book_id&gt;/<br/>*.npy")]
    FFMPEG[["ffmpeg<br/>(external)"]]

    subgraph ocr ["desktop/ocr (optional docTR)"]
        SCAN["scanned.py<br/>rebuild chapters from OCR"]
        OCRM["engine.py<br/>scan detection, gutter split,<br/>docTR"]
        WORDS["words.py<br/>English word list<br/>(Kokoro's misaki dictionary)"]
    end

    LIB[("library/&lt;book_id&gt;/<br/>book.json, chNNN.m4a, cover")]
    UP[("drafts/&lt;id&gt;/<br/>upload, book.std.epub,<br/>report.json, draft.json")]
    UI["desktop/web: index.html + app.js + app.css<br/>web UI + player (display only)"]
    PHONE["Phone / browser<br/>(Android app in M4+)"]
    MDNS["zeroconf<br/>_ebookaudio._tcp"]

    NORM -- "PDF read with OCR<br/>(lazy import)" --> SCAN --> OCRM
    NORM --> LANG
    BUILD --> LANG
    SCAN --> WORDS
    REVIEW(["you: review .std.epub<br/>(CLI: in a reader / Sigil;<br/>web: review page)"])
    NORM --> REVIEW --> CLI
    SVC -- "Drafts clean worker" --> NORM
    NORM --> PARSE
    CLI --> BUILD
    REVIEW -- "Approve" --> API
    SVC -- "Jobs convert worker<br/>(approved .std.epub)" --> BUILD
    SVC --> UP
    BUILD --> PARSE
    BUILD --> SEG
    BUILD --> CACHE
    CACHE -. miss .-> TTS
    BUILD --> FFMPEG --> LIB
    BUILD --> LIB
    SVC -- "reads" --> LIB
    SRV -- "serves / and /static<br/>from desktop/web" --> UI
    UI -- "JSON /api/v1/*" --> API
    PHONE -- "JSON /api/v1/*" --> API
    SRV --> MDNS
    MDNS -. discovery .-> PHONE
```

## Modules

| Module | Responsibility | Key API |
|---|---|---|
| `core/parse.py` | Read EPUB / PDF / TXT (`.md` too) into a uniform `Book` of `Chapter`s. Chapter text is one paragraph per line. Drops chapters under 40 chars. Skips EPUB front matter (cover, title, half title, copyright, contents) using the book's labels, its OPF guide, or exact titles. Removes footnote paragraphs (labelled, or opening with a backlink number, with their small-print continuation lines, D-027) and strips note-reference markers: `<sup>` markers and number-only note links in running text, keeping cross-references such as "Chapters 9 through 11" (D-026). Extracts the cover. | `load_book(path) -> Book`, `clean_body(html)` (shared with `normalize.py`) |
| `core/segment.py` | Split chapter text into paragraphs of sentences (pysbd). Splits sentences over 350 chars at soft breaks. Attaches punctuation-only fragments to the previous sentence. | `split_text(text) -> list[list[str]]` |
| `core/normalize.py` | Cleans a book into a standard EPUB: one XHTML file per chapter, with title, author, language, cover and the markers `ebook-audio:normalized` + `ebook-audio:source-sha1`. For EPUB it confirms TOC / contents-page entries against headings in the text and cuts there (with a nested TOC, only its top level and entries that open their own file, D-024; with a flat TOC, only at the chapter heading level, D-025), dropping front matter, contents pages, bibliography, index and endnotes. In every format it removes label-only figure lines. PDF/TXT are repackaged as parsed, and scanned PDFs are rebuilt from OCR (`ocr/scanned.py`, imported only when a PDF is read, D-033); the `ocr` mode can force OCR on or off for a PDF (D-030). It writes a report of chapters, removed text, ignored TOC entries and notes (answer placement, words to check). | `normalize(source, out, ignore_language, progress, ocr) -> (path, Report)`, `OCR_MODES` |
| `ocr/engine.py` | Detects scanned PDFs (nearly every page one full-page image), renders pages at 200 dpi, splits two-page scans at the gutter, and runs docTR on each book page. docTR is optional (`requirements-ocr.txt`) and imported only here, so CI and text books never need it; a missing install raises `ValueError` with the install command. Frees the GPU after OCR. | `is_scanned(path)`, `split_spread(img)`, `ocr_pdf(path, progress) -> (pages, cover)`, `make_engine()` (tests replace it) |
| `ocr/scanned.py` | Pure functions that turn OCR lines (`Line` of `Word`s with boxes) into chapters: strips running headers, page numbers and the back cover; builds paragraphs from indents, gaps and numbered items; joins drop caps and hyphenated breaks (keeping the hyphen of a compound such as 'good-luck'); fixes clear OCR word errors ('ofthe', 'SO', a quote mark read as '1', D-023); cuts chapters at headings confirmed by the contents page; places quiz answers after each question when the numbering allows (D-022). Returns notes for the report. | `rebuild(pages, lex) -> ScanResult`, `paragraphs(pages, lex, fixes)`, `load_scanned_pdf(path, progress) -> (Book, ScanResult)` |
| `ocr/words.py` | A yes/no English word check for the OCR fixes: the pronunciation dictionary shipped with Kokoro's G2P (misaki, ~216,000 entries) plus simple inflections ('berries', 'makes'), possessives and hyphenated compounds. Never suggests a replacement. Empty when misaki is not installed (CI), which turns the dictionary fixes off. | `load_lexicon() -> Lexicon`, `Lexicon.knows(word)` |
| `core/language.py` | Refuses books whose text isn't in a language the voices speak (English today), judged from the share of English function words in text sampled across the book. Metadata is only a hint. Called by `normalize` and by `build_book` before TTS loads. Holds `SUPPORTED_LANGUAGES` (moved from the TTS module, so core imports nothing else, D-033). | `check_language(book)`, `english_score(book)`, `SUPPORTED_LANGUAGES` |
| `tts/kokoro.py` | Wrapper around Kokoro-82M. One model on the GPU with one text pipeline per voice language (a/b) sharing it; `synth` is locked so a voice sample can run between two sentences of a conversion (D-031). One call per sentence, mono float32 at 24 kHz. Uses CUDA when available. | `KokoroTTS(voice, speed).synth(text, voice=None, speed=None)`, `VOICES`, `SAMPLE_RATE` |
| `tts/build.py` | Orchestrates the pipeline: plan, synthesize (cached), stitch with silence gaps, compute timestamps, encode m4a with ffmpeg, write `book.json` after each chapter. `ROOT` is the data folder (`EBOOK_AUDIO_DATA` or the project). | `build_book(source, out_root, voice, speed, progress, tts) -> Path`, `encode_m4a`, `ROOT`, `main()` |
| `server/service.py` | The backend, with no HTTP in it (D-032): drafts on disk with a clean worker (upload → `normalize` → review), a separate single-worker conversion queue for approved books (D-029), the library (list, manifest, file, delete) and cached voice samples. Every input check lives here, and refusals raise `Invalid` (400), `NotFound` (404) or `Conflict` (409). | `Drafts`, `Jobs`, `drafts`, `jobs`, `list_books()`, `read_book()`, `book_file()`, `delete_book()`, `voice_sample()`, `ServiceError` |
| `server/api.py` | The JSON API v1 (`APIRouter(prefix="/api/v1")`): thin routes that call `service.py` and return Pydantic models, which are the written contract for the web page and the Android app. Uploads are multipart and every other body is JSON. Every error is `{"detail": ...}`. | `router`, `API_VERSION`, models `Draft`, `DraftDetail`, `Job`, `BookSummary`, `Book`, `Info`, `ApproveRequest`, `Error` |
| `server/app.py` | The FastAPI `app`: includes the router, maps `ServiceError` to its status, serves `/` and `/static` (from `desktop/web/`), advertises mDNS (`path=/api/v1`) and prints the URLs at startup. No domain logic. | `app`, `advertise()`, `main()` |
| `web/` | `index.html` (markup), `app.css`, `app.js`: plain files with no build step. They display data and call only `/api/v1`; they don't clean or convert anything (checked by `test_api03`). Single-page UI with three tabs (D-030): **Clean** (upload with OCR mode, clean or clean & convert, "Cleaning & review" list), **Convert** (upload a cleaned `.std.epub`, approved books, conversion progress), **Library**. Also: review page (check-by-hand list, chapters and their text, removed parts, approve / Sigil download and upload / discard), conversion progress, library grid, reader with sentence highlighting and tap-to-seek. | served at `/` |

## On-disk layout

Data folders sit in the project, or under `EBOOK_AUDIO_DATA` (`library/`, `cache/`, `drafts/`). Model caches always
sit in the project.

```
<name>.std.epub            cleaned book next to its source (e.g. samples/), plus <name>.std.report.txt
library/<book_id>/          book_id = <title-slug, max 40 chars>-<sha1(original file)[:8]>;
                            a .std.epub carries the original's sha1, so cleaning or editing keeps the id
    book.json               manifest (below)
    ch000.m4a, ch001.m4a…   AAC 64 kbps mono 24 kHz, +faststart
    cover.<ext>             optional
models/huggingface/         Kokoro-82M (HF_HOME), downloaded on first use (D-028)
models/doctr/               docTR OCR models (DOCTR_CACHE_DIR), downloaded on first use
cache/voice-samples/<voice>-<sha1(text)[:8]>.m4a  ~5 s sample per voice, made on first ▶ click and kept
cache/<book_id>/<sha1>.npy  per-sentence audio, key = sha1("voice|speed|text"); deleted when the book completes
drafts/<id>/                one per book uploaded through the server (D-029); removed by Discard
    <name>.<ext>            the upload, under its own sanitized name (stem capped at 80 chars: Windows path limit)
    book.std.report.txt     the same report as text (written by normalize)
    book.std.epub           the cleaned book (replaced by an uploaded edit)
    report.json             the cleaning Report: method, chapters, removed, unconfirmed, notes, checks
    draft.json              id, file, status, message, done/total, auto, voice, speed, error,
                            chapters, checks, job_id, book_id, source_sha1, created
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
  "chapter_selection": null,
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
- `chapter_selection` is `null` for a full book, or the `--chapters` spec (e.g. `"2-4"`) for a partial one.
- `complete: false` means the book is still converting (or was interrupted), but the chapters listed so far are playable.

## HTTP API v1 (D-032)

The web page and the Android app use the same API. All paths are under `/api/v1`, and the schemas are in
`/openapi.json` (browsable at `/docs`). A breaking change goes into a new `/api/v2`; v1 keeps working. Uploads are
multipart, every other body is JSON, and every error is `{"detail": "..."}` with 400 (invalid input), 404 (unknown
id), 409 (wrong state) or 422 (a field of the wrong type, where `detail` is FastAPI's list). `test_api01` pins the exact
route list.

Not under `/api/v1`: `GET /` (the web page), `/static/*` (its files), `/docs` and `/openapi.json`.

| Method & path | Purpose |
|---|---|
| `GET /info` | `{api_version: 1, name, url, qr_svg, voices, default_voice, ocr_modes}` |
| `GET /voices/{voice}/sample` | ~5 s m4a of the voice reading a fixed sentence (made once, then cached); 404 for an unknown voice |
| `POST /drafts` | Upload and clean. Multipart `file`, `voice`, `speed` (0.5–2.0), `auto`, `ocr` (`auto`/`always`/`never`, PDF only) → `{draft_id}`. Waits for review, or converts at once with `auto=true` (replaces the old `/api/clean` and `/api/convert`) |
| `POST /drafts/cleaned` | Multipart `file` (a cleaned `.std.epub`), `voice`, `speed` → `{draft_id, job_id}`. No cleaning; converted at once. 400 for anything without the `ebook-audio:normalized` marker |
| `GET /drafts` | All drafts (`Draft`: status, message, OCR progress, chapters, checks, job and book ids) |
| `GET /drafts/{id}` | One draft plus its `report` (null until cleaned) |
| `GET /drafts/{id}/chapters/{n}` | `{index, title, paragraphs}` of one cleaned chapter; 409 before cleaning |
| `GET /drafts/{id}/std.epub` | Download the cleaned book (for Sigil); 409 before cleaning |
| `PUT /drafts/{id}/std.epub` | Replace it with an edited `.std.epub` (multipart `file`) → `{chapters}`; 400 if unreadable |
| `POST /drafts/{id}/approve` | JSON `{voice?, speed?}` (or no body: the voice and speed chosen at upload) → `{job_id}`; 409 unless the draft is in review or done |
| `DELETE /drafts/{id}` | Discard a draft and its files; 409 while cleaning or converting |
| `GET /jobs` | All conversion jobs (`Job`: queued/running/done/error, `done`/`total` sentences, message, `draft_id`, `book_id`) |
| `GET /jobs/{id}` | One job's progress |
| `GET /books` | Library summary (`BookSummary`: title, author, cover, chapters, duration, size, complete) |
| `GET /books/{id}` | The full `book.json` (`Book`) |
| `GET /books/{id}/files/{name}` | A chapter's audio or the cover, with HTTP Range (206). To download a book, fetch each chapter's `audio` file from the manifest; an interrupted download resumes with `Range: bytes=<have>-` |
| `DELETE /books/{id}` | Delete a book folder |

Book and draft IDs are validated against `^[a-z0-9\-]{1,80}$` (a draft id must also be a known draft), and file
names reject `/`, `\`, and a leading `.` (path-traversal guard).

## Concurrency model
- Two background daemon threads, each draining its own `queue.Queue`: the clean worker (`Drafts`) and the
  conversion worker (`Jobs`). Cleaning a new book never waits for a conversion; conversions run one at a time
  (one TTS model in memory). docTR is freed after OCR, so both fit on the GPU.
- One `KokoroTTS` is loaded on first use (`Jobs.model()`, its own lock) and kept for every job and voice sample, in
  both voice languages. Only the conversion worker sets its current voice; a sample passes its own.
- Drafts are saved to `draft.json` on every change and reloaded at startup. Jobs live in memory only; a draft whose
  conversion was cut off by a restart goes back to review and resumes from the sentence cache when approved again.

## External dependencies
Python 3.10–3.12, PyTorch (CUDA build recommended), `kokoro`, `ebooklib`, `beautifulsoup4`, `lxml`,
`pymupdf`, `pysbd`, `fastapi`, `uvicorn`, `python-multipart`, `zeroconf`, `qrcode`, and
**ffmpeg on PATH**.

Optional, for scanned PDFs only: `python-doctr` from `requirements-ocr.txt`, which pins torch/torchvision to
the CUDA build so the TTS keeps the GPU (D-021). It is not in `requirements-ci.txt`; the tests use a fake engine.
