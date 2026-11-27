# Desktop component: test-case library

The written test cases for `desktop/`. Each case is either **Automated** (a pytest name in
`tests/test_desktop.py`) or **Manual**. Cases marked **Gap** describe behavior that is
known to be unhandled or untested, and they are candidates for new tests or fixes.

Run the automated cases with: `.venv\Scripts\python -m pytest tests/`

CI (`.github/workflows/ci.yml`) runs every automated case on each PR into `master` and each push
to `master` (Ubuntu, Python 3.10, ffmpeg, `requirements-ci.txt`). The check must pass before a PR
can merge. Cases that need the real Kokoro model (TTS-*) stay manual, because CI does not install it.

Status legend: Automated · Manual · Gap

EPUB cases run on synthetic books built at test time by `tests/epub_factory.py` (made-up text, no
binary fixtures; see D-014). Gap cases are `xfail(strict=True)`: when a gap gets fixed, the test
starts passing, pytest reports XPASS as a failure, and you remove the marker and update the row.

---

## Segmentation (`segment.py`)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| SEG-01 | Abbreviations and quotes | `split_paragraph('Mr. Smith went to Washington. "Is it far?" she asked. He said... no.')` | 3 sentences. "Mr." does not split, and the quote stays with "she asked." | Automated `test_abbreviations_and_quotes` |
| SEG-02 | Punctuation-only fragment | `split_paragraph("The end. * * *")` | Every unit contains a letter or digit, and `* * *` is attached to "The end." | Automated `test_punctuation_only_attached_not_spoken_alone` |
| SEG-03 | Long sentence split | 30 repeated clauses joined by commas | More than one part, each ≤ 350 chars. Joining the parts reproduces the original text. | Automated `test_long_sentence_split` |
| SEG-04 | Paragraph grouping | `split_text("One. Two.\n\nThree.")` | `[["One.","Two."],["Three."]]` | Automated `test_paragraphs` |
| SEG-05 | Leading punctuation-only fragment | `split_paragraph("… Then it began.")` | The leading fragment is dropped or merged, and no unit lacks letters or digits | Manual |
| SEG-06 | Long sentence with no spaces | a 600-char token with no spaces | Hard cuts at 350 chars and no empty parts | Manual |
| SEG-07 | Empty and whitespace input | `split_text("")`, `split_text("\n \n")` | `[]` | Manual |

## Parsing (`parse.py`)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| PAR-01 | TXT with chapter headings | TXT with "Chapter 1" / "Chapter 2" lines | 2 chapters titled by the heading lines, each starting with its heading text | Automated, covered by `test_build_txt_end_to_end` |
| PAR-02 | TXT without headings | ~50k chars, no headings | Chunked into "Part 1", "Part 2", … of ~20k chars each | Manual |
| PAR-03 | TXT hard-wrapped lines | Paragraphs with single newlines inside | Single newlines are joined into spaces, and blank lines separate paragraphs | Manual |
| PAR-04 | TXT encodings | Same text saved as UTF-8 with BOM, UTF-16, cp1252 | Text decodes correctly in every case, with no BOM character in the output | Manual |
| PAR-05 | EPUB with TOC | A typical commercial EPUB | Chapters follow the spine order, titles come from the TOC (nested Section TOC, hrefs under `Text/`), and the metadata title and author are read | Automated `test_par05_metadata_spine_order_and_toc_titles` |
| PAR-06 | EPUB without TOC titles | An EPUB with an empty or missing TOC | Titles fall back to the first heading, then to "Section N" | Automated `test_par06_title_fallbacks_without_toc` |
| PAR-07 | EPUB footnote markers | Text containing `<sup><a>1</a></sup>` | The marker digits are not in the chapter text (linked and bare-digit `<sup>`) | Automated `test_par07_footnote_markers_removed` |
| PAR-08 | EPUB cover | An EPUB with a cover item / an image named "cover" | `cover` bytes are set, with the correct extension | Automated `test_par08_cover_from_cover_item`, `test_par08_cover_from_image_named_cover` |
| PAR-09 | PDF with outline | A PDF with a level-1 outline of 2 or more entries | One chapter per outline entry, plus "Front matter" if the first entry is not on page 1 | Manual |
| PAR-10 | PDF without outline | A 40-page PDF with no outline | Chapters "Pages 1–15", "Pages 16–30", "Pages 31–40" | Manual |
| PAR-11 | PDF cleanup | A PDF with hyphenated line breaks and bare page numbers | Words are de-hyphenated and page numbers removed | Manual |
| PAR-12 | Unsupported type | `load_book("x.docx")` | `ValueError: Unsupported file type` | Manual |
| PAR-13 | No readable text | A scanned image-only PDF / an EPUB with no text | `ValueError: No readable text found` | EPUB: Automated `test_par13_epub_without_text_raises`; PDF: Manual |
| PAR-14 | Short chapters dropped | A chapter with fewer than 40 chars | The chapter is removed | Automated `test_par14_short_pages_dropped` |
| PAR-15 | EPUB front matter skipped | An EPUB whose cover, title page, half title, copyright page or contents is (a) labelled with `epub:type` / `role` on a page-level element, (b) listed in the OPF `<guide>`, or (c) whose TOC entries are all titled exactly "Copyright", "Contents", "Table of Contents", "Title Page" or "Half Title" | Those pages are not chapters. A half title holding a blurb is skipped too. The `samples/` book goes from 20 chapters (2,706 sentences) to 16 (2,654), starting at "1 Mole finds Toad…" (D-016) | Automated `test_par15_front_matter_not_spoken`, `test_par15_front_matter_from_opf_guide` |
| PAR-17 | Front-matter detection doesn't over-skip | A preface labelled `preface`, a chapter with `epub:type="pagebreak"` spans, chapters titled "Copyright Law" / "Contents of the Heart", a book with no labels, and single-file books where front matter shares the file with chapter 1 (labelled section; first TOC anchor "Title Page"; guide entry on the file while the TOC points to `#c1`) | All real chapters are kept with their real titles. Only labelled sections are removed from a mixed file. Title matching is exact, and books without labels parse exactly as before | Automated `test_par15_preface_and_pagebreak_chapters_kept`, `test_par15_front_matter_from_opf_guide`, `test_par15_unlabelled_book_unchanged`, `test_par17_single_file_book_keeps_chapters[labelled/toc-title/guide]` |
| PAR-18 | Unlabelled front matter with another title | A copyright page titled e.g. "Legal Notice" with no labels and no guide entry, an unlabelled title page sharing a file with chapter 1, or a page whose only title is its heading "Contents" (no TOC entry) | **Gap (accepted):** read aloud, because guessing from content would risk skipping real text | Gap |
| PAR-16 | No XHTML parser warning | Load any XHTML-based EPUB | No `XMLParsedAsHTMLWarning`, and the extracted text is unchanged (checked on the `samples/` book: identical output for all chapters) (D-015) | Automated `test_par16_no_xml_parser_warning` |

## Cleaner (`normalize.py`)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| NORM-01 | Calibre-shaped book | Synthetic book (`calibre_spec`): size-split files, page anchors away from headings, contents page with shared anchors, heading opening a paragraph, heading split over two paragraphs, footnote junk and a missing chapter in the navigation TOC, short part heading, subsection, unlabelled front matter, bibliography | Chapters exactly Preface, 1, 2, 3. The heading gets its own line, the subsection stays inside its chapter, and the part heading is read with chapter 2. Front matter, contents and bibliography are removed and junk entries ignored, all listed in the report | Automated `test_norm01_calibre_book_cut_at_confirmed_headings`, `test_norm01_removed_and_ignored_are_reported` |
| NORM-02 | Well-formed book unchanged | `novel_spec` (labelled front matter, one file per chapter); `samples/` Counselling for Toads | Identical chapters and text before and after cleaning | Automated `test_norm02_well_formed_book_unchanged`; Counselling Manual (checked: 16 chapters, identical) |
| NORM-03 | Round trip and idempotent | Clean, read back, clean the `.std.epub` again | Read-back equals the report. A second run changes nothing. Title and author kept | Automated `test_norm03_round_trip_and_idempotent` |
| NORM-04 | Stable book id | Clean the same book twice | Original and both `.std.epub` give the same `book_id` | Automated `test_norm04_book_id_stable_across_runs` |
| NORM-05 | Fallback | Book with no confirmable TOC | One chapter per file, same as the parser, and the report says fallback | Automated `test_norm05_no_confirmed_toc_falls_back_to_files` |
| NORM-06 | TXT / PDF repackaged | A TXT; `samples/` Kokology PDF | `.std.epub` with the parsed chapters. PDF front-matter titles (Copyright, Contents) are removed and reported | TXT Automated `test_norm06_txt_repackaged`; PDF Manual (checked) |
| NORM-07 | Language refused before review | Hungarian TXT | `ValueError` and no `.std.epub` written. `ignore_language=True` writes it | Automated `test_norm07_language_refused_before_review` |
| NORM-08 | CLI requires a cleaned file | `desktop.build raw.epub --chapters 1`; `--list-chapters` on the raw file and on the `.std.epub` | Refused with the normalize command. Listing works on both | Automated `test_norm08_cli_build_refuses_uncleaned_book` |
| NORM-09 | Real Calibre book | `samples/` How to Take Smart Notes | Preface, Introduction, 1 to 14, Afterword, Appendix, with no bibliography or fake index. `--chapters 6` converts "4 A Few Things to Keep in Mind" (47 sentences, timestamps line up) | Manual (checked) |
| NORM-10 | Web UI cleans automatically | Upload a Calibre-shaped EPUB in the web UI | The job shows "Cleaning the book", then converts the cleaned chapters | Manual |
| NORM-11 | Footnotes read aloud | Book with footnote paragraphs inside chapters | **Gap:** footnote texts ("15 Ryfe and Kemmelmeier…") are read in the middle of chapters | Gap |
| NORM-13 | Sparse TOC | 4 chapter files with `<h1>`, TOC lists only chapter 1; TOC lists only part titles | Every file that opens with an h-tag stays its own chapter (same as the parser) | Automated `test_norm13_sparse_toc_keeps_untitled_chapter_files`, `test_norm13_toc_with_only_parts_keeps_chapters` |
| NORM-14 | Repeated titles | Two "Interlude" chapters in different files | Both kept as separate chapters | Automated `test_norm14_repeated_titles_are_separate_chapters` |
| NORM-15 | Endnotes with backlinks | Notes file with 6 notes each opening with `<a href="ch1.xhtml#rN">N</a>` | Kept as a chapter, not removed as a contents page | Automated `test_norm15_endnotes_with_backlinks_are_kept` |
| NORM-16 | Cleaned file not overwritten | `normalize x.std.epub` with no `--out` | Report printed, file byte-identical, nothing written | Automated `test_norm16_std_epub_never_rewritten_in_place` |
| NORM-17 | Edit in Sigil keeps the id | Open a `.std.epub` in Sigil, edit, save, list chapters | **Gap:** not verified that Sigil keeps the `ebook-audio:*` meta; if it drops them the CLI refuses the file | Manual (not yet run) |
| NORM-12 | Prologue missing from the TOC | Real chapter before the first TOC entry | **Gap (accepted):** removed as front matter, but shown in the report for review | Gap |

## Language check (`language.py`)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| LANG-01 | English accepted | English prose; the `samples/` books Counselling (0.44), Smart Notes (0.40), Kokology PDF with noisy OCR (0.32) | Accepted | Automated `test_lang01_english_accepted`; real books Manual |
| LANG-02 | Non-English refused | Hungarian and German prose written for the test; the Hungarian Kokology EPUB in `samples/` (0.00) | `ValueError` "doesn't look like English", naming the metadata language and the supported voices | Automated `test_lang02_non_english_refused`, `test_lang02_message_mentions_metadata_and_voices` |
| LANG-03 | Too short to judge | Fewer than 100 sampled words | Accepted | Automated `test_lang03_too_short_to_judge_is_accepted` |
| LANG-04 | Wrong metadata | EPUB with `dc:language` = `hu` but English text | Accepted: the text decides, metadata is only a hint | Automated `test_lang04_text_wins_over_wrong_metadata` |
| LANG-05 | Refused before work starts | `build_book` on a Hungarian TXT | Raises before TTS runs, and no library folder is created | Automated `test_lang05_build_refuses_before_tts` |
| LANG-06 | Refusal in CLI and web UI | `python -m desktop.build <hungarian book>`; upload it in the web UI | CLI prints `error: …` and exits 1. The web UI job shows status error with the same message | CLI Manual (checked); web UI Manual |
| LANG-07 | Override a wrong refusal | `build_book(..., ignore_language=True)` / CLI `--ignore-language` on a refused book | No language check, and the book converts. The refusal message suggests the flag | Automated `test_lang07_ignore_language_overrides` (CLI flag Manual) |

## TTS (`tts.py`)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| TTS-01 | Basic synthesis | `KokoroTTS().synth("Hello world.")` | Non-empty float32 mono array, plausible length (~1 s) | Manual (requires the model and GPU) |
| TTS-02 | Device selection | Run with and without CUDA available | `device` is `cuda` or `cpu` accordingly | Manual |
| TTS-03 | British voice | `KokoroTTS("bf_emma")` | The pipeline uses `lang_code="b"` | Manual |
| TTS-04 | Empty result | Text that yields no audio | A zero-length array, with no exception | Manual |

## Build pipeline (`build.py`)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| BLD-01 | Timestamps cover audio exactly | `assemble_chapter` with FakeTTS (10 ms per char) | First `start_ms`=300. Each `end_ms` equals the next `start_ms`, the last equals the total, and the gaps are 250/600 ms. `p` indexes are correct. | Automated `test_timestamps_cover_audio_exactly` |
| BLD-02 | End-to-end TXT build | `build_book` on a 2-chapter TXT with FakeTTS | `complete=true`, 2 chapters, m4a files non-empty, last `end_ms` equals `duration_ms` | Automated `test_build_txt_end_to_end` (requires ffmpeg) |
| BLD-03 | Book ID stability | Build the same file twice | Same `book_id`, and the same folder is reused | Manual |
| BLD-04 | Resume from cache | Kill the build mid-book and rerun | The rerun skips already cached sentences (faster) and finishes with `complete=true` | Manual |
| BLD-05 | Cache cleared on completion | After a successful build | `cache/<book_id>/` no longer exists | Manual |
| BLD-06 | Partial book playable | Inspect `book.json` during the build | Valid JSON with `complete=false` and finished chapters only | Manual |
| BLD-07 | ffmpeg missing | Remove ffmpeg from PATH | `RuntimeError: ffmpeg not found on PATH` | Manual |
| BLD-08 | Clipping guard | Synth returns a peak > 1.0 | The audio is normalized before encoding, with no clipping | Manual |
| BLD-09 | Cover written | Source with a cover | `cover.<ext>` exists and `manifest.cover` names it | Automated `test_bld09_epub_build_writes_cover_and_toc_titles` |
| BLD-10 | CLI | `python -m desktop.build book.epub --voice am_adam --speed 1.1` | Progress line updates, prints "Wrote … in Ns", and the manifest records the voice and speed | Manual |
| BLD-12 | Convert selected chapters | `--chapters 2` on a 3-chapter book after a full build; also the specs `3`, `2-4`, `1,3,5-5`, and the bad specs `0`, `6`, `4-2`, `x` | Output goes to `<book_id>-ch2/` with only "Chapter 2", `complete=true`, `chapter_selection="2"`. The full book folder is untouched. Bad specs raise `ValueError` before TTS loads | Automated `test_bld12_parse_chapter_spec`, `test_bld12_build_selected_chapters_into_separate_folder` |
| BLD-13 | List chapters | `python -m desktop.build book.epub --list-chapters` | Numbered chapters with sentence counts, the same numbers `--chapters` uses. No TTS is loaded | Manual |
| BLD-11 | Re-convert with fewer chapters | Rebuild the same file after the parser drops a chapter | **Gap:** stale `chNNN.m4a` files from the previous run remain in the folder (unreferenced) | Gap |

## Server API (`server.py`)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| SRV-01 | Info | `GET /api/info` | Name, LAN URL with the port, QR SVG (or null), voices, default voice | Manual |
| SRV-02 | List books | `GET /api/books` with 2 books, one corrupted `book.json` | 2 valid entries sorted newest first, and the corrupted book is skipped | Manual |
| SRV-03 | Get book | `GET /api/books/{id}` | The full manifest | Manual |
| SRV-04 | Invalid book id | `GET /api/books/..%2Fetc` and `/api/books/Nope!` | 404 | Manual |
| SRV-05 | File path traversal | `GET /api/books/{id}/files/..\book.json`, `/.hidden` | 404 | Manual |
| SRV-06 | Range requests | `GET …/files/ch000.m4a` with `Range: bytes=1000-` | 206 Partial Content | Manual |
| SRV-07 | Delete book | `DELETE /api/books/{id}` | `{ok:true}`, folder removed, then 404 afterwards | Manual |
| SRV-08 | Convert validation | Unknown voice, speed 0.4 or 2.1, `.docx` upload | 400 with a clear message in each case | Manual |
| SRV-09 | Convert happy path | Upload a small TXT | `{job_id}`, then the job goes queued, running, done, and the book appears in `/api/books` | Manual |
| SRV-10 | Job error reporting | Upload a TXT with no readable text | Job `status=error` with the error message, and the worker keeps running for later jobs | Manual |
| SRV-11 | Sequential jobs | Submit 2 conversions at once | The second stays `queued` until the first finishes | Manual |
| SRV-12 | Model reuse | Two jobs with `af_*` then `am_*` voices | The model loads once, and the second job uses its own voice | Manual |
| SRV-13 | Upload file name sanitizing | Upload `../../evil name.txt` | Saved as `uploads/<rand>_evil_name.txt` | Manual |
| SRV-14 | mDNS | Start the server and browse `_ebookaudio._tcp` from another device | The service is visible with the correct IP and port. If multicast is blocked, the server still runs and prints a hint | Manual |
| SRV-15 | Restart loses jobs | Restart the server during a conversion | **Gap:** the job disappears. Re-uploading resumes from the cache | Gap |
| SRV-16 | Delete during conversion | `DELETE` a book that is still converting | **Gap:** undefined. The build may recreate the folder or fail | Gap |
| SRV-17 | `.md` upload | Upload a `.md` file | **Gap:** rejected by `/api/convert` although `parse.py` supports `.md` | Gap |
| SRV-18 | Uploads cleanup | After many conversions | **Gap:** `uploads/` is never cleaned | Gap |

## Web UI (`static/index.html`)

| ID | Case | Steps | Expected | Status |
|---|---|---|---|---|
| UI-01 | Home loads | Open `http://localhost:8000` | LAN URL, QR code, voice list (default selected), and library are shown | Manual |
| UI-02 | Convert progress | Submit a book | The job card shows a progress bar with done/total sentences, and the library refreshes when the job changes | Manual |
| UI-03 | Partial book label | During a conversion | The library card shows "converting…" | Manual |
| UI-04 | Highlight follows audio | Play a chapter | Exactly one sentence is highlighted, matching the speech, and it stays highlighted through the pause after it | Manual |
| UI-05 | Tap to seek | Click a sentence | Playback jumps to that sentence's start and plays | Manual |
| UI-06 | Auto-scroll pause | Scroll manually during playback | Auto-scroll pauses for about 4 s, then resumes centering the highlighted sentence | Manual |
| UI-07 | Chapter switch | Click another chapter | The new text and audio load, and the chapter list highlight moves | Manual |
| UI-08 | Auto-advance | Let a chapter end | The next chapter loads and plays | Manual |
| UI-09 | Playback rate | Change speed to 1.5 | The audio rate changes and the highlight stays in sync | Manual |
| UI-10 | HTML escaping | A book whose title or text contains `<b>&` | Rendered literally, with no markup injected | Manual |
| UI-11 | Phone browser | Open the LAN URL on a phone | Layout fits the screen, playback and highlight work | Manual |
| UI-12 | Dark mode | OS set to dark | Dark palette, and the highlight is still readable | Manual |
