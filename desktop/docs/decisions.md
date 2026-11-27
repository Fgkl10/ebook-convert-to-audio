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
file. The web UI runs normalize, then build, automatically with no review. Scanned PDFs are rebuilt from OCR
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
labels ("FIGURE 1.1") and the Endnotes chapter are still read aloud.
