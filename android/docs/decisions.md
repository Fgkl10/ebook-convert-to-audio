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

| ID | Title | Parts | Relation |
|---|---|---|---|
| A-001 | Kotlin + Jetpack Compose, one `:app` module | all | |
| A-002 | Latest stable versions; compileSdk 37.2, JDK 21 | build | |
| A-003 | No DI framework, no Retrofit | api, app | |
| A-004 | Books in app-private storage; no backups | library | |
| A-005 | Cleartext HTTP to the PC | api | relies on D-037 |
| A-006 | Downloads in WorkManager with Range resume | download | uses D-038 |
| A-007 | Playback in a Media3 MediaSessionService | player | |
| A-008 | No Google services: QR codes with CameraX + ZXing | pairing | |
| A-009 | Chapter versions on the phone: keep what the PC dropped | library | uses D-038 |
| A-010 | API fixtures made from the real server | tests | |

## A-001 Kotlin + Jetpack Compose, one `:app` module
Status: Accepted · Milestone: M4a
Context: The app is a small player with five screens, for one phone (Redmi K60E, HyperOS 2, Android 14).
Decision: Kotlin, Jetpack Compose with Material 3 (dynamic color, dark mode), Navigation Compose, a single Gradle
module `:app` with packages per area (`api`, `pairing`, `library`, `download`, `player`, `settings`, `ui`).
Why: The user chose Compose. Multi-module builds pay off for large teams, not for a five-screen app.
Consequences: Package boundaries are by convention only; nothing enforces them like `tests/test_layers.py` does for
`desktop/`.

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

## A-003 No DI framework, no Retrofit
Status: Accepted · Milestone: M4a
Context: The app has a handful of long-lived objects (HTTP client, settings, local library) and five API calls.
Decision: `EbookAudioApp` builds one `AppGraph` (reached through `Context.graph`). `ApiClient` is a thin OkHttp
wrapper with kotlinx.serialization and a Bearer-token interceptor.
Why: Hilt/Koin and Retrofit add build time, generated code and concepts that this size doesn't need.
Consequences: Tests construct `ApiClient` and `LocalLibrary` directly (see `DownloaderTest`).

## A-004 Books in app-private storage; no backups
Status: Accepted · Milestone: M4a
Context: Downloaded books need a home. Shared storage needs permissions and lets other apps change the files.
Decision: `filesDir/books/<book id>/` holds `book.json` (the phone's manifest), `chNNN.m4a` and the cover. Book ids
and file names are validated before use (no path traversal). `allowBackup="false"` and `data_extraction_rules.xml`
exclude everything from cloud backups and device transfers.
Why: The user chose app-private storage. No permissions, no media-scanner clutter. The settings hold the pairing
token, which should not leave the phone.
Consequences: Uninstalling the app deletes the downloads. The files can't be opened by other apps.

## A-005 Cleartext HTTP to the PC
Status: Accepted · Milestone: M4a
Context: The PC server is plain HTTP on whatever address the phone pairs with (LAN or ZeroTier IP), so there is no
fixed domain to whitelist.
Decision: `network_security_config.xml` permits cleartext in `base-config` (lint `InsecureBaseConfiguration` is
suppressed with a reason).
Why: TLS would need a certificate the phone trusts for a changing IP; out of scope. The pairing token (D-037) guards
the API, and ZeroTier encrypts its own traffic.
Consequences: On a plain Wi-Fi network the token and the audio travel unencrypted (desktop known gap AUTH-06).

## A-006 Downloads in WorkManager with Range resume
Status: Accepted · Milestone: M4a
Context: A book can be hundreds of MB over a slow VPN. Downloads must survive leaving the app and network drops,
and must never leave a half file that looks complete.
Decision: One unique WorkManager job per book (`download-<id>`, APPEND_OR_REPLACE, needs a network, exponential
backoff, up to 5 attempts), run as a `dataSync` foreground worker with a progress notification. `Downloader` writes
each chapter to `<name>.part`, resumes with `Range: bytes=n-` (206 appends, 416 means already whole), checks the size
against `Content-Range`/`Content-Length`, then moves the file into place atomically and rewrites `book.json` (via a
temp file) after each chapter. Only chapters whose `size_bytes`/`updated_ms` differ from the phone's copy are fetched.
Why: WorkManager survives process death and handles retries and constraints; a plain coroutine would not.
Consequences: Progress reaches the UI through WorkManager progress data (throttled to 400 ms).

## A-007 Playback in a Media3 MediaSessionService
Status: Accepted · Milestone: M4a
Context: Audiobooks play for hours with the screen off and need notification, lock-screen and headset controls.
Decision: `PlaybackService` is a `MediaSessionService` with ExoPlayer (speech audio attributes, audio focus, pause on
"becoming noisy", network wake lock). The UI talks to it through a `MediaController`. A book is a playlist of its
chapters: the downloaded file if present, else the streamed URL (`?token=`). Seek steps are −10 s / +30 s. The
position (chapter + ms per book) is saved on play/pause, on chapter change, every 5 s while playing, and on destroy.
Why: Media3 gives the media notification, lock screen, Bluetooth and foreground-service handling for free.
Consequences: The service is exported (required for system controllers). HyperOS may still kill it unless the user
sets battery "No restrictions" and Autostart; the Settings screen explains this and opens App info.

## A-008 No Google services: QR codes with CameraX + ZXing
Status: Accepted · Milestone: M4a
Context: The phone runs the China ROM of HyperOS, without Google Play services, and the user asked to be told before
any Google service is used (an ML Kit plan was rejected).
Decision: Scan QR codes with CameraX (preview + ImageAnalysis) and ZXing core (`MultiFormatReader`, QR only) on the
luminance plane. No ML Kit, Firebase, Play services or Google APIs. A paste-the-link field is the fallback.
Why: ZXing is Apache-2.0, offline and needs no Play services. AndroidX libraries are open source and contact no
Google servers; Gradle fetches them from Google's Maven repository at build time only.
Consequences: Ask the user before adding any Google service.

## A-009 Chapter versions on the phone: keep what the PC dropped
Status: Accepted · Milestone: M4a
Context: The PC can re-convert chapters (D-038: `size_bytes`, `updated_ms`) or the book can lose chapters there.
Decision: `Versions.state` compares the phone's chapter with the PC's: missing → not downloaded; size or time differ
→ update available; same → downloaded; a chapter the PC no longer has stays "downloaded". `Versions.merge` writes the
PC's book metadata with the phone's chapters, re-indexed, duration summed.
Why: Deleting audio the user already has, because the PC changed, would surprise them offline.
Consequences: Removing a chapter from the phone needs "Delete from phone" (whole book) in M4a.

## A-010 API fixtures made from the real server
Status: Accepted · Milestone: M4a
Context: The app's models mirror `desktop/server/api.py`; a renamed field on the server would break the app silently.
Decision: `tests/test_android_contract.py` (AND-01) converts a made-up story with the fake TTS and compares the
shape (keys and types) of `/info`, `/books` and `/books/{id}` with the fixtures in
`android/app/src/test/resources/api/`, which `ModelsTest` decodes. `UPDATE_ANDROID_FIXTURES=1` rewrites them. The
fixtures use a made-up host name, documentation IPs and a placeholder token.
Why: One check on each side of the contract, both in CI, without running the app against a server.
Consequences: A deliberate API change means: update the Kotlin models, then regenerate the fixtures.
