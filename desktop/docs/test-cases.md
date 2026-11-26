# Desktop component: test-case library

The written test cases for `desktop/`. Each case is either **Automated** (a pytest name in
`tests/test_desktop.py`) or **Manual**. Cases marked **Gap** describe behavior that is
known to be unhandled or untested, and they are candidates for new tests or fixes.

Run the automated cases with: `.venv\Scripts\python -m pytest tests/`

Status legend: Automated · Manual · Gap

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
| PAR-05 | EPUB with TOC | A typical commercial EPUB | Chapters follow the spine order, titles come from the TOC, and the metadata title and author are read | Manual |
| PAR-06 | EPUB without TOC titles | An EPUB with an empty or missing TOC | Titles fall back to the first heading, then to "Section N" | Manual |
| PAR-07 | EPUB footnote markers | Text containing `<sup><a>1</a></sup>` | The marker digits are not in the chapter text | Manual |
| PAR-08 | EPUB cover | An EPUB with a cover item / an image named "cover" | `cover` bytes are set, with the correct extension | Manual |
| PAR-09 | PDF with outline | A PDF with a level-1 outline of 2 or more entries | One chapter per outline entry, plus "Front matter" if the first entry is not on page 1 | Manual |
| PAR-10 | PDF without outline | A 40-page PDF with no outline | Chapters "Pages 1–15", "Pages 16–30", "Pages 31–40" | Manual |
| PAR-11 | PDF cleanup | A PDF with hyphenated line breaks and bare page numbers | Words are de-hyphenated and page numbers removed | Manual |
| PAR-12 | Unsupported type | `load_book("x.docx")` | `ValueError: Unsupported file type` | Manual |
| PAR-13 | No readable text | A scanned image-only PDF | `ValueError: No readable text found` | Manual |
| PAR-14 | Short chapters dropped | A chapter with fewer than 40 chars | The chapter is removed | Manual |

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
| BLD-09 | Cover written | Source with a cover | `cover.<ext>` exists and `manifest.cover` names it | Manual |
| BLD-10 | CLI | `python -m desktop.build book.epub --voice am_adam --speed 1.1` | Progress line updates, prints "Wrote … in Ns", and the manifest records the voice and speed | Manual |
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
