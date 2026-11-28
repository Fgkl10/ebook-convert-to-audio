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

## Index

One row per entry, in both files; add a row when you add an entry. "Parts" names the subpackages the decision
touches, so decisions about one part can be found without reading the whole log. "Relation" shows how an entry
changes another. "File": *here* entries are below; settled entries that are unlikely to change are in
[`decisions-archive.md`](decisions-archive.md) and still in force. New entries go here. Search this table for a
keyword, then read only that entry.

| ID | Title | Parts | Relation | File |
|---|---|---|---|---|
| D-001 | Local TTS with Kokoro-82M | tts | | here |
| D-002 | Synthesize one sentence at a time for exact timestamps | tts | | here |
| D-003 | Gap ownership: end_ms equals the next start_ms | tts | | [archive](decisions-archive.md) |
| D-004 | pysbd segmentation, 350-character cap | core | | here |
| D-005 | Uniform `Book` model | core | | here |
| D-006 | One m4a per chapter, AAC 64 kbps mono | tts | | [archive](decisions-archive.md) |
| D-007 | Per-sentence disk cache for resumable builds | tts | | [archive](decisions-archive.md) |
| D-008 | Write the manifest after every chapter | tts | | [archive](decisions-archive.md) |
| D-009 | `book_id` = title slug + file hash | tts | | [archive](decisions-archive.md) |
| D-010 | Single-worker in-memory job queue | server | | [archive](decisions-archive.md) |
| D-011 | LAN discovery via mDNS plus a QR code | server | | [archive](decisions-archive.md) |
| D-012 | Dependency-free single-file web UI | web | | [archive](decisions-archive.md) |
| D-013 | CI with a lighter dependency set | tests, CI | | [archive](decisions-archive.md) |
| D-014 | Synthetic EPUB fixtures built at test time | tests | | [archive](decisions-archive.md) |
| D-015 | Lenient HTML parser for XHTML | core | | [archive](decisions-archive.md) |
| D-016 | Skip EPUB front matter | core | Amended by D-042 (Chinese titles) | [archive](decisions-archive.md) |
| D-017 | `--chapters` conversions go to their own folder | tts | Amended by D-035 | [archive](decisions-archive.md) |
| D-018 | Refuse unsupported languages, judged from the text | core, tts | Amended by D-042 (Chinese) | here |
| D-019 | Clean every book into a standard EPUB | core, server | Web part superseded by D-029 | [archive](decisions-archive.md) |
| D-020 | Cut chapters only at confirmed headings | core | Refined by D-024, D-025 | here |
| D-021 | Scanned PDFs read with docTR (optional) | ocr | Extended by D-030 | [archive](decisions-archive.md) |
| D-022 | Quiz answers read right after each question | ocr | | [archive](decisions-archive.md) |
| D-023 | OCR word fixes by rules and a word list | ocr | | [archive](decisions-archive.md) |
| D-024 | A nested TOC's top level is the chapter list | core | Refines D-020 | here |
| D-025 | Cut fewer rather than too many | core | Refines D-020, D-024 | here |
| D-026 | Note-reference links stripped from running text | core | | [archive](decisions-archive.md) |
| D-027 | Footnote paragraphs removed | core | Extends D-025, D-026 | [archive](decisions-archive.md) |
| D-028 | Model caches live inside the project | tts, ocr | Amended by D-044 (jieba, v1.1-zh) | [archive](decisions-archive.md) |
| D-029 | Cleaning is its own step on the website | server, web | Supersedes the web part of D-019 | [archive](decisions-archive.md) |
| D-030 | OCR mode, Clean and Convert pages | ocr, server, web | Extends D-021, D-029 | [archive](decisions-archive.md) |
| D-031 | One TTS model for both voice languages; voice samples | tts, server | Amended by D-043, D-044 | here |
| D-032 | Backend, JSON API v1 and web page as layers | server, web | Changes routes of D-029 to D-031; routes in [api.md](api.md) | here |
| D-033 | Subpackages and one-way imports | all | | [archive](decisions-archive.md) |
| D-034 | Per-chapter download with a readable name | server, web | | [archive](decisions-archive.md) |
| D-035 | Choose chapters; add them to one library entry | tts, server, web | Amends D-017 | here |
| D-036 | Safe to stop with Ctrl+C | tts, server | | [archive](decisions-archive.md) |
| D-037 | Pairing a phone: token and address choice | server, web | | here |
| D-038 | Cancel a conversion, chapter versions | tts, server, web | | here |
| D-039 | Web reader: sentence buttons and text size | web | same rules as android A-015 | here |
| D-040 | Web page in English, Simplified and Traditional Chinese | web | android A-017 | here |
| D-041 | README in three languages; MIT license | repo | exception to "everything in English" | here |
| D-042 | Chinese books: detection, cleaning rules, sentences | core | Amends D-018, D-016 | here |
| D-043 | Voices by language: two pickers, fallback, Chinese pronunciation | tts, server, web | Amends D-031; android A-021 | here |
| D-044 | Optional Kokoro v1.1-zh for better Chinese voices | tts, server, web | Amends D-031, D-028 | here |
| D-045 | TTS behind a backend interface; a setting picks the backend | tts, server, web | Amends D-031 | here |
| D-046 | Voice names from measured pitch and pace | tts, server, web | android A-022 | here |

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
**Consequences:** Since D-019, "one file = one chapter" holds by construction for cleaned books. The
normalizer writes exactly one XHTML file per chapter. Format-specific chapter heuristics live only in `parse.py`:
- EPUB: chapters follow the spine, with front matter skipped (D-016). Titles come from the TOC, then the first heading.
- PDF: chapters come from the level-1 outline, falling back to 15-page parts. The cover is a render of page 1.
  Scanned PDFs skip this: `normalize` rebuilds them from OCR (D-021, D-022).
- TXT: chapters come from heading lines ("Chapter N", "Part", "Prologue", …), falling back to ~20k-char parts. The encoding is tried as UTF-8, UTF-16, cp1252, then latin-1.

## D-018 Refuse books in languages the voices can't speak, judged from the text
Status: Accepted, amended by D-042 (Chinese is detected and accepted too) · Milestone: M3
**Context:** All voices are English (`a*`/`b*`), and the sentence splitter is English-only. A Hungarian book
would be read with English pronunciation. Internet books often have wrong `dc:language` metadata (the
Hungarian Kokology's chapter files say `lang="en"` while its OPF says `hu`), and PDF/TXT usually have none.
**Decision:** `language.check_language` samples up to 400 words from each of about 6 chapters spread across the book,
and computes the share that are common English function words. Below 0.15 it raises `ValueError` naming the metadata
language (if any) and `tts.SUPPORTED_LANGUAGES`. Under 100 sampled words, the book is accepted, because there is too little to judge.
`build_book` calls it right after loading, before any TTS or file writes.
**Why:** It needs no new dependency, and the measured separation is wide. English is 0.32 (noisy OCR scan) to 0.44, while Hungarian
is 0.00 and German/French/Spanish/Dutch prose 0.00 to 0.08. Words common in other languages ("a", "i", "is", "in")
are excluded. The text decides because metadata is unreliable.
**Consequences:** Only English versus not-English is detected, with no identification of the actual language. A wrongly refused English book can be
forced through with the CLI flag `--ignore-language` (LANG-07). The web UI has no override. Adding a language means adding voices and a detector for it.

## D-020 Chapters are cut only at headings confirmed in the text
Status: Accepted · Milestone: M3
**Context:** In Smart Notes, TOC and contents-page anchors are page markers (`#page_76`) from the print edition,
not chapter starts. "12 Develop Ideas" points mid-list on the page where chapter 12 begins. The navigation TOC
missed chapters 5 and 9, and the book's own contents page listed all of them.
**Decision:** Candidates come from the navigation TOC plus links on contents pages (≥5 contents entries making up ≥60% of the
page; an entry is a paragraph of at most 150 chars whose text is ≥80% link text into another file, so endnotes
that open with a backlink are not mistaken for a contents page). Links in one paragraph sharing an href are joined, as when one title is split over two links. Candidates are
dropped if implausible (over 120 chars, fewer than 3 letters, lowercase first letter, ending in a glued footnote number
like `)11`) or if they are an `N.M` subsection of an existing chapter `N`. A whole-file entry cuts at the
file start, unless the file is a contents page or listed in the guide as front matter. Otherwise the cleaner
searches from the anchor for a block whose opening element, or first lines joined (up to 3), equals the
title. Unconfirmed candidates are ignored and reported. Entries with the same title are kept as separate chapters
when they land on different blocks. A spine file that opens with a real `<h1>`–`<h3>` also starts a chapter
even when the TOC leaves it out (sparse TOCs, TOCs listing only parts); Calibre's mid-text splits don't open
with h-tags, so they are unaffected. With no confirmed cut, it falls back to one chapter per file.
A heading that opens a paragraph gets its own line, so it is spoken with a pause. Part headings under 40 chars
are read with the next chapter.
**Why:** Text confirmation is also the junk filter, and nothing relies on Calibre class names (the test fixture
uses random ones). On the real books, Smart Notes gives Preface, Introduction, 1 to 14, Afterword and Appendix,
and Counselling for Toads comes out identical (16 chapters, same text).
**Consequences:** Text before the first confirmed chapter is removed as front matter, so a prologue missing from
the TOC would be dropped, though it is shown in the report. Footnote texts inside chapters are still read aloud. An empty file
(only labelled front matter) is skipped, so a TOC entry for it can't borrow the next file's start.

## D-024 A nested TOC's top level is the chapter list; its children are sections
Status: Accepted · Milestone: M3 · Refines D-020
**Context:** The Art of Game Design (publisher EPUB, one file per chapter) has 35 chapters, but the cleaner gave 647
pieces. Its TOC nests sections (and sub-sections) under each chapter, all pointing into the chapter's file, and D-020
treated every entry as a chapter. A second contents page, the "Table of Lenses", linked to boxes inside the chapters
and added more cuts. The chapter titles were also lost: the TOC says "1 In the Beginning, There Is the Designer" while
the page prints "CHAPTER ONE" over "In the Beginning, There Is the Designer", so the entry never matched, and the h-tag
rule named the chapter "CHAPTER ONE". The half-title page's own `<h1>` ("Tenth Anniversary") became a chapter, and
"Copyright Page" was not a known front-matter title. One "missing" section, "Problem #3", is printed as body text with
no heading or TOC entry in the source; its text was there, inside the "Problem #2" piece.
**Decision:**
- With a nested TOC, candidates are its top-level entries plus nested entries that open a file of their own (no
  anchor, or an anchor on the file's first block), which is how chapters sit under part titles. Other nested entries
  are sections and stay inside their chapter. Contents-page links are not used, since the nested TOC already gives the
  structure. A flat TOC works as before (D-020), including contents-page links.
- Matching a title to a heading ignores one leading label on either side: "chapter/part/book" plus a word, or a bare
  number. "1 In the Beginning" matches "CHAPTER ONE" + "In the Beginning". The chapter keeps the TOC's title.
- Files that a TOC entry labels as front matter ("Half Title", "Copyright Page", "Dedication Page", "Cover") never
  start a chapter through the h-tag rule, and the front-matter titles gain those names.
**Why:** In a nested TOC the publisher already says what is a chapter and what is a section; splitting every section
off produces hundreds of 300-character "chapters" with no chapter names. Entries that open their own file are still
chapters, so books with parts at the top level keep their chapters (NORM-13). The other samples (Smart Notes,
Counselling for Toads) have flat TOCs and give the same chapters and text as before.
**Consequences:** The Art of Game Design gives 39 chapters: Hello, 1–35, Goodbye, Acknowledgments and Endnotes, with all
the text the old cut had except the half-title and copyright pages. Section headings are read inside the chapter,
each on its own line. A book whose nested TOC lists chapters as anchors inside one big file (a single-file book with
parts at the top) would now get only the parts as chapters; no sample has that shape (NORM-19, a known gap). Figure
labels ("FIGURE 1.1") and the Endnotes chapter are still read aloud (both removed by D-025).

## D-025 Cut fewer rather than too many: chapters are cut at the chapter heading level; endnotes and figure labels go
Status: Accepted · Milestone: M3 · Refines D-020, D-024
**Context:** D-024 fixed The Art of Game Design for its nested TOC, but the same book with a flat TOC (chapters and
sections side by side, as many books list them) would still give hundreds of pieces. The user asked to make the
cleaner general and stated the principle: "宁可少分一点也不要切得太碎" (rather cut a bit less than chop the book
into fragments). They also asked to drop the Endnotes chapter and the figure labels ("FIGURE" over "1.1", 145 in
that book).
**Decision:**
- **Chapter level.** The heading level chapters use is taken from the confirmed cuts that carry real text (at least
  `MIN_CHAPTER_CHARS`, not front or back matter). For a book with a file per chapter, it is the most common level among
  cuts that open a file; for a single-file book, it is the highest level with 3 or more such cuts, so a lone h1
  "Introduction" and "Epilogue" don't outrank twelve h2 chapters. Short part titles never set it.
- **Sections stay inside.** With a flat TOC, a mid-file cut on a heading below the chapter level is a section and
  stays in the chapter before it. So is a mid-file cut on no heading at all (a box, a `<p>` line), but only when most
  cuts are on headings: Calibre books put their chapters on `<p>` lines, and Smart Notes must keep its 14 chapters.
  A cut that opens a file is never dropped, because text before the first cut would be lost as front matter. The
  report lists what was kept inside.
- **h-tag rule.** A spine file opening with a heading below the chapter level no longer starts a chapter.
- **Back matter.** "Notes", "Endnotes", "End notes" and "Footnotes" join Bibliography, References and Index. They are
  removed in every format, not only EPUB.
- **Figure labels.** A line that is only a label ("Figure 2.1", "Fig. 4b", or "FIGURE" over "17.3a") is removed in
  every format, and the count is shown in the report. A label followed by a caption or prose ("Figure 17.4 shows…")
  stays.
- An already-cleaned `.std.epub` is left as it is, so edits made in Sigil survive.
**Why:** A heading level is a general signal, set by the publisher, that does not depend on any one book's titles. When
unsure, merging keeps the listening order and loses nothing; an extra cut adds a tiny "chapter" with no name. Endnotes
read in a row are meaningless as audio, and figure labels point at pictures the listener cannot see.
**Consequences:** The Art of Game Design gives 38 chapters, and still 38 when its TOC is flattened; the only text removed is
the Endnotes chapter and the 145 labels. Smart Notes and Counselling for Toads give the same chapters and text as before.
A single-file book whose parts carry intro text (3 or more) is cut by part only, a deliberate under-split. In-text note
references ("…as Jung showed.12") are still read aloud and now point at notes that are not read (NORM-11; removed by D-026).

## D-031 One TTS model for both voice languages; cached voice samples
Status: Accepted, amended by D-043 (a Chinese pipeline on the same model) and D-044 (an optional second model) · Milestone: M3
**Context:** The user wants to hear each voice before choosing one. A sample needs the TTS model, which may be busy
with a conversion in the other voice language; before, the server reloaded the whole model whenever the language
(American a / British b) changed, which would also break a running conversion.
**Decision:** `KokoroTTS` loads one `KModel` and makes a `KPipeline` per language on first use, passing the model in.
`synth(text, voice=None, speed=None)` runs under a lock, so a sample is made between two sentences of a conversion and
passes its own voice instead of changing the conversion's. `Jobs.model()` loads it once, under its own lock (not the
job-list lock, so loading never freezes the progress display). `GET /api/voices/{voice}/sample` reads one fixed
made-up sentence (~5 s), encodes it with `encode_m4a` into `cache/voice-samples/<voice>-<sha1(text)[:8]>.m4a` once,
and serves the file afterwards. The page has a ▶ button next to every Voice list.
**Why:** Sharing the model keeps one copy on the GPU and makes language switches free. Caching makes every later
click instant. The text hash in the file name means changing the sentence makes new samples without manual cleanup.
**Consequences:** The first ▶ of a session waits for the model to load (~10 s), and the first sample of each voice
~4 s (it downloads the voice file into `models/`). During a conversion a sample waits for the current sentence.
Samples are never deleted automatically (about 50 kB each).

## D-032 Backend, JSON API v1 and web page as separate layers in one server
Status: Accepted · Milestone: M3 · Changes the routes of D-029, D-030 and D-031
**Context:** The Android app (M4+) will do everything the web page does: upload, clean, review the report, approve,
follow the conversion, list the library and download audio. In `server.py` the domain logic (`Drafts`, `Jobs`,
library reading, voice samples) was mixed with the HTTP routes and raised `HTTPException`. The URLs had no version,
approve took HTML form fields, and the responses had no written schema. The page held its HTML, CSS and JS in one
file. The user wanted the backend and the frontend apart while keeping one server and one start command, and no
separate frontend project or build step.
**Decision:**
- **`service.py`** is the backend, with no FastAPI import. It holds `Drafts`, `Jobs`, the library functions and the
  voice samples. All input checks live there (voice, speed, OCR mode, file type), and refusals raise `Invalid`,
  `NotFound` or `Conflict`, each carrying its HTTP status.
- **`api.py`** is the JSON API, `APIRouter(prefix="/api/v1")`. Its routes are thin, and its Pydantic response models
  are the contract (`/openapi.json`, browsable at `/docs`). One exception handler turns a `ServiceError` into
  `{"detail": msg}`, the same shape FastAPI uses for its own errors.
- **`server.py`** builds the app, serves `/` and `/static`, advertises mDNS with `path=/api/v1`, and starts uvicorn.
- **`static/`** is `index.html`, `app.css` and `app.js`. The page only displays data and calls `/api/v1`.
- The routes follow resources:
  - `POST /drafts` replaces `/api/clean`, and `/api/convert` is dropped, since it is the same call with `auto=true`;
  - `POST /drafts/cleaned` replaces `/api/convert-std`;
  - the edited std is replaced with `PUT /drafts/{id}/std.epub`;
  - `GET /jobs/{id}` is new, so a client can follow one conversion.
- Uploads stay multipart; every other body is JSON. Approve takes `{voice?, speed?}`, and a field left out falls back
  to the choice made at upload.
- Downloads stay per file: the manifest lists each chapter's `.m4a`, fetched with HTTP Range. There is no zip.
- The old unversioned routes are removed rather than kept as aliases. This page was their only client.
- `EBOOK_AUDIO_DATA` (read by `build.ROOT`) moves `library/`, `cache/` and `drafts/` out of the project.
  `tests/conftest.py` sets it before anything is imported.
**Why:**
- A versioned prefix lets installed copies of the app keep working when the API changes: a breaking change goes into
  `/api/v2`, and `/info` reports `api_version` so the app can refuse a server it doesn't support.
- JSON bodies are what Android HTTP clients (Retrofit, Ktor) send by default.
- Per-file downloads resume chapter by chapter over flaky Wi-Fi, and a finished chapter plays while the rest is still
  downloading.
- With no HTTP in the backend, it can be tested and reused (the CLI, a later desktop app) without a server.
- `test_api01` pins the exact route list, so any change to the contract shows up as a failing test that has to be
  changed on purpose.
- The data-folder override fixes a real incident: a test server, and even importing the server module in a test run,
  shared and rewrote the drafts of the user's running server.
**Consequences:**
- Bookmarks or scripts that call `/api/...` must move to `/api/v1/...`.
- The page is still served by the same process, so the web UI and the API always match in version.
- A new endpoint needs a model in `api.py`, a line in `EXPECTED_ROUTES` and a test.
- There is still no authentication (D-011): the API is for a trusted home network.

*Follow-up (page only):*
- The Clean and Convert forms show their progress and errors under themselves instead of in pop-ups. A slow reply,
  such as a refused upload arriving after a tab switch, can then never look as if the other form sent it.
- An original book uploaded on the Convert page brings up "Clean it now?", which sends it to the Clean step.
- The OCR menu reads "OCR (PDF only)". Disabled controls are visibly greyed out in both themes, and a line explains
  that EPUB and TXT need no OCR.

## D-035 Choose which chapters to convert; they are added into the book's one library entry
Status: Accepted · Milestone: M3
**Context:** Approve on the web page always converted the whole book. The CLI's `--chapters` (D-017) writes a
separate `-ch<spec>` test folder, so converting a book a few chapters at a time made one library entry per batch.
The user wanted to tick chapters on the Review page and add them to the same book, converting more later.
**Decision:**
- **Web page and API.** Each chapter on the Review page has a checkbox, and `POST /drafts/{id}/approve` takes
  `chapters`, a list of 1-based numbers (null means all).
  - The chosen chapters go into `library/<book_id>/` with `build_book(..., merge=True)`. A chapter converted before
    is replaced; all the others are kept.
  - `book_id` is computed at approval, so the library can say "converting" while the job is still queued.
- **Numbering.** Chapters keep their number in the cleaned book.
  - In `book.json` each chapter has `number`, and its audio is `ch{number-1:03d}.m4a`. It is shown in the reader and
    used in download names (this changes D-034's position numbering).
  - Books from before D-035 have no `number`: it comes from the audio name for a full book, which stays exact when an
    empty chapter was skipped. Position + 1 would be off by one there, and a merge would overwrite the wrong file.
- **Voice.** Each chapter records its own `voice` and `speed`.
  - The Review page defaults to the library book's voice and speed.
  - When the user picks another voice while converted chapters stay, a line warns that the book will mix voices. It
    doesn't block.
- **Edited chapters.** Each chapter stores `text_sha1`. On Review, a converted chapter whose cleaned text has
  changed since (a Sigil edit) is not marked "converted", so it is ticked again by default. A chapter with no hash
  (older books) counts as converted.
- **Default ticks.** Every chapter not converted yet. After an interrupted or failed run, only that run's chapters
  that are still missing (`last_chapters` on the draft, cleared by a Sigil upload).
- **Cache.** Merged runs share `cache/<book_id>/`. A run that succeeds deletes only its own chapters' sentences. The
  whole folder goes when the book is complete. Without this, finishing chapter 9 would wipe the cache of an
  interrupted run of chapters 3–6, and that run could no longer resume.
- **`complete`** now means "every chapter with text is converted". It used to mean "the run finished".
  - `chapters_total` and a `converting` flag (from the job queue) were added to `BookSummary`.
  - This is a deliberate change of meaning inside v1, against the rule in `api.py` that breaking changes go to
    v2. It is made in v1 because no Android client exists yet. For a full conversion the value is the same as
    before.
- **The CLI stays separate** (the user's choice). `--chapters` still writes the `-ch<spec>` test folder, so test
  conversions never touch the real book. Its files and numbers now use the original chapter numbers too.
**Why:**
- One entry per book matches how a listener thinks of it, and the library doesn't fill up with fragments.
- Original numbers keep a chapter's name, download name and audio file the same no matter which chapters were
  converted first.
- Per-chapter voice keeps the choice with the user: re-converting the whole book in one voice is one click
  ("all").
**Consequences:**
- Old `-ch` test folders get their numbers from the stored spec, so the user's `…-ch4` Kokology book now reads
  "Ch 04". If an empty chapter inside the spec was skipped, the spec and the folder don't line up, and the position
  is used. Checked read-only against the 3 real library books: `-ch1` → 1, `-ch4` → 4, the full book → 1–38.
- A Sigil edit that adds or removes chapters shifts the numbers. Chapters converted earlier keep their old number and
  audio. Only the `text_sha1` check flags them (as not converted), and they are not removed. Delete the book and
  convert again to start clean.
- No way yet to delete one chapter from a book.
- The default ticks after an interrupted run are covered by the API data (`last_chapters`) but were not clicked in a
  browser.

## D-037 Pairing a phone: a token in the QR code, and a choice of the PC's addresses
Status: Accepted · Milestone: M3 (wrap-up before M4)
**Context:**
- M4's Android app will be the second client of `/api/v1`. Until now anyone who could reach the port could list,
  download and delete books.
- The user's router has AP isolation, so the phone reaches the PC over **ZeroTier One**, not the local Wi-Fi.
  The old `lan_ip()` picked the default-route address (the Wi-Fi, 192.168.24.154), and the QR code pointed there.
- A PC can have several adapters: Wi-Fi, ZeroTier, other VPNs, Wi-Fi Direct.
**Decision:**
- **Token.** `server/auth.py` makes `<data>/server-token` (`secrets.token_urlsafe(24)`) at first start and reuses
  it. `ebook-server --new-token` replaces it, which unpairs every phone. The file is gitignored.
- A router-level dependency on `/api/v1` lets a request through in two cases:
  - it comes from the PC's own page: a loopback client (or TestClient's `testclient`) **whose `Host` is
    `localhost`, `127.0.0.1` or `[::1]` and whose `Origin`, if sent, is one of those too**. The client address
    alone isn't enough: a web page open in the PC's browser can send cross-site requests to localhost (a foreign
    `Origin`), or point its own domain at 127.0.0.1 by DNS rebinding and read `/info`'s token (a foreign `Host`);
  - it carries the token as `Authorization: Bearer <token>` or `?token=<token>`.
  The query form is for URLs the browser loads by itself (`<audio src>`, `<img>`, download links), which can't
  send headers. Anything else gets 401 "Pair this device: scan the QR code shown on the PC". The comparison uses
  `secrets.compare_digest`.
- `/`, `/static/*`, `/docs` and `/openapi.json` stay open: they are the page and the contract, with no data.
  `/info` is protected because its QR codes hold the token.
- **QR code** = `http://<address>:<port>/#token=<token>`. The page reads the token from the hash, keeps it in
  `localStorage`, removes it from the address bar (`history.replaceState`), then sends the header on every `fetch`
  and adds `?token=` to src/href URLs. The Android app reads the same QR code.
- **Addresses.** `server/network.py` lists the PC's IPv4 addresses with their adapter names (`ifaddr`), skipping
  loopback and link-local. The default stays the local (default-route) address, as before, unless
  `ebook-server --advertise <address>` or `EBOOK_AUDIO_ADVERTISE` names another. `/info.urls` lists every address,
  each with its own `pair_url` and QR SVG.
- **Home page.** Every address is a button under "Other addresses"; a click switches the QR code and the address
  text, without a request or a server restart. A field takes a typed address (host name, IPv4 or `[IPv6]`, optional
  `:port`); **Show QR** calls `GET /api/v1/qr?address=` for its QR code, and a bad value shows the 400 message under
  the field. The choice is remembered per browser by its full URL (a typed address can share its host with a
  listed one and differ only in the port).
- mDNS now registers every IPv4 address, not only the default one.
**Why:**
- A token in the QR code costs the user nothing: scanning it is the pairing step the phone needs anyway.
- Loopback needs no token: the PC's own browser is the owner, and the token file is readable on the PC anyway.
- ZeroTier gets no automatic preference (the user's choice): adapter names vary, and the default-route address is
  right for most setups. One click picks another address; the typed field covers addresses the PC doesn't list
  (a port forward, a DNS name).
**Consequences:**
- After this change, a phone or a bookmark without the token gets 401 until it scans the new QR code once.
- **Known limits:**
  - The server speaks plain HTTP. ZeroTier encrypts its traffic, but on a plain Wi-Fi network the token can be
    sniffed. The token guards against other devices on the network, not against someone watching it.
  - Every program on the PC itself is trusted (loopback with a local `Host`); web pages in its browser are not
    (`Host`/`Origin` check, AUTH-05).
  - Opening the page on the PC by one of its network addresses (not `localhost`) counts as another device: it
    needs the token like a phone.
  - `?token=` URLs appear in the server's access log if one is turned on (it is off: `log_level="warning"`).
  - `GET /qr` doesn't check that the phone can reach the typed address.

## D-038 Cancel a conversion, chapter versions, no delete while converting
Status: Accepted · Milestone: M3 (wrap-up before M4)
**Context:**
- A conversion could only be stopped by stopping the server.
- Since D-035 a re-converted chapter keeps its `chNNN.m4a` name. An offline copy on the phone (M4) can't tell from
  the name that it is stale.
- Deleting a book while its conversion ran was undefined (SRV-16): the worker could recreate the folder or fail.
**Decision:**
- **Cancel.** `build_book(..., cancel=threading.Event)` checks the event before each chapter and after each
  sentence, and raises `build.Cancelled`. The checks sit between sentences, so ffmpeg is never cut off and no
  `.tmp.m4a` is left.
  - `Jobs.cancel(job_id)`: a **queued** job becomes `cancelled` at once, and the worker skips it when it comes off
    the queue (both under the jobs lock). A **running** job gets its event set; the worker catches `Cancelled` and
    sets `cancelled`. An ended job → `Conflict` (409).
  - The draft goes back to review with "Cancelled: approve again to resume (finished chapters and sentences are
    kept)". Finished chapters stay in `book.json` (D-035) and the sentence cache stays, so approving again resumes.
    The server and the loaded model keep running.
  - Routes: `POST /jobs/{id}/cancel` and `POST /drafts/{id}/cancel` (the draft's own job; simpler for the phone),
    both returning the `Job`. `JobStatus` gains `cancelled`.
  - The page has a **Cancel** button on the draft card and on the job card while queued or running, with a
    confirmation.
- **Chapter versions.** Each chapter in `book.json` gets `size_bytes` and `updated_ms` (the `.m4a`'s mtime in epoch
  milliseconds), and `read_book()` fills both from the file for older books. The phone compares them with its copy.
- **Delete while converting.** `delete_book()` raises `Conflict` ("cancel the conversion first") while the book is
  in `jobs.busy_books()`. `DELETE /books/{id}` documents 409.
- **"Converted N of M".** `GET /drafts` items now carry `converted` too (moved from `DraftDetail` to `Draft`). The
  draft card shows "converted 1 of 2" when some chapters are in the library. `Drafts.library_state()` computes it,
  cached per draft by the cleaned file's and `book.json`'s mtimes, because the page asks every 2 s.
**Why:**
- A cancel checked between sentences stops within one sentence (about 0.5 s live) and needs no process killing.
- Milliseconds, not seconds: two runs in the same second (tests, a quick re-convert of a short chapter) would look
  the same. Size and time together are cheap and need no hashing of the audio.
**Consequences:**
- A cancel that comes while the model loads or while the last chapter is being encoded takes effect only after that
  step (a few seconds).
- Cancelled jobs, like done ones, stay in `GET /jobs` until the server restarts (jobs live in memory).
- Checked live (real Kokoro, scratch data folder): cancel in chapter 2 → stopped in 0.5 s, chapter 1 kept, no
  leftovers, a second cancel → 409, the server kept serving; approving again finished the book. Delete while
  converting → 409.

## D-039 Web reader: sentence buttons and text size, same rules as the phone
Status: Accepted · Milestone: M5
**Context:** M5 added a read-along view to the Android app (android A-015). The user asked for the web reader to get
the same text size control and previous/next sentence buttons (not the sleep timer).
**Decision:**
- The player bar has **‹ Sentence**, **Sentence ›**, **A−** and **A+**.
- ‹ Sentence restarts the current sentence when more than 1.5 s (`RESTART_MS`) into it, else goes to the one before.
  Sentence › does nothing on the last sentence. Both start playback when paused. The same `sentenceAt` binary search
  as the highlight (D-012) is used.
- Text size 12–32 px in steps of 2, default 18 (`TEXT_SIZE`), set as the `--text-size` CSS variable on `#text` and
  remembered in `localStorage` (a private window just doesn't remember it).
**Why:** The phone and the PC readers behave alike. The numbers are written in both places; AND-11
(`tests/test_android_contract.py`) fails if they drift apart.
**Consequences:** No server change. The size is per browser, not per book or user.

## D-040 Web page in English, Simplified and Traditional Chinese
Status: Accepted · Milestone: M6a
**Context:** The user asked for Simplified and Traditional Chinese support. For now that means the interface; Chinese
voices come later (the language check, D-018, still accepts English books only). The Android app gets the same three
languages (android A-017).
**Decision:**
- The page's text lives in `desktop/web/i18n/en.json`, `zh-Hans.json` and `zh-Hant.json`: flat `key → text` maps with
  `{name}` placeholders. `index.html` marks static text with `data-i18n` (and `data-i18n-html`, `-title`,
  `-placeholder`, `-aria`); `app.js` builds its dynamic text with `t(key, vars)`. Keys are written as literals, so a
  test can find every one.
- The language is a saved choice (`localStorage` `ebookAudioLang`), else the browser's `navigator.languages`:
  zh-TW / zh-HK / zh-MO / zh-Hant → Traditional, any other `zh` → Simplified, else English. A language dropdown at the
  top (English / 简体中文 / 繁體中文, each in its own script; three buttons until after M7, changed at the user's request)
  saves the choice and reloads the page, which redraws every list in the new language.
- The page loads English plus the chosen language before its first render. A missing key falls back to English,
  then to the key itself.
- The files are served by the existing `/static` mount (open to every device, like `app.js`); they are package data
  in `pyproject.toml`. No server change.
- Traditional Chinese uses Taiwan wording (檔案, 設定, 網路, 伺服器, 權杖). The Android strings use the same words for
  shared labels, such as "Other addresses" → 其他地址 / 其他位址, which the app's pairing messages refer to.
**Why:** No build step and no library (the page is plain files, D-032). JSON files can be checked by pytest.
Reloading on a switch is simpler and safer than re-rendering every list by hand.
**Consequences:**
- Text that comes from the server stays English: error `detail`s, draft and job `message`s, the cleaning report's
  checks, method and removed-item reasons. Translating those means message codes in the API (a later change).
- `tests/test_web_i18n.py` fails when a language misses a key, a placeholder differs, the page or script uses an
  unknown key, or a key is unused.
- A switch reloads the page: an open review or reader is left (the tab in the URL hash stays).

## D-041 README in three languages; MIT license
Status: Accepted · Milestone: M6a
**Context:** The user asked for a formal, professional README, in Simplified and Traditional Chinese as well, and for
the project to present itself as working on any Android phone, not only Xiaomi HyperOS. CLAUDE.md says everything
in the repository is written in English.
**Decision:**
- `README.md` (English) is the source. `README.zh-CN.md` and `README.zh-TW.md` are full translations with the same
  sections and a language switcher at the top of each. Translations are the deliberate exception to the English
  rule: these READMEs and the UI text files (`android/.../res/values-b+zh+*/strings.xml`,
  `desktop/web/i18n/zh-*.json`, D-040, android A-017), all meant to be read in that language. Code, comments,
  component docs, commits and PRs stay English.
- The README states Android 8.0+ on any vendor. Vendor-specific install and background-playback steps are tables
  (Xiaomi, Huawei/Honor, Samsung, OPPO/OnePlus/realme, vivo/iQOO, stock Android), matching the app's Settings screen
  (android A-018).
- The code is MIT-licensed (`LICENSE`, the user's choice). The README notes that some dependencies are AGPL-3.0
  (PyMuPDF, EbookLib) and that Kokoro-82M is Apache-2.0.
**Why:** Chinese-speaking users can read the setup in their language. The license makes reuse terms clear.
**Consequences:** CLAUDE.md's Language rule names this exception. A README change must be made in all three files in the same PR. The vendor steps are written from
the vendors' documented settings; only Xiaomi HyperOS was tried on a real phone.

## D-042 Chinese books: language detection, cleaning rules, sentences
Status: Accepted · Milestone: M7 (Chinese voices)
**Context:** The roadmap's next item is converting Chinese books, Simplified and Traditional. D-018 refused everything
that is not English. The user asked whether Chinese books should get a cleaner of their own. Two real samples
(a Simplified `zh` and a Traditional `zh-TW` EPUB) showed what the English cleaner got wrong: 版权信息 and 参考文献
were kept as chapters, and so were the title page and colophon (titled with the book's name). The part titles
上篇 and 下篇 swallowed 第一章 and 第四章, because each part title shares its file with its first chapter.
**Decision:**
- **One cleaner, not two.** Almost all of `normalize.py` doesn't depend on the language: it confirms TOC entries against
  headings and uses TOC nesting and h-tag levels. Only word lists and patterns are English-specific. The Chinese titles
  don't overlap with the English ones, so they are simply added to the same sets. No per-language switch is needed.
  - Front matter (D-016): 封面 扉页 书名页 版权 版权信息 版权页 目录 题献 献词, and the Traditional forms.
  - Back matter: 参考文献 参考书目 索引 注释 尾注 附注, and the Traditional forms.
  - Chapter labels (`_LABEL`): 第一章 / 第12节 / 第三卷… match a TOC entry without the label, like 'CHAPTER ONE'.
    The TXT chapter-line rule knows 第…章, 序, 前言, 楔子, 后记, 结语.
  - `_plausible_title` accepts a title with one Chinese character (序), instead of needing three letters.
  - Figure labels: 图 1.1 / 圖 2-3 lines.
- Two general rules, which English books get too:
  - **Chapters under a part title:** when one child of a TOC entry opens its own file, all its siblings are
    chapters, including the first one that shares the part's file. A part title with no text of its own is then read
    with that chapter, as before.
  - **Title page and colophon:** a "chapter" titled with the book's own title (or the start of it, before a subtitle)
    and shorter than 1500 characters is removed.
- **Detection** (`language.detect_language`): a book is Chinese when Chinese characters are ≥ 30 % of the letters
  sampled and there are ≥ 100 of them, with next to no Japanese kana. Otherwise the English check of D-018 applies.
  With too little text, a supported `dc:language` decides, else English. `check_language` returns the code
  ("en"/"zh") and refuses anything else. The report, the std EPUB's `dc:language` (a matching tag such as `zh-TW` is
  kept) and `book.json`'s `language` carry the result.
- **Text:** a line break between two Chinese characters is joined without a space (`parse.unwrap`, PDF and TXT). A TXT
  file with no blank line has one paragraph per line, and TXT files are read as GB18030 before cp1252. UTF-16 is only
  tried with a BOM.
- **Sentences** (`segment.py`): Chinese uses its own rule rather than pysbd, which cut `。”` apart. A sentence ends after
  。！？ together with the closing quotes and brackets that follow; …… doesn't end one. A piece that starts with
  closing punctuation (a cut inside 《a title！：its subtitle》) joins the one before. The length cap is 120 characters,
  split at ，；：、——.
- Both sample books cleaned as expected: 自序, 第一章 to 第八章, 结语, 后记; and 國際好評, 推薦序 ×4, 前言, 第1章 to
  第18章, 感謝名單. The English samples' reports are unchanged.
**Why:** A separate cleaner would copy about 500 lines, and every later fix would have to be made twice. Each new rule is
general, matching the "fewer cuts, general rules" approach the cleaner already follows.
**Consequences:**
- Forewords (推薦序), praise pages (國際好評) and acknowledgements (感謝名單) are kept, as in English books.
- The dedication on a Chinese title page goes with the page.
- `book_id`'s slug only keeps ASCII letters, so Chinese books are `book-<hash>`. They are still unique, but the
  folder name doesn't say which book it is.
- Japanese and other CJK-script books are refused. Chinese **scanned** PDFs are not supported: docTR reads Latin
  script only. This is a known gap (ZH-G01).

## D-043 Voices by language: two pickers, fallback, Chinese pronunciation
Status: Accepted · Milestone: M7 (Chinese voices)
**Context:** Kokoro v1.0 has 8 Mandarin voices (`zf_*`, `zm_*`) on the model the server already loads. The user wanted
two dropdowns, a Language and a Voice whose list follows it. They also wanted a voice in the wrong language for the
book to give way to that language's default. The voice is chosen at upload, before cleaning has found the language.
**Decision:**
- `kokoro.py` groups voices by language (`V10_VOICES = {"en": […14], "zh": […8]}`). A voice's first letter is its
  language (a/b → en, z → zh). `DEFAULT_VOICES = {"en": "af_heart", "zh": "zf_xiaoxiao"}`.
  `voice_for(voice, lang)` keeps a voice that speaks the book's language and otherwise returns that language's default.
- **Fallback:** `build_book` (CLI) and `Drafts.approve` (server) apply `voice_for` with the detected language. The job,
  the draft and `book.json` record the voice actually used. The draft's message says so while the job is queued.
- `GET /info` adds `languages: [{code, voices, default_voice}]` and keeps the flat `voices` and `default_voice` for
  older apps. The voice sample reads a Chinese sentence for a Chinese voice.
- **Pickers:** the web page and the app show Language ▸ Voice ▶ wherever a voice is chosen. The Review page starts on
  the book's detected language. The web page keeps the last voice picked per language and the last language in
  `localStorage`. With no saved choice, the page starts on Chinese when its interface is Chinese. The app starts on the
  interface's language.
- **Pronunciation:**
  - Traditional text is converted to Simplified for G2P only (OpenCC `t2s`). jieba's word list is Simplified, and its
    word split picks the reading of characters with several (raw 銀行 read *yín xíng*, converted *yín háng*). The text
    on screen stays as printed.
  - Latin words inside Chinese ("eBay", "Gamification") are read through an English G2P-only pipeline. misaki does
    that only for v1.1-zh. For v1.0 it passed the letters to the model as phonemes, so `kokoro._v10_zh_g2p` does the
    same split for v1.0 using misaki's own `legacy_call`. If misaki's internals change, it falls back to misaki as it is.
  - jieba's dictionary cache goes to `models/jieba/` instead of the system temp folder (D-028).
- Readers join Chinese sentences with no space. The web reader uses `book.language`. The app judges from the text
  (`SentenceSync.gap`), so books downloaded earlier show right too.
**Why:** Two dropdowns keep each list short and make the language choice explicit. The fallback means an English voice
left in the upload form can't produce a Chinese book read with English phonemes.
**Consequences:**
- The fallback note is overwritten by the conversion's progress messages. Afterwards the voice shows in the draft and
  the book, not as a message.
- Server messages stay English (D-040).
- New dependencies: `misaki[zh]` (jieba, pypinyin, cn2an) and `opencc-python-reimplemented`, in `requirements.txt` only.
  CI doesn't load the TTS.

## D-044 Optional Kokoro v1.1-zh for better Chinese voices
Status: Accepted · Milestone: M7 (Chinese voices)
**Context:** `hexgrad/Kokoro-82M-v1.1-zh` is a second Kokoro model (327 MB) with 100 Mandarin voices that sound clearly
better than v1.0's. Using it means a second model on the GPU, which D-031 avoided. The user chose to offer it as an
option that each user installs or leaves out.
**Decision:**
- `desktop/tts/models.py` lists its 100 voices (`zf_001`…`zm_100`), so the voice list needs no network. It also tells
  whether the model is installed (`config.json` and `kokoro-v1_1-zh.pth` in the Hugging Face cache under
  `models/huggingface/`). `ZhModel` downloads in a background thread and removes the model folder. Voice files
  (~0.5 MB each) download on first use, as with v1.0.
- Installed, the Chinese list shows v1.1-zh's voices instead of v1.0's 8, and the Chinese default becomes `zf_001`.
  English stays on v1.0. A voice's model follows from its name (`repo_of`). The Kokoro backend keeps one `KModel` per repo
  and loads v1.1-zh on its first Chinese sentence. Pipelines are keyed by (language, repo).
- API: `GET /models/zh` (status, and `done_bytes`: what has reached the cache so far; with Hugging Face's xet
  transfer that stays 0 until the file is complete, so the page then says "Downloading about 327 MB…"), `POST` (install), `DELETE` (remove; 409 while a queued or running
  conversion uses one of its voices, and the loaded copy is dropped). The web page has a "Better Chinese voices" box
  under "Other addresses". The phone only sees the longer voice list.
**Why:** It's the user's choice, and installing it costs nothing on PCs that never convert Chinese.
**Consequences:**
- With v1.1-zh loaded, two models share the GPU: about 330 MB more.
- While it is installed, v1.0's Chinese voices are not offered. A book read with `zf_xiaoxiao` keeps its audio, but its
  Review page offers v1.1-zh voices, with the mixed-voice warning for new chapters.
- Removing it while the app shows a v1.1-zh voice: the next approve is refused with "Unknown voice" until the
  user picks again.

## D-045 TTS behind a backend interface; a setting picks the backend
Status: Accepted · Milestone: M8 (TTS backends, voice names)
**Context:** Kokoro was called directly from `build.py` and `service.py` (`KokoroTTS`, module-level voice lists), so
another engine would have meant edits all over. The user asked for an interface with Kokoro as the first backend and a
setting to pick one, without adding other engines yet.
**Decision:**
- `tts/backend.py` defines `Backend`: `languages()`, `voices(lang)` (as `Voice` records: id, language, gender, accent,
  name, number, traits), `default_voice(lang)`, `synth(text, voice, speed) → float32 mono`, `sample_rate`, `unload()`
  and `cache_key(voice, speed, text)`, plus helpers (`voice_ids`, `voice_language`, `voice_for`). `BACKENDS` maps a
  name to a lazy constructor, so importing it loads no model. Only `kokoro` is registered.
- `tts/kokoro.py` is `KokoroBackend`. Its `cache_key` stays `voice|speed|text`, so sentences cached before this
  change still resume (checked on a real pre-change cache: 32 of 32 files match). Other backends' keys are prefixed
  with their id. Voice sample files keep their names for Kokoro and are prefixed with the backend id otherwise.
- Which backend: `--tts` (`ebook-server`, `ebook-convert`) > `EBOOK_AUDIO_TTS` > `settings.json` `"tts"` in the data
  folder (written by the page) > `kokoro`. An unknown name from the command line or the variable stops the start
  with the list of names; an unknown saved name falls back to Kokoro.
- API: `GET /settings/tts` → `{backend, backends: [{id, name}], fixed_by}`; `PUT` `{backend}` switches (400 unknown,
  409 while a conversion is queued or running, 409 when `fixed_by` is `--tts` or `EBOOK_AUDIO_TTS`). Switching frees
  the old backend's model. The page has a "Speech engine" box; the phone doesn't use these routes.
- A draft's voice that the current backend doesn't offer gives way to its default for the book's language; a book in
  a language the backend can't read is refused.
**Why:** One seam for engines, no shared mutable voice state, and an unchanged cache and sample layout.
**Consequences:**
- `SUPPORTED_LANGUAGES` stays in `core`; a backend may offer a subset.
- Tests use a fake second backend (`OtherTTS`); none ships.
- The page's subtitle still says "Kokoro TTS".

## D-046 Voice names from measured pitch and pace
Status: Accepted · Milestone: M8 (TTS backends, voice names)
**Context:** The pickers showed raw ids (`af_nicole`, `zf_047`). Kokoro publishes no description of its voices, and
v1.1-zh's 100 voices are only numbered. The user asked for names based on each voice's style, chose measured traits
over hand-written ones, and the format "translated name + id" in the interface language.
**Decision:**
- `tts/voice_traits.py` synthesizes three fixed sentences per voice and measures the median F0 of voiced frames
  (normalized autocorrelation, checked on generated tones including a weak fundamental) and the pace (syllables per
  second of speech, pauses left out). Pitch is ranked within model + language + gender, pace within model + language;
  the lowest third gets `low`/`slow`, the highest `high`/`fast`, the middle no word. The results for all 122 voices are
  committed as `voice_traits.json` (packaged), so naming a voice never runs the model. Re-measured on other sentences,
  13 voices moved a few percent, all in the same direction, and kept their words.
- `Voice.traits` carries the words; `/info` adds `languages[].voice_details` (same order as `voices`, which stays a
  list of ids).
- The clients build the label: "Nicole · American woman, deep, calm (af_nicole)", "女声 025 · 低沉，轻快（zm_025）".
  The user picked the descriptive words deep/bright and calm/lively (低沉/明亮, 舒缓/轻快) over "lower/higher". The
  v1.0 Chinese names stay in pinyin (Xiaoxiao) in every language: Kokoro doesn't publish their characters.
- The option's value stays the id, so saved choices, the CLI and the API are unchanged.
**Why:** Measured words are honest about what they describe and cover the numbered voices too.
**Consequences:**
- The words are relative: a "deep" woman's voice is deep for a woman's voice of that model.
- A new voice or model needs `python -m desktop.tts.voice_traits` (GPU, a few minutes); until then it shows without
  traits. A backend other than Kokoro brings its own traits or none.
