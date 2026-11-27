# Desktop component: decision log

Each entry records why a design choice was made. Entries D-001 to D-012 were written after M1–M3
and reconstructed from the code and its comments. Add new entries at the bottom and never
renumber old ones. If a decision is reversed, add a new entry that supersedes the old one and
mark the old one `Superseded by D-xxx`.

Template:

```
## D-NNN Title
Status: Accepted | Superseded by D-xxx · Milestone: Mx
Context: what problem or constraint forced a choice
Decision: what we chose
Why: reasons, alternatives rejected
Consequences: trade-offs we accept
```

---

## D-001 Local TTS with Kokoro-82M
Status: Accepted · Milestone: M1
**Context:** Books are long (hundreds of thousands of words). Cloud TTS costs scale per character, and
the book text would leave the machine.
**Decision:** Run Kokoro-82M locally through the `kokoro` package, on CUDA when available and on the CPU otherwise.
**Why:** It is free to run, private, and offline. Its English quality is high for its size, and 82M parameters fit easily on a
consumer GPU.
**Consequences:** It needs PyTorch and a GPU for reasonable speed. It supports English voices only (American `a*`, British `b*`).
The first run downloads the model from Hugging Face.

## D-002 Synthesize one sentence at a time for exact timestamps
Status: Accepted · Milestone: M2
**Context:** The player must highlight the sentence being read and let the user tap a sentence to seek.
**Decision:** Call TTS once per sentence and stitch the results. The timestamp of each sentence is its sample offset.
**Why:** The timestamps are exact by construction, so no forced-alignment model (e.g. aeneas/WhisperX) and
no extra dependency or error source are needed.
**Consequences:** Prosody does not flow across sentence boundaries. There are more TTS calls, each with some overhead.
Segmentation quality directly drives both audio and highlight quality (see D-004).

## D-003 Gap ownership: a sentence's end_ms equals the next sentence's start_ms
Status: Accepted · Milestone: M2
**Context:** Silence is inserted between sentences (250 ms) and between paragraphs (600 ms), and there is a 300 ms chapter lead-in.
**Decision:** The pause after a sentence belongs to that sentence. `end_ms[k] = start_ms[k+1]`, and the last
`end_ms` equals the chapter duration.
**Why:** Every playback position maps to exactly one sentence, so the player can binary-search over `start_ms`
alone, with no "between sentences" state.
**Consequences:** The highlight stays on a sentence through the pause that follows it, which is the intended behavior.

## D-004 pysbd segmentation with a 350-character cap and punctuation-only merging
Status: Accepted · Milestone: M2
**Context:** A naive split on `.` breaks on "Mr.", ellipses, and quotes. Very long sentences give coarse highlighting and
worse TTS quality. Fragments like `* * *` produce empty or odd audio.
**Decision:** Use pysbd (`clean=False`). Split sentences over 350 chars at the last soft break (`, ; : — – ( )`)
in the second half of the window, falling back to the last space and then to a hard cut. Attach fragments with no
letters or digits to the previous sentence, or drop them if they open a paragraph.
**Why:** pysbd is rule-based and fast, and it handles abbreviations and quotes well. `clean=False` keeps the text faithful.
**Consequences:** Segmentation is English-only. A hard cut can split a word in the rare case of 175+ characters without a space.

## D-005 Uniform `Book` model with paragraph-per-line chapter text
Status: Accepted · Milestone: M2
**Context:** EPUB, PDF, and TXT expose structure differently.
**Decision:** Every loader produces `Book(title, author, chapters[Chapter(title, text)], cover)`, where
`text` has one paragraph per line. Chapters shorter than 40 chars are dropped.
**Why:** Downstream code (segmentation, build) stays format-agnostic. The 40-char floor removes cover pages and blank
separators that would become near-empty chapters.
**Consequences:** Format-specific chapter heuristics live only in `parse.py`:
- EPUB: chapters follow the spine. Titles come from the TOC, then the first heading.
- PDF: chapters come from the level-1 outline, falling back to 15-page parts. The cover is a render of page 1.
- TXT: chapters come from heading lines ("Chapter N", "Part", "Prologue", …), falling back to ~20k-char parts. The encoding is tried as UTF-8, UTF-16, cp1252, then latin-1.

## D-006 One m4a per chapter, AAC 64 kbps mono, faststart
Status: Accepted · Milestone: M2
**Context:** The files must stream and seek well on Android (Media3) and in browsers, and stay small for download.
**Decision:** Encode each chapter separately with ffmpeg: AAC at 64 kbps, mono, 24 kHz, `+faststart`. Normalize the audio only if the peak exceeds 1.0.
**Why:** Per-chapter files keep timestamps chapter-relative, allow partial books, and keep files a manageable size.
AAC/m4a is supported natively everywhere. Speech needs little bitrate. `faststart` puts the moov atom first
for progressive playback.
**Consequences:** It needs ffmpeg on PATH. Encoding writes a `.tmp.m4a` file, then renames it, so a crash never leaves a half-written chapter.

## D-007 Per-sentence disk cache for resumable builds
Status: Accepted · Milestone: M2
**Context:** Converting a book takes a long time, and crashes or Ctrl+C should not waste GPU work.
**Decision:** Cache each sentence's audio as `.npy` under `cache/<book_id>/`, keyed by `sha1(voice|speed|text)`. Delete the
cache when the book completes.
**Why:** It is the simplest resume mechanism, because re-running the build replays cached sentences instantly. Including voice and speed in the key
prevents stale audio after either setting changes.
**Consequences:** The cache can grow to several GB of raw float32 for a large book until the book completes. Encoding
and manifest writing rerun from scratch on resume.

## D-008 Write the manifest after every chapter
Status: Accepted · Milestone: M2
**Context:** The user wants to start listening before a long conversion finishes.
**Decision:** Rewrite `book.json` atomically (tmp file, then replace) after each chapter, with `complete: false` until the end.
**Why:** A partial book is playable immediately, and the atomic replace means readers never see torn JSON.
**Consequences:** Clients must handle `complete: false` and a growing chapter list.

## D-009 `book_id` = title slug + file hash
Status: Accepted · Milestone: M2
**Context:** IDs must be URL-safe, readable, stable across re-runs (for resume), and unique per file.
**Decision:** `<slug(title)[:40]>-<sha1(file bytes)[:8]>`.
**Why:** The same file always gets the same ID, which is what resume needs, and different editions with the same title don't collide.
**Consequences:** Converting the same file again with another voice reuses the ID and overwrites the previous audio.

## D-010 Single-worker in-memory job queue
Status: Accepted · Milestone: M3
**Context:** There is one GPU and one loaded model, and conversions are long.
**Decision:** One daemon thread processes a `queue.Queue` sequentially. Job state is a dict in memory. The loaded model is reused while the
voice language prefix is unchanged, and the voice and speed are swapped per job.
**Why:** It needs no database or broker, and it avoids GPU memory contention and loading the model twice.
**Consequences:** Jobs are lost when the server restarts, though cached sentences make a manual re-upload cheap. There is no cancellation and
no parallelism.

## D-011 LAN discovery via mDNS plus a QR code fallback
Status: Accepted · Milestone: M3
**Context:** The phone app must find the PC without the user typing an IP address.
**Decision:** Advertise `_ebookaudio._tcp.local.` with zeroconf, and show the LAN URL as a QR code in the web UI.
**Why:** mDNS gives zero-config discovery when the network allows multicast. The QR code covers networks that block it.
Both are optional, so failures only print a hint.
**Consequences:** The server binds to `0.0.0.0` with no authentication. It is intended for trusted home networks only.

## D-012 Dependency-free single-file web UI
Status: Accepted · Milestone: M3
**Context:** The UI needs a quick way to convert and test playback before the Android app exists.
**Decision:** One static `index.html` with inline CSS/JS, no build step and no framework.
**Why:** There is nothing to install or bundle, and FastAPI serves it directly. It also serves as a reference implementation of
the sentence-sync logic for the Android app (binary search over `start_ms`).
**Consequences:** It will get harder to maintain if the UI grows. If it does, revisit this decision with a new entry.

## D-013 CI with a lighter dependency set, required before merge
Status: Accepted · Milestone: M3
**Context:** Tests must pass before anything merges into `master`. The automated tests use a fake TTS
and never import Kokoro or PyTorch, but `requirements.txt` pulls in `kokoro` and with it PyTorch
(about 1 GB, several minutes to install on every CI run).
**Decision:** A GitHub Actions workflow runs `pytest` on Ubuntu with Python 3.10 and ffmpeg, installing
`requirements-ci.txt` (everything except `kokoro`/`soundfile`). Branch protection on `master`
requires a PR (0 approvals, solo project) and the `test` check to pass. It applies to admins too, and
it blocks force pushes and branch deletion.
**Why:** It keeps CI fast (about 1 minute), and `tts.py` imports torch/kokoro lazily, so nothing tested needs them.
Ubuntu runners start fastest, and the code is platform-neutral.
**Consequences:** CI does not prove that the full `requirements.txt` installs, or that the real TTS works.
Those stay manual checks (TTS-* cases). When code starts importing a new package, add it to both
requirements files.

## D-014 Synthetic EPUB fixtures built at test time
Status: Accepted · Milestone: M3
**Context:** Parser tests need EPUBs with real-world structure (front matter, nested TOC, footnote
markers, covers). The sample books available are copyrighted, and this repository is public.
**Decision:** `tests/epub_factory.py` writes small EPUBs with ebooklib into pytest's `tmp_path` while the tests run.
It uses only made-up text. Real sample books stay local in the git-ignored `samples/` folder for manual end-to-end runs.
**Why:** Committing real books, or excerpts of them, would redistribute copyrighted text. Generated fixtures are
diffable code rather than binaries, CI can run them, and each one targets one structure on purpose.
The factory refuses pages under `MIN_CHAPTER_CHARS` unless they are marked `allow_short`, so a fixture can't
be dropped by the parser without anyone noticing.
**Consequences:** The fixtures are only as realistic as we make them. When a real book shows a new quirk, add
a synthetic spec that reproduces it. Known gaps are encoded as `xfail(strict=True)` tests.
