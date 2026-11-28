# HTTP API v1

The JSON API served by `desktop/server/api.py` (D-032). It is the one description of the API: other docs link here
instead of repeating it. The live schemas are in `/openapi.json` (browsable at `/docs`) while the server runs. The
`book.json` manifest that `GET /books/{id}` returns is described in [architecture.md](architecture.md#bookjson-manifest).

## Rules

The web page and the Android app use the same API. All paths are under `/api/v1`, and the schemas are in
`/openapi.json` (browsable at `/docs`). A breaking change goes into a new `/api/v2`; v1 keeps working. Uploads are
multipart, every other body is JSON, and every error is `{"detail": "..."}` with 400 (invalid input), 404 (unknown
id), 409 (wrong state) or 422 (a field of the wrong type, where `detail` is FastAPI's list). `test_api01` pins the exact
route list. `tests/test_android_contract.py` pins the shape of `/info`, `/books` and `/books/{id}` that the Android
app decodes (android/docs A-010, AND-01): a field change there means updating the app's models and its fixtures.

## Pairing (D-037)

Every route needs pairing (D-037). From the PC's own page (loopback, with a local `Host` and `Origin`), nothing is
needed. From any other device, the
request must carry the token from the QR code, as `Authorization: Bearer <token>` or as `?token=<token>` (for
`<audio src>`, `<img>` and download links). Without it the answer is 401
`{"detail": "Pair this device: scan the QR code shown on the PC"}`.

Not under `/api/v1`, and open to every device: `GET /` (the web page), `/static/*` (its files), `/docs` and
`/openapi.json`.

## Routes

| Method & path | Purpose |
|---|---|
| `GET /info` | `{api_version: 1, name, url, qr_svg, urls, voices, default_voice, languages, ocr_modes}`. `urls` lists every address of the PC, the default first, each as `{address, adapter, url, pair_url, qr_svg}` with `pair_url` = `<url>/#token=<token>`. `url` and `qr_svg` are the first entry's. `languages` is `[{code: "en"\|"zh", voices, default_voice}]` (D-043); `voices` is all of them in one list and `default_voice` the English default, for apps before that |
| `GET /models/zh` | The optional Kokoro v1.1-zh model (D-044): `{id, installed, installing, done_bytes, total_bytes, error}`. While it is installed, the `zh` voices in `/info` are its 100 voices |
| `POST /models/zh` | Start downloading it (~327 MB, in the background) → the status; nothing happens when it is installed or installing |
| `DELETE /models/zh` | Remove it → the status. 409 while it is downloading or while a queued or running conversion uses one of its voices |
| `GET /qr?address=` | An `Address` (adapter `"typed"`) for an address typed by hand: a host name, IPv4 or `[IPv6]`, with an optional `:port` (otherwise the server's port). 400 for anything else: a scheme, a path, spaces, or a port outside 1–65535 |
| `GET /voices/{voice}/sample` | ~5 s m4a of the voice reading a fixed sentence, English or Chinese by the voice's language (made once, then cached); 404 for a voice not offered now |
| `POST /drafts` | Upload and clean. Multipart `file`, `voice`, `speed` (0.5–2.0), `auto`, `ocr` (`auto`/`always`/`never`, PDF only) → `{draft_id}`. Waits for review, or converts at once with `auto=true` (replaces the old `/api/clean` and `/api/convert`) |
| `POST /drafts/cleaned` | Multipart `file` (a cleaned `.std.epub`), `voice`, `speed` → `{draft_id, job_id}`. No cleaning; converted at once. 400 for anything without the `ebook-audio:normalized` marker |
| `GET /drafts` | All drafts (`Draft`: status, message, OCR progress, chapters, checks, job and book ids, `converted`) |
| `GET /drafts/{id}` | One draft plus its `report` (null until cleaned; `report.language` is `en` or `zh`, D-042), `converted` (1-based chapters already in the library book with this text) and the library book's `book_voice`/`book_speed` (null before the first conversion) |
| `GET /drafts/{id}/chapters/{n}` | `{index, title, paragraphs}` of one cleaned chapter; 409 before cleaning |
| `GET /drafts/{id}/std.epub` | Download the cleaned book (for Sigil); 409 before cleaning |
| `PUT /drafts/{id}/std.epub` | Replace it with an edited `.std.epub` (multipart `file`) → `{chapters}`; 400 if unreadable |
| `POST /drafts/{id}/approve` | JSON `{voice?, speed?, chapters?}` (or no body: the voice and speed of the last approval or the upload, every chapter) → `{job_id}`. A voice that doesn't speak the book's language (`report.language`) is replaced by that language's default voice; the job and draft show the one used (D-043). `chapters` is a list of 1-based numbers, added to the book's one library entry (replacing those chapters, keeping the others; D-035). 400 for an empty, repeated or out-of-range list; 409 unless the draft is in review or done |
| `POST /drafts/{id}/cancel` | Cancel the draft's queued or running conversion → its `Job`; the draft goes back to review (D-038). 409 if it isn't converting |
| `DELETE /drafts/{id}` | Discard a draft and its files; 409 while cleaning or converting |
| `GET /jobs` | All conversion jobs (`Job`: queued/running/done/error/cancelled, `done`/`total` sentences, message, `draft_id`, `book_id`) |
| `GET /jobs/{id}` | One job's progress |
| `POST /jobs/{id}/cancel` | Stop a conversion → the `Job`. A queued job never starts; a running one stops at the next sentence. Finished chapters and cached sentences are kept, so approving the draft again resumes. 409 if the job has already ended (D-038) |
| `GET /books` | Library summary (`BookSummary`: title, author, cover, chapters converted, `chapters_total`, duration, size, `complete` = all chapters converted, `converting` = a job for it is queued or running) |
| `GET /books/{id}` | The full `book.json` (`Book`), with the book's `language` (`en` or `zh`; absent in books before D-042, which are English); every chapter has a `number`, `size_bytes` and `updated_ms`, filled in for older books |
| `GET /books/{id}/files/{name}` | A chapter's audio or the cover, with HTTP Range (206). To download a book, fetch each chapter's `audio` file from the manifest; an interrupted download resumes with `Range: bytes=<have>-`. Without a query the file is served inline (no `Content-Disposition`), for `<audio>` and `<img>`. With `?download=1` it is sent as an attachment named `Book Title - Ch 01 - Chapter Title.m4a` (cover: `Book Title - cover.jpg`), with RFC 5987 `filename*` so non-ASCII titles survive (D-034) |
| `DELETE /books/{id}` | Delete a book folder; 409 while a conversion of it is queued or running (D-038) |

Book and draft IDs are validated against `^[a-z0-9\-]{1,80}$` (a draft id must also be a known draft), and file
names reject `/`, `\`, and a leading `.` (path-traversal guard).

## What the Android app calls

The app uses every route except `GET /qr`, `GET /jobs/{id}`, the two `std.epub` routes and the three `/models/zh`
routes (those are the web page's typed-address QR code, the Sigil round-trip, and installing Kokoro v1.1-zh, which
stays on the PC's page).

| Call | Used for |
|---|---|
| `GET /info` | Pairing check (`api_version`, PC name); the Language and Voice lists (`languages`, else `voices`) |
| `GET /books` | The On the PC tab |
| `GET /books/{id}` | Book screen, downloads, version check |
| `GET /books/{id}/files/{name}` | Audio and covers: download (with `Range`) and streaming |
| `DELETE /books/{id}` | Delete from PC (A-014; 409 while converting) |
| `GET /drafts`, `GET /jobs` | The Convert tab (polled every 2 s while visible) |
| `POST /drafts` (multipart: file, voice, speed, auto, ocr) | Upload a book to clean |
| `POST /drafts/cleaned` (multipart: file, voice, speed) | Upload an already-cleaned .std.epub; converts at once |
| `GET /drafts/{id}`, `GET /drafts/{id}/chapters/{i}` | Review: report, picks, chapter text |
| `POST /drafts/{id}/approve` (`{voice, speed, chapters}`; `null` = all) | Convert |
| `POST /drafts/{id}/cancel`, `POST /jobs/{id}/cancel`, `DELETE /drafts/{id}` | Cancel, discard |
| `GET /voices/{voice}/sample` | ▶ voice sample (token in the query) |

Every request sends `Authorization: Bearer <token>`; media URLs carry `?token=` because ExoPlayer and Coil fetch
them themselves.
