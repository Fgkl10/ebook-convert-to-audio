# Android component: architecture

The Android app plays the books converted on the PC: it pairs with the PC server, lists the PC's library, downloads
books into app-private storage, and plays them in the background with notification and lock-screen controls.
M4a is the player; M4b adds managing conversions from the phone.

## Overview

```mermaid
flowchart LR
  subgraph Phone["Android app (app.ebookaudio)"]
    UI["ui/ + screens<br/>Compose, Navigation"]
    PAIR["pairing/<br/>PairUrl, QrScanner (CameraX+ZXing)"]
    API["api/<br/>ApiClient (OkHttp), Models"]
    SET["settings/<br/>DataStore: pairing, speed, positions"]
    LIB["library/<br/>LocalLibrary, Versions"]
    DL["download/<br/>Downloads (WorkManager), Downloader"]
    PL["player/<br/>PlaybackService (Media3), PlayerConnection"]
  end
  PC["PC: ebook-server<br/>/api/v1 (desktop/server)"]
  UI --> PAIR & API & LIB & DL & PL & SET
  PAIR --> API
  PAIR --> SET
  DL --> API
  DL --> LIB
  PL --> LIB
  PL --> SET
  API -- "HTTP + Bearer token<br/>(LAN or ZeroTier)" --> PC
  PL -- "stream ?token=" --> PC
```

## Modules (packages of `:app`)

| Package | Files | Responsibility |
|---|---|---|
| (root) | `EbookAudioApp.kt` | `AppGraph`: one OkHttp client, `Settings`, `LocalLibrary`, an app scope; `api()` builds an `ApiClient` from the saved pairing (A-003) |
| `api` | `ApiClient.kt`, `Models.kt` | Typed calls `info`, `books`, `book(id)`; `fileUrl` with `?token=` for the player and Coil. 401 → `NotPaired`; other errors → `ApiError` with the server's `detail`. Models ignore unknown keys |
| `pairing` | `PairUrl.kt`, `Scanner.kt`, `PairScreen.kt` | Parse `http(s)://host:port/#token=…` (D-037); scan with CameraX + ZXing (A-008) or paste; check `GET /info` (`api_version` 1) before saving |
| `settings` | `Settings.kt` | DataStore: pairing `{baseUrl, token, pcName}`, playback speed, last book, position per book (`chapter:ms`) |
| `library` | `LocalLibrary.kt`, `Versions.kt`, `LibraryScreen.kt`, `BookScreen.kt` | Books on the phone (A-004); chapter states and merging (A-009); the On this phone / On the PC tabs; the book screen (play/continue, download, delete, per-chapter state) |
| `download` | `Downloader.kt`, `DownloadWorker.kt` | Range-resumable, size-checked, atomic chapter downloads in a WorkManager foreground worker (A-006) |
| `player` | `PlaybackService.kt`, `PlayerConnection.kt`, `NowPlaying.kt`, `PlayerScreen.kt` | Media3 session + ExoPlayer (A-007); playlist = chapters (file or stream); position saving; player and mini player UI |
| `ui` | `MainActivity.kt`, `SettingsScreen.kt`, `Theme.kt`, `Format.kt` | Edge-to-edge activity, navigation, theme, settings with the HyperOS background-playback help |

## Data on the phone

```
filesDir/books/<book id>/          book id: [a-z0-9-]{1,80}
  book.json                        the phone's manifest: the PC's Book JSON, only the downloaded chapters
  ch000.m4a, ch001.m4a, …          chapter audio (AAC/M4A, as on the PC)
  ch000.m4a.part                   an unfinished download (never played, resumed with Range)
  cover.jpg|png                    optional
DataStore "settings"               pairing, speed, last book, positions
```

`book.json` uses the server's format (`desktop/docs/architecture.md`, `/api/v1/books/{id}`), so the same model
decodes both. Each chapter keeps `size_bytes` and `updated_ms` from the download, which is how "update available"
is detected (D-038, A-009). Sentences are stored but unused until M5 (sentence sync).

## API used (`/api/v1`, see `desktop/docs/architecture.md`)

| Call | Used for |
|---|---|
| `GET /info` | Pairing check (`api_version`, PC name) |
| `GET /books` | The On the PC tab |
| `GET /books/{id}` | Book screen, downloads, version check |
| `GET /books/{id}/files/{name}` | Audio and covers: download (with `Range`) and streaming |

Every request sends `Authorization: Bearer <token>`; media URLs carry `?token=` because ExoPlayer and Coil fetch
them themselves.

## Build

| Item | Value |
|---|---|
| Versions | `android/gradle/libs.versions.toml` (A-002) |
| SDK | compileSdk 37.2, targetSdk 37, minSdk 26 |
| JDK | 21 (Android Studio's `jbr` locally; Temurin 21 in CI); Java 17 bytecode |
| Commands | `cd android; .\gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug` |
| Output | `android/app/build/outputs/apk/debug/app-debug.apk` |
| CI | the `android` job in `.github/workflows/ci.yml` |
