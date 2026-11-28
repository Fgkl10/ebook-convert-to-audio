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
| AND-03 | The app decodes the server's JSON | Decode the fixtures | `Info`, `BookSummary`, `Book` decode; every `pair_url` parses; `Info.languages` is en and zh, each default among its voices; chapter audio names, sizes, times; sentences end at the chapter's duration; unknown fields ignored | Automated `ModelsTest` (`info`, `books`, `book`, `ignoresFieldsItDoesNotKnow`) |
| AND-03b | An older PC without `languages` | Decode an `/info` with only `voices` and `default_voice` | One English language made from the flat list (A-021) | Automated `ModelsTest.infoFromAPcBeforeChineseVoices` |

## Convert tab (M4b)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| AND-07 | The web page's rules | Status labels, buttons per status, visible jobs, default picks (fresh, partly converted, interrupted run), "New only", approve label and chapters (`null` = all), mixed-voice warning, uploadable names | Same results as `desktop/web/app.js`. Labels are values (`StatusLabel`, `ApproveLabel`, `MixedVoice`) that the screens localize (A-017) | Automated `ConvertRulesTest` |
| AND-07b | Voices by language | `languageOf`, `voiceFor` (kept, English voice for a Chinese book, a voice the PC no longer offers, no list yet), `startVoice` for zh / en | As in A-021, the same as the web page (desktop D-043) | Automated `ConvertRulesTest.voicesByLanguage` |
| AND-M38 | Language ▸ Voice on the phone | Add a book: switch Language to 中文, play a sample, upload a Chinese EPUB; Review it | The Voice list follows the Language; Review starts on 中文 with a Chinese voice; the book converts | Manual, pass (2026-11-28, K60E, versionCode 104, the 认知觉醒 sample, one chapter with `zf_001`) |
| AND-M39 | Chinese read-along | Play a converted Chinese chapter with the text shown | No spaces between sentences; the highlight moves sentence by sentence; tapping a sentence plays from it | Manual, pass (2026-11-28, K60E, streamed) |
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

## Read-along and sleep timer (M5)

These manual cases used a made-up two-chapter book (both chapters converted, so "end of chapter" could be checked
against the next one).

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| AND-09 | Sentence lookup and buttons | Positions before, at and between sentence starts, past the end; 1,000 sentences; previous at 0.5 s / 1 s / 2 s into a sentence; next on the last sentence; paragraph grouping; the gap between sentences (English: a space; Chinese: none, A-021) | Same rules as the web reader (A-015) | Automated `SentenceSyncTest` |
| AND-10 | Sleep timer logic | Minutes count down, never below 0, expire; fade over the last 10 s; end of chapter uses the chapter's time left at the speed; invalid minutes refused | As listed (A-016) | Automated `SleepTimerTest` |
| AND-11 | The web reader and the app share the reading rules | Read `app.js`, `index.html`, `app.css`, `SentenceSync.kt`, `Settings.kt`, `PlayerScreen.kt` | Same restart threshold and text size range; the web buttons exist and are wired; both clients start playback from a sentence button | Automated `tests/test_android_contract.py::test_and11_web_reader_and_app_share_the_reading_rules` |
| AND-M22 | Read along while streaming | Play a book that isn't downloaded; open the player | Text shown; current sentence highlighted, a third of the way down; hand scroll holds the auto-scroll until 4 s after; tapping a sentence plays from it | Manual, pass (2026-11-28) |
| AND-M23 | Buttons and remembered settings | ‹ Sentence / Sentence ›; Larger / Smaller text; cover ⇄ text; force-close and reopen | As in A-015; text size and text/cover choice remembered | Manual, pass (2026-11-28) |
| AND-M24 | Keep the screen on | Screen timeout 15–30 s; text view playing, paused, cover view | Stays on only while the text is shown and playing (failed with `View.keepScreenOn`; passes with the window flag) | Manual, pass (2026-11-28) |
| AND-M25 | Minutes timer with the screen locked | Sleep → Other… → 1 minute; lock the phone | Fades over the last 10 s and pauses; normal volume on the next play | Manual, pass (2026-11-28) |
| AND-M26 | End of this chapter | Near the end of chapter 1 → End of this chapter | Stops at the end of chapter 1; chapter 2 doesn't start | Manual, pass (2026-11-28) |
| AND-M27 | Timer state after leaving the player | Set a timer, pause, leave the player, come back | The sleep button and the mini player still show the time left | Manual, pass (2026-11-28) |
| AND-M28 | Read along offline | Download the book; airplane mode; open the player | Text from the phone's copy | Manual, pass (2026-11-28) |
| AND-M29 | End-of-chapter timer on the book's last chapter | Set "End of this chapter" in the last chapter | Playback ends; the timer clears (`STATE_ENDED`) | Manual, pass (2026-11-28) |
| AND-G06 | Sleep timer after the service is stopped | Set a timer, then stop playback from the notification | The timer is gone (in memory only, A-016) | Gap (by design, not tested) |

## Languages and other phones (M6a)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| AND-12 | Battery steps per phone maker | `vendorOf` with Xiaomi, Redmi, POCO, HUAWEI, HONOR, samsung, OnePlus, realme, vivo, " iQOO ", an unknown manufacturer with a known brand, Google, motorola, null, "" | The matching vendor; the brand when the manufacturer is unknown; Other for the rest (A-018) | Automated `BackgroundTipsTest` |
| AND-13 | Every string translated | Build with lint | `MissingTranslation` / `ExtraTranslation` (errors) find no key missing from or extra in `values-b+zh+Hans` / `values-b+zh+Hant`; no `LocalContext.getString` in composition | Automated `:app:lintDebug` (CI) |
| AND-14 | Language choice reads back | `AppLanguage.fromTags` with each choice's tag, zh-CN, zh, zh-Hans-SG, zh-TW, zh_HK, zh-Hant-MO, "en-US,zh-Hans", "", " ", fr-FR | The same choice; regions → their script; unknown or empty → the phone's language (A-019) | Automated `AppLanguageTest` |
| AND-M30 | App in Simplified Chinese | The system per-app language set to `zh-Hans` (`adb shell cmd locale set-app-locales app.ebookaudio --locales zh-Hans`, since HyperOS hides that screen); open Library, Convert, Settings, the player | The screens in Simplified Chinese; messages from the PC stay English | Manual, pass (2026-11-28; the download notification not checked) |
| AND-M31 | App in Traditional Chinese | Settings → Language → 繁體中文; open the other screens | As AND-M30 in Traditional Chinese (Taiwan wording) | Manual, pass (2026-11-28) |
| AND-M32 | Settings shows the phone maker's steps | Open Settings on the Redmi K60E | "Playing with the screen off" with the Xiaomi steps; Open app info works | Manual, pass (2026-11-28) |
| AND-M33 | Language choice in Settings | Settings → Language dropdown → 繁體中文; force-close and reopen; then 跟隨手機語言 | Redraws in Traditional at once, Settings stays open; still Traditional after the reopen; back to the phone's language (English) | Manual, pass (2026-11-28, Android 14; again with the dropdown, versionCode 105). **Gap:** not run on Android 8–12, where AppCompat stores the choice |
| AND-G07 | Battery steps on other makers' phones | Open Settings on a Samsung, Huawei/Honor, OPPO/OnePlus/realme, vivo and a Pixel | The steps match that phone's menus | Gap (only a Xiaomi phone is available; the steps follow the vendors' documented settings) |
| AND-G08 | Server messages in Chinese | Use the app in Chinese; cause a PC error; review a cleaned book | Error details, draft/job messages and cleaning-report entries are English (A-017, desktop D-040) | Gap (known limitation) |

## Building and publishing the APK (A-020)

| ID | Case | Steps / input | Expected | Status |
|---|---|---|---|---|
| AND-M34 | Same key on the PC and on GitHub | Build `assembleDebug` and `assembleRelease` locally with `android/keystore/`; build `assembleRelease` with the key in environment variables (as CI) and `VERSION_NAME=9.9.9`; `apksigner verify --print-certs`; `aapt2 dump badging` | All three: certificate `CN=Ebook Audio`, SHA-256 `012e71…a1e5`; versionCode = commit count; versionName 0.5.0, and 9.9.9 from the variable | Manual, pass (2026-11-28) |
| AND-M35 | APK artifact on a master push | Merge a change under `android/`; open Actions → APK | The run passes; the artifact `ebook-audio-<count>-<sha>.apk` downloads; same certificate as AND-M34 | Manual, pass (2026-11-28: `ebook-audio-98-d9c3b05.apk`, `CN=Ebook Audio`, SHA-256 `012e71…a1e5`, versionCode 98) |
| AND-M36 | Release on a tag | Push tag `v0.5.0` | A GitHub Release `v0.5.0` with `ebook-audio-0.5.0.apk` | Manual, pass (2026-11-28; the downloaded file's SHA-256 matched the release's digest) |
| AND-M37 | Updates install over each other | On the phone: install the Release APK; then `adb install -r` a newer PC build | Both install without an uninstall; downloads and settings kept | Manual, pass (2026-11-28, K60E: v0.5.0 release, code 98, after a one-time uninstall of the old debug-key build; then a PC `assembleDebug`, code 100, installed over it with `-r`). HyperOS asks for a tap on the phone for each USB install |
| AND-G09 | No key | Build in a clone without `android/keystore/` and without the variables | Builds with the standard debug key (seen in the `ci.yml` PR job) | Gap (`apk.yml`'s missing-secret failure not tested) |

## Known gaps

- No instrumented (on-device) tests and no Compose UI tests in CI: screens are checked by hand (AND-M*).
- `PlaybackService` and `DownloadWorker` themselves are only tested on the phone; their logic (`Downloader`,
  `Versions`, `Position`, `SleepTimer`) is unit-tested. The sleep timer's service glue (session command, extras,
  fade applied to the player, end-of-item pause) is manual only (AND-M25..M27).
- The read-along view (`ReadAlong.kt`: scrolling, highlight, taps) is checked by hand only; its lookup is
  `SentenceSync` (AND-09).
- Cleartext HTTP on plain Wi-Fi (A-005, desktop AUTH-06).
- Test setup: files copied to the phone with `adb push` don't show in the file picker until the media scanner indexes
  them (`adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/...`).
- The PC's firewall must allow the server's port on the network the phone uses (found when a test server on another
  port was unreachable over ZeroTier).
