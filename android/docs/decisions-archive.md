# Android component: decision archive

Settled decisions, moved here from [`decisions.md`](decisions.md) because they are unlikely to change. They are still
in force. The index in `decisions.md` lists every entry, archived or not, and says which file it is in. To change one,
add a new entry in `decisions.md` that supersedes or amends it, and mark the archived entry here.

## A-001 Kotlin + Jetpack Compose, one `:app` module
Status: Accepted · Milestone: M4a
Context: The app is a small player with five screens, for one phone (Redmi K60E, HyperOS 2, Android 14).
Decision: Kotlin, Jetpack Compose with Material 3 (dynamic color, dark mode), Navigation Compose, a single Gradle
module `:app` with packages per area (`api`, `pairing`, `library`, `download`, `player`, `settings`, `ui`).
Why: The user chose Compose. Multi-module builds pay off for large teams, not for a five-screen app.
Consequences: Package boundaries are by convention only; nothing enforces them like `tests/test_layers.py` does for
`desktop/`.

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
sets battery "No restrictions" and Autostart; the Settings screen explains this and opens App info. Other makers
have similar settings: the Settings screen shows the steps for the phone's maker (A-018).

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
Consequences: A deliberate API change means: update the Kotlin models, then regenerate the fixtures. M4b added the
drafts, draft, chapter and jobs responses; a report's `source` (a path on the PC) is reduced to the file name.

## A-011 Convert tab: the web page's rules as tested pure functions
Status: Accepted · Milestone: M4b
Context: The phone gets the web page's conversion features ("everything except Sigil"). The page has rules that are
easy to get subtly different: which chapters are ticked when a review opens, the approve button's label, "converted
N of M", the mixed-voice warning, which jobs to show, which buttons each status gets.
Decision: `ConvertRules` copies those rules from `desktop/web/app.js` as pure functions, unit-tested in
`ConvertRulesTest`; the screens only call them. The Convert tab polls `/drafts` and `/jobs` every 2 s while visible,
like the page. Voice samples play in a short-lived ExoPlayer of their own and pause the book.
Why: Both clients should behave the same, and the rules are where mistakes hide; Compose screens are not tested in CI.
Consequences: A rule change on the web page needs the same change in `ConvertRules` (AND-07).

## A-012 Uploads streamed from the ContentResolver, resendable
Status: Accepted · Milestone: M4b
Context: A book can be a large scanned PDF; the phone shouldn't load it into memory. On the phone, an upload failed
with "unexpected end of stream": the server (uvicorn) closes idle keep-alive connections after 5 s, and an upload
started after a dialog reused such a pooled connection.
Decision: `UploadFile` opens a fresh `InputStream` from the ContentResolver for each write; the multipart body streams
it and reports bytes sent. The body is not one-shot, so OkHttp resends it on a fresh connection when a pooled one
turns out closed. Uploads use a 10-minute write/read timeout.
Why: Memory stays flat for any file size; the resend makes the stale-connection case invisible to the user.
Consequences: A retried upload reads the file twice. The upload runs in the screen's scope: leaving the Upload screen
cancels it (the screen says so).

## A-013 "Open with" / Share for book files
Status: Accepted · Milestone: M4b
Context: On the phone, books arrive in file managers, chat apps (WeChat, QQ) and browsers.
Decision: `MainActivity` takes `ACTION_VIEW` (content: URIs) and `ACTION_SEND` (`EXTRA_STREAM`) for
`application/epub+zip`, `application/pdf`, `text/plain` and `application/octet-stream` (chat apps often send EPUBs
as that). The Uri goes to the Upload screen, through pairing first if needed. The file name (`DISPLAY_NAME`) decides
whether it can be uploaded (.epub/.pdf/.txt); the server checks again.
Why: Saves saving the file somewhere and finding it again in the picker.
Consequences: The app also appears when sharing plain text without a file; then it just opens normally.

## A-014 Delete from PC on the phone
Status: Accepted · Milestone: M4b
Context: The API can delete a library book (`DELETE /books/{id}`, 409 while converting), but the web page has no
button for it. The user asked for it on the phone.
Decision: The book screen's ⋮ menu has "Delete from PC" with a confirmation. The copy on the phone stays; a refusal
(409) is shown on the book screen.
Why: Managing the library from the phone; the confirm guards against a mis-tap.
Consequences: The web page and the phone differ here until the page gets the same button.
