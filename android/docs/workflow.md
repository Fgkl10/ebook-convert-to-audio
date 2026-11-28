# Android component: workflows

## Start and pairing

```mermaid
flowchart TD
  A[App starts] --> B{Paired, or books on the phone?}
  B -- no --> P[Pair screen]
  B -- yes --> L[Library]
  P --> S[Scan the QR code on the PC's page<br/>or paste the link]
  S --> Q{"PairUrl.parse:<br/>http(s)://host:port/#token=…"}
  Q -- invalid --> P
  Q -- valid --> I[GET /api/v1/info with the token]
  I -- 401 --> E1[Error: token not accepted, scan again] --> P
  I -- unreachable --> E2[Error: server running? ZeroTier on?<br/>pick another address on the PC] --> P
  I -- api_version 1 --> V[Save baseUrl, token, PC name] --> L
```

## Library and download

```mermaid
sequenceDiagram
  participant U as User
  participant B as BookScreen
  participant W as DownloadWorker (WorkManager)
  participant D as Downloader
  participant PC as PC server
  U->>B: open a book
  B->>PC: GET /books/{id}
  B->>B: Versions.state per chapter (✓ / ↓ / update)
  U->>B: Download N
  B->>W: enqueue unique work "download-<id>"
  W->>D: download(book, wanted)
  D->>PC: GET /books/{id}, cover
  loop each missing or changed chapter
    D->>PC: GET files/chNNN.m4a (Range: bytes=n- if a .part exists)
    D->>D: append to .part, check size, move into place
    D->>D: write book.json (atomic)
    D-->>W: progress (notification, UI)
  end
  W-->>B: finished (or retry on network loss, up to 5 attempts)
```

## Playback and resume

```mermaid
flowchart TD
  A[Play / Continue on the book screen] --> B[Playlist.items: per chapter,<br/>local file if downloaded, else stream URL with ?token=]
  B --> C[MediaController → PlaybackService<br/>setMediaItems at saved chapter + ms, speed]
  C --> D["ExoPlayer plays; notification + lock screen controls"]
  D --> E{Event}
  E -- play/pause, chapter change, every 5 s --> F[Save position chapter:ms in DataStore]
  E -- headphones unplugged --> G[Pause]
  E -- app swiped away, not playing --> H[Service stops]
  F --> D
  I[App reopened] --> J[Book screen shows Continue · ch N, m:ss] --> A
```

## Read along (M5)

```mermaid
flowchart TD
  A[Player screen opens] --> B{Text or cover? DataStore}
  B -- cover --> C[Cover]
  B -- text --> D{Sentences of the playing chapter}
  D -- "in the phone's book.json" --> F
  D -- "else GET /books/{id}" --> F[ReadAlong: paragraphs by p]
  D -- "neither (offline, not paired)" --> C
  F --> G["Every 100 ms: position → SentenceSync.at (binary search over start_ms)"]
  G --> H[Highlight; scroll it a third of the way down<br/>unless scrolled by hand in the last 4 s]
  H --> G
  F -- tap a sentence --> I[seekTo start_ms, play]
  J["‹ Sentence / Sentence ›"] --> K["SentenceSync.previousStart / nextStart → seekTo, play"]
  F -- "text shown and playing" --> L[Window FLAG_KEEP_SCREEN_ON]
```

## Sleep timer (M5)

```mermaid
sequenceDiagram
  participant UI as Player screen
  participant S as PlaybackService
  participant P as ExoPlayer
  UI->>S: custom command SLEEP (minutes N / chapter / off)
  alt minutes
    loop every 250 ms
      S->>S: count down by real time spent playing
      S->>P: volume fades over the last 10 s
      S-->>UI: session extras (mode, time left in whole seconds)
    end
    S->>P: pause at 0; volume 1; timer off
  else end of chapter
    S->>P: pauseAtEndOfMediaItems = true
    P-->>S: paused at the end of the item, or the book ended
    S->>P: pauseAtEndOfMediaItems = false; timer off
  end
```

## Convert on the PC from the phone (M4b)

```mermaid
flowchart TD
  A["Convert tab: Add a book"] --> B["Upload screen"]
  O["Open with / Share from another app"] --> P{Paired?}
  P -- no --> PR[Pair screen] --> B
  P -- yes --> B
  B --> C{Already cleaned?}
  C -- "yes (.std.epub)" --> D["POST /drafts/cleaned"]
  D -- "400 Not a cleaned book" --> E["Clean it now?"] --> F
  D -- ok --> J
  C -- no --> F["POST /drafts (voice, speed, auto, ocr)"]
  F --> G["PC cleans it: draft 'cleaning'"]
  G -- "auto (skip review)" --> J
  G --> H["Review: report, chapter text, picks, Language ▸ Voice + sample<br/>(starts on the book's language, A-021), speed"]
  H -- "Approve (chapters, or null = all)" --> J["Job runs: Convert tab shows progress (polled every 2 s)"]
  H -- Discard --> X[Draft deleted]
  J -- Cancel --> K["Job cancelled; finished chapters kept"]
  J -- done --> L["Listen: book screen (stream or download)"]
```

## Building and publishing the APK (A-020)

```mermaid
flowchart TD
  PR["Pull request"] --> CI["ci.yml: unit tests, lint, debug APK (not kept)"]
  CI -- merged --> M["Push to master"]
  M -- "changes android/** or apk.yml" --> A["apk.yml"]
  T["Push tag vX.Y.Z"] -- "create event" --> A
  A --> K{"ANDROID_KEYSTORE_BASE64 secret set?"}
  K -- no --> F["Fail: nothing published"]
  K -- yes --> B["assembleRelease, signed with the release key;<br/>versionCode = commit count, versionName = tag"]
  B --> V["apksigner: certificate is CN=Ebook Audio"]
  V --> AR["Artifact ebook-audio-….apk (90 days)"]
  V -- "tag only" --> R["GitHub Release with ebook-audio-X.Y.Z.apk"]
  R --> P["Phone: download, install over the older version (same key, higher versionCode)"]
```
