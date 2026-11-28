# Android component: decision log

Each entry records why a design choice was made in `android/`. Add new entries at the bottom and never renumber old
ones. If a decision is reversed, add a new entry that supersedes the old one and mark the old one
`Superseded by A-xxx`. Server-side decisions live in `desktop/docs/decisions.md` (D-xxx).

Template:

```
## A-NNN Title
Status: Accepted | Superseded by A-xxx · Milestone: Mx
Context: what problem or constraint forced a choice
Decision: what we chose
Why: reasons, alternatives rejected
Consequences: trade-offs we accept
```

## Index

Every entry, in both files. "Here" entries are below; settled entries that are unlikely to change are in
[`decisions-archive.md`](decisions-archive.md) and still in force. New entries go here. Search this table for a
keyword, then read only that entry.

| ID | Title | Parts | Relation | File |
|---|---|---|---|---|
| A-001 | Kotlin + Jetpack Compose, one `:app` module | all | | [archive](decisions-archive.md) |
| A-002 | Latest stable versions; compileSdk 37.2, JDK 21 | build | | here |
| A-003 | No DI framework, no Retrofit | api, app | | [archive](decisions-archive.md) |
| A-004 | Books in app-private storage; no backups | library | | [archive](decisions-archive.md) |
| A-005 | Cleartext HTTP to the PC | api | relies on D-037 | [archive](decisions-archive.md) |
| A-006 | Downloads in WorkManager with Range resume | download | uses D-038 | [archive](decisions-archive.md) |
| A-007 | Playback in a Media3 MediaSessionService | player | | [archive](decisions-archive.md) |
| A-008 | No Google services: QR codes with CameraX + ZXing | pairing | | here |
| A-009 | Chapter versions on the phone: keep what the PC dropped | library | uses D-038 | [archive](decisions-archive.md) |
| A-010 | API fixtures made from the real server | tests | | [archive](decisions-archive.md) |
| A-011 | Convert tab: the web page's rules as tested pure functions | convert | mirrors desktop/web/app.js | [archive](decisions-archive.md) |
| A-012 | Uploads streamed from the ContentResolver, resendable | api | | [archive](decisions-archive.md) |
| A-013 | "Open with" / Share for book files | ui | | [archive](decisions-archive.md) |
| A-014 | Delete from PC on the phone | library | uses `DELETE /books/{id}` | [archive](decisions-archive.md) |
| A-015 | Read-along in the player screen | player | same rules as desktop D-039 | here |
| A-016 | Sleep timer in the playback service | player | | here |
| A-017 | English, Simplified and Traditional Chinese | all screens | desktop D-040 | here |
| A-018 | Background-playback steps per phone maker | ui | generalizes A-007's HyperOS note | here |
| A-019 | Language choice in Settings, through AppCompat | ui | amends A-017 | here |
| A-020 | APK built and signed by GitHub Actions | build, CI | | here |
| A-021 | Chinese voices: Language and Voice pickers, Chinese read-along | convert, player | desktop D-042, D-043 | here |

## A-002 Latest stable versions; compileSdk 37.2, JDK 21
Status: Accepted · Milestone: M4a
Context: A new project; the versions are pinned in `android/gradle/libs.versions.toml` (AGP 9.5.3, Gradle 9.9.3,
Kotlin 2.4.21, Compose BOM 2026.11.01, Media3 1.11.1, OkHttp 5.5.1, CameraX 1.7.0, ZXing 3.5.4, …).
AGP 9 has built-in Kotlin support with an older bundled Kotlin. The newest AndroidX and OkHttp releases need
`compileSdk` 37.1 or later. Only JDK 21 (Android Studio's `jbr`) is installed.
Decision: Use the latest stable version of every library. Declare the Kotlin 2.4.21 Compose and serialization
plugins `apply false` in the root build, which raises the Kotlin version AGP uses. `compileSdk` is API 37.2
(`release(37) { minorApiLevel = 2 }`), `targetSdk` 37, `minSdk` 26. No Java toolchain is requested: the build runs
on JDK 21 and emits Java 17 bytecode. CI uses Temurin 21.
Why: A new app should start on current versions; holding back on `compileSdk` would mean holding back on AndroidX.
`compileSdk` only changes which APIs compile; `targetSdk` 37 only changes behavior on Android 16+, and the phone runs
Android 14. Requesting a JDK 17 toolchain failed, because Gradle has no download repository configured.
Consequences: AGP downloads the Android 37.2 platform on first build (CI too). Version bumps are one file.

## A-008 No Google services: QR codes with CameraX + ZXing
Status: Accepted · Milestone: M4a
Context: The phone runs the China ROM of HyperOS, without Google Play services, and the user asked to be told before
any Google service is used (an ML Kit plan was rejected).
Decision: Scan QR codes with CameraX (preview + ImageAnalysis) and ZXing core (`MultiFormatReader`, QR only) on the
luminance plane. No ML Kit, Firebase, Play services or Google APIs. A paste-the-link field is the fallback.
Why: ZXing is Apache-2.0, offline and needs no Play services. AndroidX libraries are open source and contact no
Google servers; Gradle fetches them from Google's Maven repository at build time only.
Consequences: Ask the user before adding any Google service.

## A-015 Read-along in the player screen, same rules as the web reader
Status: Accepted · Milestone: M5
Context: Each chapter carries `sentences: [{i, p, text, start_ms, end_ms}]` (D-012). The user wanted the text in the
player, shown by default, with the cover one tap away, plus text size, previous/next sentence buttons and the screen
kept on while reading.
Decision:
- The player screen shows the chapter text (`ReadAlong.kt`), paragraphs grouped by `p`. The sentence being read is
  highlighted and scrolled to a third of the way down. Tapping a sentence plays from it. Scrolling by hand stops the
  automatic scrolling while dragging or flinging, and for 4 s after.
- The sentences come from the phone's `book.json`, else `GET /books/{id}`. If neither works (offline and not
  downloaded, not paired) the cover shows; playback never depends on the text.
- The lookup is `SentenceSync`: a binary search over `start_ms`, the same rule as `desktop/web/app.js`. "‹ Sentence"
  restarts the current sentence when more than 1.5 s into it, else goes to the one before. "Sentence ›" does nothing
  on the last sentence. Both start playback. The web reader has the same buttons with the same rule.
- Text size 12–32 sp in steps of 2 (default 18) and the text/cover choice are kept in DataStore. The web reader uses
  the same range in px, kept in `localStorage`.
- The screen stays on (`FLAG_KEEP_SCREEN_ON` on the activity's window) only while the text is shown and playing.
  Setting `View.keepScreenOn` from Compose didn't keep the screen on during the phone test (HyperOS).
- The highlight follows a 100 ms poll of the controller on the player screen (250 ms elsewhere).
Why: One set of rules for both readers, checked by AND-11, so the phone and the PC feel the same. Times are positions in
the audio, so speed changes need no handling.
Consequences: Streaming a book fetches its JSON once per chapter shown. Long chapters are one `LazyColumn` item per
paragraph, so only the visible paragraphs are laid out.

## A-016 Sleep timer in the playback service
Status: Accepted · Milestone: M5
Context: The user wanted to stop after a set time (presets, custom minutes) or at the end of the chapter, with the
screen off.
Decision:
- The timer lives in `PlaybackService`, so it keeps running with the screen off and the app in the background. The UI
  sets it with a custom session command (`app.ebookaudio.SLEEP`: mode off / minutes / chapter); the service publishes
  the mode and the time left as session extras, which `NowPlaying` reads.
- Minutes count real time spent playing (a pause, e.g. a call, doesn't use it up). The volume fades out over the last
  10 s, then the player pauses, the volume goes back to 1 and the timer turns off.
- "End of this chapter" uses ExoPlayer's `pauseAtEndOfMediaItems`. The timer clears when the player pauses at the end
  of the item, or when the book ends on its last chapter. Its time left is the chapter's remaining audio at the
  current speed.
- Presets 15/30/45/60 minutes, "Other…" for 1–1440 minutes, "Turn off". The button is in the player's bottom row,
  next to Speed (the user's choice), and shows the time left. The mini player shows it too.
- The timer state is in memory only: it doesn't survive the service being stopped.
- The countdown and fade are the pure `SleepTimer` class, unit-tested. The service glue is tested by hand.
Why: A timer in the UI would stop when the screen is off. The fade avoids an abrupt cut while falling asleep.
Consequences: `pauseAtEndOfMediaItems`, `DEFAULT_SESSION_COMMANDS` and `DEFAULT_PLAYER_COMMANDS` are Media3
`@UnstableApi`, opted into in the service. No sleep timer on the web page (not asked for).

## A-017 English, Simplified and Traditional Chinese
Status: Accepted · Milestone: M6a
Context: The user asked for Simplified and Traditional Chinese support. For now that means the interface; Chinese
voices are a later milestone. The app's text was hard-coded English in Compose.
Decision:
- Every user-visible string moved to `res/values/strings.xml`, with translations in `values-b+zh+Hans` and
  `values-b+zh+Hant`. Script qualifiers, not region ones (`zh-rCN`, `zh-rTW`): Android 7+ resolves zh-CN/SG to Hans
  and zh-TW/HK/MO to Hant, so one folder covers each script. Traditional uses Taiwan wording.
- The app follows the phone's language. On Android 13+ the system's per-app language setting lists the three
  languages, from `generateLocaleConfig`. (At first there was no in-app picker; A-019 added one.)
- `ConvertRules` returns values instead of English text (`StatusLabel`, `ApproveLabel`, `MixedVoice`), so it stays a
  pure, tested function; `ConvertText.kt` maps them to resources. `Format.duration` became the composable
  `durationText`.
- Screens read strings in callbacks through `LocalResources.current` (lint flags `LocalContext.getString` as not
  configuration-aware). `Resources.errorText` shows "not paired" in the app's language and otherwise the message
  from the PC or the network.
- Shared labels use the same words as the web page (D-040), e.g. "Other addresses" → 其他地址 / 其他位址, which the
  pairing messages point to.
Why: Android resources are the standard way: the system picks the language, lint checks completeness, and
`pluralStringResource` handles English plurals (Chinese has one form).
Consequences: Messages from the PC (errors, draft/job messages, cleaning reports) and OkHttp's network errors stay
English. Adding a string means adding it to all three files, or lint fails the build.

## A-018 Background-playback steps per phone maker
Status: Accepted · Milestone: M6a
Context: The Settings screen explained only HyperOS's battery settings (the test phone). The user wants the project
to work on any Android phone. Each maker hides "let this app run in the background" somewhere else.
Decision: `BackgroundTips.vendorOf(Build.MANUFACTURER, Build.BRAND)` picks one of Xiaomi (also Redmi, POCO),
Huawei/Honor, Samsung, OPPO (also OnePlus, realme), vivo (also iQOO) or Other. The section "Playing with the screen
off" shows a general line plus that maker's steps (a string per vendor) and keeps the **Open app info** button. The
README has the same table and links dontkillmyapp.com.
Why: Showing only the relevant steps is shorter than a list for every maker; the brand fallback catches phones whose
manufacturer field is unusual. A pure function is unit-tested (`BackgroundTipsTest`).
Consequences: The steps follow each vendor's documented settings and change between OS versions; only the Xiaomi
steps were tried on a real phone. Unknown makers get the stock-Android steps.

## A-019 Language choice in Settings, through AppCompat
Status: Accepted · Milestone: M6a · Amends A-017
Context: A-017 left the language to the system. On the test phone (HyperOS 2, Android 14) the user could not find
the system's per-app language screen, and asked for a choice inside the app.
Decision: Settings has a **Language** section with one dropdown (amended after M7 at the user's request, formerly a
radio list; the same `ui/DropdownField` as the voice pickers): Phone's language / English / 简体中文 / 繁體中文. The language names are
written in their own script and not translated, so each can be found whatever the current language. A pick calls
`AppCompatDelegate.setApplicationLocales` (empty list = the phone's language), which recreates the activity in the
new language. `AppLanguage.fromTags` maps the current locale list back to a choice, and treats zh-TW/HK/MO as
Traditional because the system setting may store a region. To make this work on Android 8–12, `MainActivity`
became an `AppCompatActivity` (theme parent `Theme.AppCompat.DayNight.NoActionBar`; Compose still draws
everything), and the manifest enables AppCompat's `AppLocalesMetadataHolderService` with `autoStoreLocales`.
Why: AndroidX AppCompat (open source, not a Google service) is the standard way to get one API for every Android
version. On 13+ it writes through to the system's own setting, so the two never disagree. A hand-made
`attachBaseContext` wrapper would need its own storage and would not update the system setting.
Consequences: A new dependency, `androidx.appcompat:appcompat` 1.8.0. On Android 8–12 the choice reaches the
activity only. The download notification there (built from the application context) and Media3's notification
stay in the phone's language.

## A-020 APK built and signed by GitHub Actions
Status: Accepted · Milestone: after M6a
Context: The APK was built on the PC only. The user wants to download it from GitHub. CI already built a debug
APK, but each runner signs with a new random debug key, and Android installs an update only when the signing key
matches. That APK could never update an installed app.
Decision:
- One release key (RSA 4096, alias `ebook-audio`, `CN=Ebook Audio`, PKCS12). It lives in GitHub Secrets
  (`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`), with a
  local copy in the git-ignored `android/keystore/` that the user also backs up outside the project.
- `build.gradle.kts` takes the key from environment variables (CI) or `android/keystore/release.properties` (PC).
  Both debug and release builds use it when present, so a PC build and a downloaded APK install over each other.
  Without the key (other clones, PRs), builds fall back to the standard debug key.
- `versionCode` is the commit count (`git rev-list --count HEAD`), the same number on the PC and on GitHub, so the
  newer commit always wins. A run number would differ from the PC's and block installs as a downgrade.
  `versionName` comes from the tag (`v0.5.0` → `0.5.0`), else the file's value.
- `.github/workflows/apk.yml` (separate from `ci.yml`):
  - a push to `master` that touches `android/**` gives a signed release APK as the run's artifact (90 days);
  - a `v*` tag also gives a GitHub Release with `ebook-audio-<version>.apk`. Tags come through the `create`
    event, because a `paths` filter would also apply to a tag push.
  - The job fails if the key secret is missing and checks the certificate with `apksigner`.
Why: Releases give a permanent public download link without a PC build. Artifacts give every master change without
tagging. Secrets keep the key out of the repository, which is public.
Consequences:
- Losing the key means later APKs can't update the installed app; the user then has to uninstall, which deletes
  the phone's downloads and settings.
- Pull requests from forks get no signed APK (no secrets).
- The first install with the new key needed one uninstall of the earlier build, which used the old local debug
  key.
- Release builds are not minified (`isMinifyEnabled = false`), as before.

## A-021 Chinese voices: Language and Voice pickers, Chinese read-along
Status: Accepted · Milestone: M7 (Chinese voices)
Context: The PC converts Chinese books and groups its voices by language (desktop D-042, D-043). The user wanted two
dropdowns, a Language and a Voice that follows it, on the phone as on the PC's page. Chinese has no spaces between
sentences, and the read-along joined sentences with one.
Decision:
- `Info.languages` (`[{code, voices, default_voice}]`). With a PC before D-043 it is one English entry made from the
  flat `voices` list, so the app still works with an older PC.
- `VoiceAndSpeed` shows a Language dropdown (hidden when there is only one) above the Voice dropdown. Choosing a
  language picks that language's default voice. The language shown is the current voice's.
- `ConvertRules`, tested like the other rules (A-011):
  - `languageOf` and `voiceFor` (the voice when it speaks the language, else the language's default);
  - `startVoice` (Upload starts in the interface's language: Chinese for 简体 / 繁體).
  Review starts on `report.language`, keeping the book's voice when it speaks it.
- Read-along joins two sentences with nothing when either side is a Chinese character or Chinese punctuation
  (`SentenceSync.gap`), and with a space otherwise. It is judged from the text, not `book.json`'s `language`, so books
  downloaded before that field show right too.
- Installing Kokoro v1.1-zh (desktop D-044) stays on the PC's page; the phone just gets the longer Chinese list.
Why: Same behaviour as the web page, and the rules stay pure functions with unit tests.
Consequences:
- The app doesn't remember the last voice per language; a language switch starts on that language's default.
- A mixed English–Chinese paragraph joins an English sentence after a Chinese one without a space.
