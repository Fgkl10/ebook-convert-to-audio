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
**Consequences:** Since D-019, "one file = one chapter" holds by construction for cleaned books. The
normalizer writes exactly one XHTML file per chapter. Format-specific chapter heuristics live only in `parse.py`:
- EPUB: chapters follow the spine, with front matter skipped (D-016). Titles come from the TOC, then the first heading.
- PDF: chapters come from the level-1 outline, falling back to 15-page parts. The cover is a render of page 1.
  Scanned PDFs skip this: `normalize` rebuilds them from OCR (D-021, D-022).
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
*Update (D-032):* the page is now split into `index.html`, `app.css` and `app.js`. These are still static files with
no build step and no framework.

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

## D-015 Keep the lenient HTML parser for XHTML and silence its warning
Status: Accepted · Milestone: M3
**Context:** EPUB chapters are XHTML, and BeautifulSoup warns (`XMLParsedAsHTMLWarning`) on every chapter
when they are parsed with the lxml HTML parser (PAR-16).
**Decision:** Keep `BeautifulSoup(html, "lxml")` and ignore that one warning category, only around that call.
**Why:** Real EPUBs often contain HTML entities and markup that is not valid XML. A strict XML parse
(`features="xml"`) can silently lose text, and the HTML parse had just been checked end to end
(2,706 sentences). After the change the output was identical on the sample book.
**Consequences:** Nothing changes in behavior. Other warnings still show. Silencing is local, so no global filter hides warnings from other code.

## D-016 Skip EPUB front matter by label, OPF guide, or exact title
Status: Accepted · Milestone: M3
**Context:** The cover, title page, half title, copyright page and contents were read aloud as chapters
(PAR-15). In the sample book the half title holds a 13-sentence marketing blurb.
**Decision:** Skip a spine document if (a) a page-level element (`body`, `section`, `div`, `nav`,
`article`) has `epub:type` in {cover, titlepage, halftitlepage, copyright-page, toc} or `role` in
{doc-cover, doc-toc}, or (b) the OPF `<guide>` lists it as cover, title-page, copyright-page or toc,
or (c) every TOC title pointing into it, normalized, is exactly "copyright", "contents", "table of contents",
"title page", "half title" or "half title page". Dedication, foreword, preface and introduction are kept.
Skipping is **per page, not per file**, because one XHTML file can hold front matter and real chapters (Word/Calibre
conversions, single-file books). A labelled `section`/`div` is removed and the rest of the file is still read. A whole
file is skipped only when its `body` is labelled, when all of its TOC titles are front matter, or when the guide lists it
and no TOC entry points into the middle of it (`#fragment`). A file's chapter title is its first TOC title that isn't front matter.
Headings are not used for skipping, only for titles.
**Why:** The user's choices were labels plus title matching, with half titles skipped. Labels are what publishers use
to mark these pages, and they don't overlap with chapter labels (`chapter`, `pagebreak`). Exact-title matching catches
unlabelled books without catching chapters like "Copyright Law".
**Consequences:** Unlabelled front matter with other titles is still read, as is an unlabelled title page sharing
a file with chapter 1 (PAR-18, accepted). The first version decided per file and dropped whole single-file books.
PAR-17 tests guard against that. A book whose real
content has exactly one of those titles would lose that chapter, which is very unlikely. Applies to EPUB only. PDF and TXT
have no such labels.

## D-017 Partial conversions with --chapters go to their own folder
Status: Accepted · Milestone: M3
**Context:** Most conversions of the user's sample books are only tests. A full book took about 10 minutes of GPU time,
while one chapter takes about 20 seconds.
**Decision:** `desktop.build` takes `--chapters` (1-based, `3`, `2-4`, `1,3,5-6`) and `--list-chapters`. The selected
chapters are written to `library/<book_id>-ch<spec>/` with `chapter_selection` recorded in `book.json`.
The numbering is the one `--list-chapters` prints, after front matter is skipped.
**Why:** A separate folder means a test never overwrites or mixes with the full book, and the stale-file
problem (BLD-11) cannot hit the full book. Validation runs before the TTS model loads, so typos fail instantly.
**Consequences:** Partial books show up in the library as their own entries. Only the CLI has this option, not the web UI.
*Amended by D-035:* the web page now converts chosen chapters into the book's one entry; the CLI keeps the
separate test folder, but its audio files and `number` now use the original chapter numbers.

## D-018 Refuse books in languages the voices can't speak, judged from the text
Status: Accepted · Milestone: M3
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

## D-019 Clean every book into a standard EPUB, reviewed before CLI conversion
Status: Accepted · Milestone: M3
**Context:** Internet EPUBs (often Calibre conversions) split files by size, not chapter, and their TOCs mix
chapters with footnote fragments (How to Take Smart Notes: 14 chapters in 4 files, chapters 9 to 14 as one
1,707-sentence "chapter", a 400-character sentence and bare numbers as titles, the bibliography read aloud).
**Decision:** A separate step, `python -m desktop.normalize`, writes `<name>.std.epub` (one XHTML file per chapter)
plus `<name>.std.report.txt`. On the CLI, `desktop.build` converts only files with the `ebook-audio:normalized`
marker, recognised by metadata rather than file name, and refuses others with the command to run. `--list-chapters` works on any
file. The web UI runs normalize, then build, automatically with no review (superseded by D-029: the web UI now stops
for review too). Scanned PDFs are rebuilt from OCR
(D-021); text PDFs and TXT are still repackaged as parsed. `normalize` runs the language check first.
The `.std.epub` stores the original file's sha1, and `make_book_id` prefers it, so re-cleaning or editing the
cleaned file keeps the same `book_id` and cache. That Sigil keeps the custom `<meta>` entries when saving
is not verified yet. Running normalize on a `.std.epub` with no `--out` writes nothing, so a hand-edited
file is never overwritten.
**Why:** It was the user's design. The parser stays simple, the user gets a checkpoint before GPU time, any reader can
show the result, and Sigil can fix it. One intermediate format serves EPUB, PDF and TXT.
**Consequences:** The CLI needs two commands. The report is the only place to see what was removed, so it lists every
removed block (first 80 chars) and every ignored TOC entry. `Book.author` now joins all `dc:creator`
entries instead of keeping only the first, so the cleaned file round-trips.

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

## D-021 Scanned PDFs are read with docTR, an optional dependency, one book page at a time
Status: Accepted · Milestone: M3
**Context:** The Kokology PDF is a scan of two-page spreads with an Acrobat text layer. That layer misreads
headings ("KEY TO S\\'EET ~1El\\IORIES"), drops every big first letter ("he eyes" for "The eyes"), reads "1." as
"I." and garbles running headers. Images can't be read at all without OCR.
**Decision:** A PDF whose pages are nearly all one full-page image (≥80% of pages, image ≥85% of the page) is OCRed,
even when it has a text layer. Pages are rendered at 200 dpi. A scan wider than 1.15× its height is split at the
gutter, the widest ink-free column band in the middle 30%, not at the exact centre. docTR 1.0.1 reads each book
page on the GPU, and the model is freed before the TTS loads. docTR lives in `requirements-ocr.txt`, which pins
`torch==2.6.0+cu124` and `torchvision==0.21.0+cu124`. Without the pins pip would install the newest CPU torch.
It downgrades `huggingface_hub` 2.5 to 1.33, which transformers (≥1.31) and Kokoro accept; checked by
synthesizing with Kokoro against hub 1.33. The language check runs on the OCR text.
**Why:** The user compared three options on 3 real pages: the Acrobat layer, docTR, and EasyOCR. docTR got the headings,
numbers, drop caps, punctuation and line breaks right, at under 2 s per scan on an RTX 4060. EasyOCR turned
periods into ":" and ";" and merged paragraphs, which hurts sentence splitting and pauses. Surya 0.24 calls a
server by default, so it isn't local. The centre split cut words on page 87 ("you see t" / "rector"). The gutter split
reads them whole. Keeping OCR optional is a deliberate exception to D-013's "add new imports to both
requirements files". About 15 packages for one kind of book don't belong in every install or in CI.
**Consequences:** Reading the whole 90-page Kokology takes about 40 s. The first run downloads about 100 MB of models.
Most OCR word errors are fixed by D-023. Big first letters that docTR misses entirely ("ne day", "a ot") remain. The report lists these first, under "Check by hand", for review in Sigil.
A scan without a contents page falls back to one chapter per heading in capitals.
Big first letters ("drop caps") come back from docTR in three shapes: glued as a tall first word ("T he"), as a
line of their own beside the first line (['S'] next to ['ome', 'days']), or as a normal-height letter. They are
merged back onto their line and joined by the words the book itself uses, comparing how often each form appears:
"S ome" → "Some", "I he" → "The" (docTR reads a big T as I), "A hospital" and "I can't" stay two words because
those words are far more common on their own than glued. Measured on Kokology: every chapter and key opening
reads correctly except the 3 letters docTR did not read at all.
`is_scanned` sends a PDF to OCR when nearly every page is one full-page image, even with a real text layer. A
born-digital PDF that puts a full-page background image on every page would be OCRed too, and without docTR it
now fails with the install hint where it used to convert from its text layer (SCAN-16, a known gap).

## D-022 Quiz answers are read right after each question when the book numbers both the same
Status: Accepted · Milestone: M3
**Context:** In Kokology each quiz is followed by a "KEY TO …" section with the answers. Read in book order, the
listener hears all the questions and then all the answers. The user asked for each answer right after its
question, and otherwise for a reading experience the same as the book ("follow the book exactly as written").
Measured on all 55 chapters, about 13 quizzes ask numbered questions that the key answers with the same numbers.
Most others number the choices of a single question (like "3. I will sleep on the porch tonight." in the test fixture), and some have no numbers.
**Decision:** The rule is applied only when the quiz items and the key items are both numbered 1..n (n ≥ 2), and at least half
of the quiz items contain a "?" outside quoted speech. Then the order is: intro, Q1, the "Key to …" heading as printed,
the key's theme paragraph, A1, Q2, A2, and so on. Everything else keeps book order. The report records which rule each chapter
got and why ("multiple choice", "no numbered questions", "question and answer numbers differ").
**Why:** Choices that are quoted speech, like '"Where did I put it?"', are still choices, so the quote rule keeps them that way.
Interleaving choices with their answers would give the answer away before all the choices are read. When OCR loses an item
number, the numbers differ and the chapter falls back to book order, which is always safe.
**Consequences:** A quiz whose numbering OCR damaged keeps book order instead of interleaving, and the report shows it.
The key heading is spoken once, before the theme paragraph, as the user preferred ("before answer 1").

## D-023 OCR word errors are fixed by rules checked against a word list, not by a model
Status: Accepted · Milestone: M3
**Context:** After D-021 the cleaned Kokology still had about 55 wrong words in 25,865 (0.2%): small words glued to
the next ("ofthe" ×5, "Ifyou", "Ican't", "anuisance"), "SO" in capitals inside lowercase text, quote marks read as
"1", and about 7 compounds whose line-break hyphen the cleaner itself removed ("goodluck", "halfhour",
"up-todate"). Kokoro reads each one oddly, about once every 2–3 minutes of audio. The user asked whether to train a
small model to fix them.
**Decision:** No model. `words.py` provides a yes/no English word check from the pronunciation dictionary that
already ships with Kokoro (misaki), plus simple inflections. `scanned.py` changes a word only when the check settles it:
- A line-break hyphen is dropped when the book or the dictionary knows the joined word ("mo-mentary" → "momentary").
  It is kept when the joined form is unknown but both halves are words ("good-" + "luck" → "good-luck").
- "of", "if", "I" or "a" glued to a known word is split when the glued form is not a word ("ofthe" → "of the").
  Lowercase "i", and "I" or "a" before fewer than 3 letters ("Ioe"), are too unsure and stay.
- A short word in capitals between lowercase words ("SO", "ZOO") is lowercased when it is a lowercase word that the
  dictionary does not list in capitals; acronyms ("CD", "TV") stay. At a paragraph start it becomes "As", "How".
- A lone "1" after closing punctuation and before a capital or the end of the paragraph is dropped (a quote mark).
Each fix is counted and listed in the report's notes, so every change can be checked.
**Why:** There is no training data (one scanned book), and a model that rewrites text can change correct but unusual
words (names, "kokology") without any sign, which is worse than a typo. The errors fall into a few kinds, and each kind
has a test that is either right or leaves the word alone. The dictionary costs nothing new to install.
**Consequences:** On Kokology 94 words are fixed, and what remains is about 8 one-off misreads ("ould", "coffe") plus
the 3 missed big letters (listed under "Check by hand"), and compounds the book or OCR printed as one word
("guestroom", "halfhour"), which Kokoro still reads understandably. CI does not install Kokoro, so there the list is empty and
the dictionary fixes are off; tests pass their own small word list.

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

## D-026 Note-reference links are stripped from running text; cross-references stay
Status: Accepted · Milestone: M3 · Extends PAR-07
**Context:** With endnotes removed (D-025), reference numbers in the text point at notes nobody hears, and Kokoro reads
them as numbers ("…the scientific community. two. It was…"). The parser already dropped `<sup>` markers, but Calibre
books style the marker with a class instead: Smart Notes has 58 plain `<a><span>2</span></a>` links, some with a space
before them, some glued ("hear.9"). The same kind of link is also a real cross-reference: The Art of Game Design
writes "(Chapters 9 through 11, 24, 25, and 33)" with each number linked. Neither spacing nor the link target separates
them (Calibre points both at page markers).
**Decision:** In `clean_body`, a link is removed when its text is only a 1–3 digit number (optionally in brackets) or a
note symbol (`*`, `†`, `‡`, `§`), and all of these hold:
- it is not an external link (`http`, `mailto`) and not an index locator;
- it sits in running text, not alone on its line (a contents entry or page number);
- the text just before it (up to 60 characters in the same block) does not end in a pointer word followed only by
  numbers and connectors: "chapter(s)", "section", "part", "figure", "fig.", "table", "page", "p.", "pp.", "lens", "step",
  "rule", "tip", "appendix", "volume", "no.", "number" or "#", with ",", "and", "or", "through", "to" or a dash between.
Numbers that are plain text, not links ("SQ4R,8"), are left, since they can't be told apart from real numbers.
**Why:** A pointer word is how prose introduces a number the listener should hear. A bare number after a sentence or
word is a marker. The rule lives with the `<sup>` rule, so every EPUB path (cleaner, fallback, plain parsing) gets it.
**Consequences:** Smart Notes loses exactly its 58 marker numbers (all checked by hand), and the footnote paragraphs
inside its chapters lose their leading backlink number. The Art of Game Design and Counselling for Toads are unchanged.
The footnote paragraphs themselves are still read in the middle of chapters (NORM-11; removed by D-027). Unlinked
plain-text markers remain, and a marker right after a pointer word ("…in figure.3") would be kept.

## D-027 Footnote paragraphs inside chapters are removed
Status: Accepted · Milestone: M3 · Extends D-025, D-026
**Context:** Smart Notes (a Calibre conversion of a print layout) collects 39 footnotes at the end of each part, so they
were read between the last paragraph of one chapter and the next part heading. Each note is a paragraph that opens with a
number-only link back to its reference ("1 The research on willpower…"). Most continue over more `<p>` lines, one per
printed line, until an empty paragraph. None is labelled as a footnote in the markup.
**Decision:** In `clean_body`, before the note markers are stripped (D-026), these are removed:
- elements labelled as notes (`epub:type` footnote/endnote/rearnote/note, `role` doc-footnote/doc-endnote);
- a `<p>`, `<li>`, or a `<div>`/`<aside>` with no block children, that opens with a number-only note link and has more
  text after it, together with its continuation lines: following `<p>` siblings whose text is (≥90%) in the same
  inline style as the note's number (its small print), up to an empty paragraph, the next note, another kind of
  element or the end of the parent. If a line in another style comes first, or there is no end within
  `MAX_NOTE_LINES` (8), only the opening paragraph goes.
The cleaner's report counts the notes removed.
**Why:** A note read in the middle of the text breaks the flow and, with endnotes and markers gone, no longer belongs to
anything. The opening backlink is how EPUBs tie a note to its reference. The style test is what makes it safe: a
footnote followed directly by body text (no empty line) must not take the body text with it, and in Smart Notes body
lines are never wholly in the notes' small print (only their marker numbers are).
**Consequences:** Smart Notes loses exactly its 39 notes (1,055 words); every removed run ends right before the next part
heading. The Art of Game Design and Counselling for Toads are unchanged. A note whose continuation lines are not styled
differently from body text loses only its first paragraph, and the rest stays as a fragment (NORM-11, a known gap).

## D-028 Model caches live inside the project
Status: Accepted · Milestone: M3
**Context:** Kokoro-82M (313 MB, from Hugging Face) and the docTR OCR models (124 MB) downloaded into the user's
`~/.cache`, outside the project. Everything the project uses should stay inside its folder.
**Decision:** `desktop/__init__.py` sets `HF_HOME=<project>/models/huggingface` and `DOCTR_CACHE_DIR=<project>/models/doctr`
with `os.environ.setdefault`, before any desktop module imports Kokoro or docTR (both read the variables at import time).
`models/` is gitignored. The existing copies were moved there (the Hugging Face folder holds plain files on Windows, no
symlinks); other models in `~/.cache` were not touched.
**Why:** One folder holds the whole project, so it can be moved, backed up or deleted as a unit. The package `__init__` is
the one place every entry point (CLI, server, tests) passes through first.
**Consequences:** A fresh checkout downloads the models into `models/` on first use. A value set in the environment still
wins, so a shared cache can be used by setting `HF_HOME` / `DOCTR_CACHE_DIR`. Code that imports `kokoro` or `doctr`
without importing `desktop` first would still use `~/.cache`.

## D-029 Cleaning is its own step on the website, with review
Status: Accepted · Milestone: M3 · Supersedes the web part of D-019
**Context:** The website cleaned and converted in one go, so a badly cut book cost hours of GPU time before anyone saw
it. Only the CLI had a review checkpoint. The user wants the same on the website: clean, look at the result, approve,
and only then convert, with a way to skip the stop.
**Decision:**
- An upload becomes a *draft* in `drafts/<id>/`: the uploaded file under its own name, `book.std.epub`, `report.json`
  (the `Report` as JSON) and `draft.json` (status, progress, voice, speed, the upload's sha1, job and book ids).
  Statuses: `cleaning`, then `review`, `queued`, `converting`, `done`, or `error`.
- A clean worker with its own queue runs `normalize()` and shows the OCR page count as progress. The conversion
  worker (`Jobs`) gets only approved `.std.epub` files, so cleaning a new book never waits for a long conversion.
- The review page shows "Check by hand" first, the chapter list, each chapter's text (served one chapter at a time),
  and what was removed or ignored. From there: Approve & convert (voice, speed), download the `.std.epub`, upload an
  edited one, or discard.
- An uploaded edit is read with `load_book` and rewritten with `write_std_epub` and the draft's original sha1, so the
  markers survive an editor that drops them and the book keeps its id and sentence cache.
- "Convert right after cleaning (skip review)" (`auto`) approves as soon as cleaning succeeds. `POST /api/convert` is
  kept as that one-step shortcut and now returns `{draft_id}`.
- Drafts survive a restart: `cleaning` becomes an error, `queued`/`converting` go back to review with "approve again".
**Why:** The review checkpoint is the reason the cleaner can stay cautious ("fewer cuts"). Drafts on disk, rather than in
memory like jobs, are what make reviewing at leisure possible. Two workers keep the slow GPU conversion from blocking
quick feedback on a new book. The Sigil round-trip covers edits without building an editor in the browser.
**Consequences:** `uploads/` is no longer used; discarding a draft removes its files, but drafts are never removed
automatically. Chapters cannot be edited in the browser, and a refused language cannot be overridden on the website
(the CLI has `--ignore-language`). The drafts list is not paged. Approving a `done` draft again converts it again (for
another voice).

## D-030 OCR mode, separate Clean and Convert pages, converting an uploaded cleaned book
Status: Accepted · Milestone: M3 · Extends D-021, D-029
**Context:** OCR ran only when a PDF was detected as a scan (≥80% full-page images), so a text PDF with a garbled
text layer, or a partly scanned PDF, could not be read with OCR, and a scan could not be forced onto its text layer.
The website showed cleaning, converting and the library on one page, and a book cleaned on the CLI or fixed in Sigil
could only be converted from the CLI.
**Decision:**
- `normalize(..., ocr="auto" | "always" | "never")`, also `--ocr` on the CLI and an OCR dropdown on the Clean page
  (only enabled for a PDF). `always` reads every PDF page with OCR (`ocr_pdf` renders any page); `never` uses only
  the text layer. Ignored for EPUB and TXT. The report's method names a forced choice.
- When OCR text has no contents page and no heading in capitals, the whole text is kept as one chapter ("Full Text")
  with a "Check by hand" item, instead of being removed as "before the first chapter".
- The website has three tabs: **Clean** (upload, cleaning and review list), **Convert** (upload a cleaned
  `.std.epub`, approved books, conversion progress) and **Library**. The tab is kept in the URL hash.
- `POST /api/convert-std` accepts only an EPUB with the `ebook-audio:normalized` marker. It becomes a draft that skips
  cleaning and is approved at once, keeping the book's original hash, so its library id matches.
**Why:** Detection is right for nearly every book, so `auto` stays the default; the override is for the rare book
detection gets wrong. Keeping all text when no heading is found follows "rather too few cuts than fragments". The
marker check keeps the D-019 rule that only cleaned books are converted.
**Consequences:** `always` on a long text PDF costs OCR time (about 0.5 s a page on the GPU) and may read worse than
its text layer. A PDF that is only partly scanned still has no mixed mode: it is all OCR or all text layer.

## D-031 One TTS model for both voice languages; cached voice samples
Status: Accepted · Milestone: M3
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

## D-033 Subpackages core / ocr / tts / server / web, one-way imports, installed commands
Status: Accepted · Milestone: M3 · Move-only (no behavior change except the command names)
**Context:** `desktop/` was 13 flat modules. Book-text code, OCR, TTS and the web server sat side by side, and nothing
stopped, say, the parser from importing the server. The user wanted clear parts in the same project, with one venv
and one start command, and shorter commands than `python -m desktop.xxx`.
**Decision:**
- Files moved, with history kept (`git mv`). Old name → new name:

  | Old | New |
  |---|---|
  | `parse.py`, `segment.py`, `normalize.py`, `language.py` | `core/` (same names) |
  | `ocr.py` | `ocr/engine.py` |
  | `scanned.py`, `words.py` | `ocr/` (same names) |
  | `tts.py` | `tts/kokoro.py` |
  | `build.py` | `tts/build.py` |
  | `server.py` | `server/app.py` |
  | `service.py`, `api.py` | `server/` (same names) |
  | `static/` | `web/` (still served at `/static`) |

  Earlier entries in this log keep the old names.
- Imports go one way:
  - `core` imports nothing else;
  - `ocr` and `tts` import only `core`;
  - `server` may import all three;
  - nothing imports `server`, and `web` holds no Python.

  `tests/test_layers.py` checks every import in the source, including imports inside functions.
- Two existing imports crossed the new lines, and each was fixed without changing behavior:
  - `SUPPORTED_LANGUAGES` moved from the TTS module to `core/language.py`, its only user;
  - `normalize()` imports `desktop.ocr` inside the function, only for a PDF, instead of at the top of the module.
- Paths that depended on a module's own location (`build.ROOT`, the static folder) now start from
  `desktop.PROJECT`. Moving a file one level deeper would otherwise have moved `library/` and `cache/`.
- `pyproject.toml` installs three commands with `pip install -e .`: `ebook-server`, `ebook-normalize` and
  `ebook-convert` (the old `desktop.build`; a Python package named `build` already exists). `python -m desktop.server`
  still works.
- `pyproject.toml` lists no dependencies. The requirements files stay the source of truth, because PyTorch must come
  from its CUDA index.
**Why:**
- Each part can be read, tested and replaced on its own. The Android app (M4+) only needs `server`'s API.
- A one-way rule enforced by a test stays true. A rule written only in a doc drifts.
- Installed commands are shorter and work from any folder while the venv is active.
- **OCR as a pip extra (`pip install -e .[ocr]`) was considered and left out.** docTR needs `torchvision`; resolving
  it from PyPI would install a CPU torchvision, or replace the CUDA torch, and the TTS would lose the GPU (the reason
  for the pins in D-021).
- OCR is still optional:
  - docTR is installed only from `requirements-ocr.txt`;
  - `core` loads `desktop.ocr` only when it reads a PDF;
  - LAY-04 checks that cleaning a TXT loads no OCR, TTS or web module.
**Consequences:**
- The commands changed: `python -m desktop.normalize` / `desktop.build` became `ebook-normalize` / `ebook-convert`,
  and the CLI's own messages name the new commands. Scripts that used the old commands need the new names.
- `pip install -e .` has to be run once in each venv. It writes `ebook_audio.egg-info/`, which is gitignored.
- A new module must go into one of the packages and follow the import rule, or `test_layers` fails.

## D-034 Per-chapter download with a readable file name
Status: Accepted · Milestone: M3
**Context:** The reader only played chapters. Saving one from the browser gave `ch000.m4a`, which says nothing once
it is in a Downloads folder or on a phone. The user wanted a download button per chapter and names like
"Book Title - Ch 01 - Chapter Title.m4a", with inline playback unchanged and no zip download.
**Decision:**
- `GET /api/v1/books/{id}/files/{name}` takes an optional `?download=1`.
  - Without it, the response is the same as before, with no `Content-Disposition`.
  - With it, the file is sent as `attachment` with a readable name. Starlette writes `filename*=utf-8''…`, so
    non-ASCII titles survive.
- The name is built in `service.download_name()`, with no HTTP:
  - The parts are `<book title> - Ch <n> - <chapter title>.m4a`. `n` is the chapter's place in the manifest, the
    same numbering the reader's list shows. It is padded to two digits, or more for books with 100+ chapters.
  - A file that isn't a chapter gets `<book title> - <stem>.<ext>` (the cover).
  - Characters reserved on Windows or Android (`\ / : * ? " < > |`) and control characters become spaces, then
    whitespace collapses and trailing dots and spaces are trimmed.
  - Empty parts are dropped. The whole name is capped at 200 UTF-8 bytes (filesystems such as ext4 and f2fs limit names to 255 bytes, not
    characters), cut between whole characters and keeping the extension. If nothing is left,
    the stored name is used.
- In the reader, each chapter row has a ⬇ link (`<a download href="…?download=1">`). Its click stops propagating, so
  downloading doesn't switch or start a chapter.
- No zip or whole-book download.
**Why:**
- A query option instead of a new route keeps the v1 route list (and the Android contract) as it was. One URL serves
  both uses, and Range requests still work for resumed downloads.
- The filename lives on the server, so the web page, the phone app and `curl -OJ` all get the same name.
- Numbering by list position matches what the listener sees in the reader.
**Consequences:**
- *Superseded by D-035:* chapters are now numbered by their number in the cleaned book. Before that, a book
  converted from a chapter selection (e.g. `…-ch4`) named its first chapter "Ch 01", not its number in the
  original book.
- The saved file name has been checked with curl but not yet in a browser (UI-24).

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

## D-036 Safe to stop with Ctrl+C at any point
Status: Accepted · Milestone: M3
**Context:**
- The user stops the server with Ctrl+C, sometimes mid-conversion.
- The sentence cache (D-007) was written with `np.save(<key>.npy)` directly, so an interrupted write could leave a
  half file. A resumed conversion would then fail on `np.load`.
- ffmpeg's `chNNN.tmp.m4a` (D-006) was never removed and was counted in the library size.
- uvicorn's graceful shutdown waited for open connections. A phone downloading a chapter kept the server running:
  still alive 30 s after Ctrl+Break in a live test.
**Decision:**
- **Cache.** `CachedSynth` writes `<key>.npy.tmp` through a file handle, then `os.replace` to `<key>.npy`. It goes
  through a handle because `np.save(path)` appends `.npy` to a name that lacks it. An entry that can't be loaded (a
  cut-off file from an older version) is deleted and made again.
- **Startup.** `service.clean_leftovers()` runs in `ebook-server`'s `main()` and deletes every `*.tmp.m4a` and
  `*.npy.tmp` under `library/` and `cache/`. `list_books()` never counts them.
- **Shutdown.** `uvicorn.run(..., timeout_graceful_shutdown=1)`: after the first Ctrl+C, open requests get 1 s, then
  they are cancelled.
- **Unchanged:**
  - an interrupted conversion's draft goes back to review and resumes from the cache when approved;
  - an interrupted cleaning is marked failed (SRV-25);
  - `book.json` and `draft.json` were already written atomically (D-008).
**Why:**
- A temp-and-rename write is all-or-nothing on one filesystem, so no reader ever sees half a file.
- Cleaning at start, not at shutdown, also covers crashes and power loss, and the shutdown path stays short.
- 1 s is enough for a page load or an API call. A cut-off chapter download resumes with HTTP Range (D-032).
**Consequences:**
- The cleanup assumes one server per data folder: a second server on the same folder could delete the first one's
  in-progress files. Tests and checks use their own `EBOOK_AUDIO_DATA` (D-032).
- The CLI (`ebook-convert`) doesn't run the cleanup. A Ctrl+C there can leave a `.tmp.m4a` until the next server
  start; the next CLI run overwrites it.
- A Ctrl+C during a conversion also stops ffmpeg (same console). The worker may record "Conversion failed" just
  before the process ends. Either way the draft is back in review after a restart.
