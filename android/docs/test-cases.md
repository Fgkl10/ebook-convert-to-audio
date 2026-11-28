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
| AND-01 | Fixtures match the server | Convert a made-up story with the fake TTS; compare `/info`, `/books`, `/books/{id}` with the fixtures | Same keys and types at every level; no real host, address or token in the fixtures | Automated `tests/test_android_contract.py::test_and01_android_fixtures_match_the_server` |
| AND-03 | The app decodes the server's JSON | Decode the fixtures | `Info`, `BookSummary`, `Book` decode; every `pair_url` parses; chapter audio names, sizes, times; sentences end at the chapter's duration; unknown fields ignored | Automated `ModelsTest` (`info`, `books`, `book`, `ignoresFieldsItDoesNotKnow`) |

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
- The PC's firewall must allow the server's port on the network the phone uses (found when a test server on another
  port was unreachable over ZeroTier).
