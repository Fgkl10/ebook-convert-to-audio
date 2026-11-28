# Android component: test-case library

The written test cases for `android/`. Each case is **Automated** (a JUnit or pytest name), **Manual** (run on the
phone), or a **Gap** (known untested or unhandled behavior).

Run the automated cases:
- JVM unit tests: `cd android; .\gradlew :app:testDebugUnitTest` (plus `:app:lintDebug`, which fails on errors)
- The contract test: `.venv\Scripts\python -m pytest tests/test_android_contract.py`

CI runs both on each PR into `master` (`android` and `test` jobs in `.github/workflows/ci.yml`).

Manual cases were run on a Redmi K60E (HyperOS 2.0, Android 14) over ZeroTier, against a test server on scratch data
with a one-chapter made-up book. "Pass (date)" records the last run.

Status legend: Automated · Manual · Gap

## API contract

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| AND-01 | Fixtures match the server | Convert a made-up story with the fake TTS; compare `/info`, `/books`, `/books/{id}`, `/drafts`, `/drafts/{id}`, `/drafts/{id}/chapters/0`, `/jobs` with the fixtures | Same keys and types at every level; no real host, address, token or PC path in the fixtures | Automated `tests/test_android_contract.py::test_and01_android_fixtures_match_the_server` |
| AND-06 | The Convert tab decodes the server's JSON | Decode `drafts.json`, `draft.json`, `draft_chapter.json`, `jobs.json` (made by AND-01) and a hand-written report | Drafts, report (chapter and removed pairs), chapter text and jobs decode | Automated `ConvertModelsTest` |
| AND-03 | The app decodes the server's JSON | Decode the fixtures | `Info`, `BookSummary`, `Book` decode; every `pair_url` parses; chapter audio names, sizes, times; sentences end at the chapter's duration; unknown fields ignored | Automated `ModelsTest` (`info`, `books`, `book`, `ignoresFieldsItDoesNotKnow`) |

## Convert tab (M4b)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| AND-07 | The web page's rules | Status labels, buttons per status, visible jobs, default picks (fresh, partly converted, interrupted run), "New only", approve label and chapters (`null` = all), mixed-voice warning, uploadable names | Same results as `desktop/web/app.js` | Automated `ConvertRulesTest` |
| AND-08 | Requests | Multipart upload (fields, exact file bytes, progress), cleaned upload route, approve body with `"chapters": null` and with a list, cancel/discard/delete methods and paths, 409/401 errors, voice sample URL | As listed | Automated `ApiClientTest` |
| AND-08b | Upload over a closed pooled connection | The server closes the connection after a 400; the next upload reuses it | Resent on a fresh connection; succeeds | Automated `ApiClientTest.uploadRetriesWhenThePooledConnectionWasClosed` |
| AND-M12 | Upload, review, convert one chapter | Picker → .txt → sample ▶ → Upload & clean → Review → read a chapter → untick one → Convert 1 chapter → progress → Listen | Only the ticked chapter is converted | Manual, pass (2026-11-28) |
| AND-M13 | Mixed-voice warning | Review again after a partial conversion; pick another voice | Warning shown | Manual, pass (2026-11-28) |
| AND-M14 | Skip review | Upload a one-chapter .txt with "Skip review" | Cleans and converts by itself | Manual, pass (2026-11-28) |
| AND-M15 | Cleaned upload | Upload a .std.epub with "Already cleaned" | Converts at once | Manual, pass (2026-11-28) |
| AND-M16 | Not a cleaned book | Upload an original .epub with "Already cleaned"; wait 10 s; "Clean it" | Offer to clean; uploaded to clean (failed with "unexpected end of stream" before the A-012 fix) | Manual, pass (2026-11-28) |
| AND-M17 | OCR option | Pick a PDF, then a .txt | OCR modes enabled only for the PDF | Manual, pass (2026-11-28) |
| AND-M18 | Cancel a conversion | Start a ~70-sentence chapter, cancel while running | Job "cancelled" partway (55/71 seen) | Manual, pass (2026-11-28) |
| AND-M19 | Discard a draft | Discard a draft in review | Gone from the list and the PC | Manual, pass (2026-11-28) |
| AND-M20 | Open with / Share | Share a .txt from the file manager; open an .epub from WeChat with "Open with other app" | The app opens Add a book with the file chosen | Manual, pass (2026-11-28) |
| AND-M21 | Delete from PC | Book → ⋮ → Delete from PC → confirm | Gone from the PC tab | Manual, pass (2026-11-28) |
| AND-G03 | Delete from PC while converting | Delete a book whose conversion runs | The 409 message on the book screen | Gap (409 mapping covered by AND-08, not run on the phone) |
| AND-G04 | Leaving the Upload screen during an upload | Press Back while uploading | The upload is cancelled (A-012) | Gap (known limitation, not tested) |

## Pairing

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| AND-02 | QR link parsing | Valid links (IPv4, host name, IPv6, no port, https) and invalid ones (no/short/bad token, path, query, user info, other scheme) | Valid → `Pairing(baseUrl, token)`; invalid → null | Automated `PairUrlTest` |
| AND-M01 | Pair by QR code over ZeroTier | PC page → ZeroTier address → scan in the app | Library screen | Manual, pass (2026-11-28) |
| AND-M02 | PC unreachable | Scan a QR code for a port the firewall blocks | "Can't reach http://…" with ZeroTier / other-address advice; stays on the pair screen | Manual, pass (2026-11-28) |
| AND-G01 | Wrong or revoked token while paired | `ebook-server --new-token`, then use the app | Library shows "pair again" | Gap (covered by `NotPaired` in `DownloaderTest`, not run on the phone) |

## Library, versions and downloads

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| AND-04 | Chapter states, merge, positions, media ids | Unit cases for missing / same / changed / dropped chapters; `Position` and `MediaIds` round trips and invalid input | As in A-009; invalid strings → null | Automated `VersionsTest` |
| AND-05a | Full download | MockWebServer book with two chapters | Files byte-identical, `book.json` saved, progress reaches the total, token on every request, no `.part`/`.tmp` left | Automated `DownloaderTest.downloadsTheWholeBook` |
| AND-05b | Cut-off download resumes | Server drops the connection mid-chapter, then a retry | No file under the real name and no listed book after the cut; the retry sends `Range` and completes | Automated `DownloaderTest.aCutOffChapterIsNeverUsedAndResumesWithRange` |
| AND-05c | Only changed chapters fetched | Download chapter 1; re-convert it on the server; download all; download again | Second run fetches ch1 (changed) and ch2 (missing); third fetches nothing | Automated `DownloaderTest.fetchesOnlyChangedOrMissingChapters` |
| AND-05d | Wrong token | Download with a bad token | `NotPaired` | Automated `DownloaderTest.aWrongTokenMeansNotPaired` |
| AND-05e | No path traversal | Bad book ids and file names | Refused | Automated `DownloaderTest.libraryRefusesPathsOutsideItsFolder` |
| AND-M03 | Download on the phone | Book → Download | Progress, then ✓; file SHA-256 equals the PC's; no `.part` left | Manual, pass (2026-11-28) |
| AND-M04 | Update available | Re-convert the chapter on the PC; reopen the book | Update icon; "Download 1"; after it, ✓ again | Manual, pass (2026-11-28) |
| AND-M05 | Delete from phone | Book → Delete from phone | Files gone; position kept; book still on the PC tab | Manual, pass (2026-11-28) |
| AND-G02 | Download in the background for a long book | Start a large download, leave the app | Finishes; notification shows progress | Gap (only a one-chapter book was tested) |

## Playback

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| AND-M06 | Offline playback | Airplane mode on; play a downloaded book | Plays | Manual, pass (2026-11-28) |
| AND-M07 | Lock screen and notification controls | Play, lock the phone | Controls shown; audio continues | Manual, pass (2026-11-28) |
| AND-M08 | Resume after the app is killed | Pause at a point; swipe the app away; reopen the book | "Continue · ch N, m:ss"; resumes there | Manual, pass (2026-11-28) |
| AND-M09 | Streaming | Play a book that isn't downloaded | Streams from the PC | Manual, pass (2026-11-28) |
| AND-M10 | Headphones unplugged | Unplug or disconnect headphones while playing | Pauses | Manual, pass (2026-11-28) |
| AND-M11 | Long playback with the screen off on HyperOS | Battery "No restrictions" + Autostart; play 30+ min screen off | Keeps playing | Manual, pass (2026-11-28) |

## Known gaps

- No instrumented (on-device) tests and no Compose UI tests in CI: screens are checked by hand (AND-M*).
- `PlaybackService` and `DownloadWorker` themselves are only tested on the phone; their logic (`Downloader`,
  `Versions`, `Position`) is unit-tested.
- Cleartext HTTP on plain Wi-Fi (A-005, desktop AUTH-06).
- Test setup: files copied to the phone with `adb push` don't show in the file picker until the media scanner indexes
  them (`adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/...`).
- The PC's firewall must allow the server's port on the network the phone uses (found when a test server on another
  port was unreachable over ZeroTier).
