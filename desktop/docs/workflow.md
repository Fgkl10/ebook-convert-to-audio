# Desktop component: workflows

## 1. Convert a book (`build_book`)

Used by both the CLI and the server worker.

```mermaid
flowchart TD
    A([source file]) --> B["parse.load_book()<br/>EPUB / PDF / TXT → Book"]
    B --> B1{any chapter<br/>≥ 40 chars?}
    B1 -- no --> X1([ValueError: no readable text])
    B1 -- yes --> C["make_book_id()<br/>slug + sha1(file)[:8]"]
    C --> D["plan_chapters()<br/>segment.split_text per chapter"]
    D --> E["count total sentences<br/>report progress 0/total"]
    E --> F{tts passed in?}
    F -- no --> F1["load KokoroTTS(voice, speed)"]
    F -- yes --> G
    F1 --> G["wrap in CachedSynth<br/>cache/&lt;book_id&gt;/"]
    G --> H["write cover file (if any)"]
    H --> I{next chapter?}
    I -- yes --> J["assemble_chapter()"]
    J --> K["encode_m4a() via ffmpeg<br/>→ chNNN.m4a (tmp then rename)"]
    K --> L["append chapter to manifest<br/>write book.json atomically<br/>complete=false"]
    L --> I
    I -- no --> M["complete=true<br/>write book.json"]
    M --> N["delete cache/&lt;book_id&gt;/"]
    N --> O([library/&lt;book_id&gt;/])
```

### 1a. Stitching a chapter (`assemble_chapter`)

```mermaid
flowchart TD
    S([paragraphs → sentences]) --> L0["pieces = [300 ms silence]<br/>pos = lead length"]
    L0 --> N{next sentence?}
    N -- yes --> C{"cache hit?<br/>sha1(voice|speed|text)"}
    C -- yes --> R["np.load(.npy)"]
    C -- no --> T["KokoroTTS.synth(text)<br/>np.save(.npy)"]
    R --> ST
    T --> ST["record start_ms = pos<br/>append audio, pos += len"]
    ST --> G{last sentence<br/>of paragraph?}
    G -- yes --> PG["append 600 ms gap"]
    G -- no --> SG["append 250 ms gap"]
    PG --> N
    SG --> N
    N -- no --> E["end_ms[k] = start_ms[k+1]<br/>last end_ms = total"]
    E --> O([chapter audio, sentences])
```

### 1b. Resume after interruption
If the process dies mid-book, the next run of the same file (same `book_id`) re-plans everything.
Sentences already in `cache/<book_id>/` load from disk instead of running TTS again, so only the
missing sentences cost GPU time. The m4a files and `book.json` are rewritten from scratch.

## 2. Convert through the server

```mermaid
sequenceDiagram
    actor U as User (browser)
    participant UI as index.html
    participant API as server.py
    participant Q as Jobs queue + worker
    participant B as build_book

    U->>UI: pick file, voice, speed → Convert
    UI->>API: POST /api/convert (multipart)
    API->>API: validate voice, 0.5≤speed≤2, ext ∈ {epub,pdf,txt}
    API->>API: save to uploads/
    API->>Q: submit(job) → status=queued
    API-->>UI: {job_id}
    loop every 2 s
        UI->>API: GET /api/jobs
        API-->>UI: job list (status, done/total, message)
        UI->>API: GET /api/books (when job signature changes)
    end
    Q->>Q: take next job → status=running
    Q->>Q: _get_tts(voice, speed) (reuse model if same language)
    Q->>B: build_book(path, LIBRARY, ..., progress, tts)
    B-->>Q: progress(done, total, msg)
    B-->>Q: out_dir
    Q->>Q: status=done, book_id  (or status=error, error=msg)
```

## 3. Listen with sentence sync (web player)

```mermaid
flowchart TD
    A([click a book]) --> B["GET /api/books/{id}<br/>→ book.json"]
    B --> C["render chapter list"]
    C --> D["loadChapter(i)<br/>render one span per sentence,<br/>grouped into &lt;p&gt; by p"]
    D --> E["audio.src = /files/chNNN.m4a"]
    E --> F["requestAnimationFrame loop"]
    F --> G["i = binary search:<br/>last sentence with start_ms ≤ currentTime"]
    G --> H{i changed?}
    H -- yes --> I["move highlight to span i<br/>scroll into view unless the user<br/>scrolled in the last 4 s"]
    H -- no --> F
    I --> F
    D --> J["click span → currentTime = start_ms; play"]
    E --> K["on ended → loadChapter(i+1) and play"]
```

## 4. Server startup and discovery

```mermaid
sequenceDiagram
    participant M as server.main()
    participant Z as zeroconf
    participant V as uvicorn
    participant P as Phone

    M->>M: create library/ if missing
    M->>Z: register _ebookaudio._tcp.local. (LAN IP, port, path=/api)
    Note over M,Z: on failure: print a hint and keep running without mDNS
    M->>V: run on 0.0.0.0:port
    P->>Z: browse _ebookaudio._tcp (M4+)
    P->>V: GET /api/books …
    Note over P,V: or scan the QR code from GET /api/info shown in the web UI
    V-->>M: shutdown
    M->>Z: unregister + close
```
