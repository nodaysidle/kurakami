# Kuraoke Kami: code + UI/UX audit

Date 2026-11-21 · commit `357588a` · tests passing (12 py, node lyricpage).
Method: read every source file, checked the real library (`songs/`, config, offsets), ran an isolated instance
(port 18891, fixture songs + a read-only scan of `songs/`) and screenshotted the phone remote and TV in headless Chromium.

---

## 0. Executive summary

| # | Finding | Area | Impact |
|---|---|---|---|
| 1 | Adding songs is CLI-only, and the running app never sees them until someone presses **S → Scan** | pipeline | every import needs a manual step |
| 2 | Lyrics fail silently: 6/48 MP3s have no `.lrc`, 2 of them because the file name has a typo (`Fabri Firba`, `Fedezz`). The app has no "missing lyrics" signal and no way to fix one | pipeline | guests find out mid-song |
| 3 | Bad sync is fixed by mashing `.` : saved offsets of **+29.95 s** and **+15.75 s** exist (~120 and ~63 key presses at 0.25 s). The offset is keyed by absolute path and lost on rename | pipeline | slow fix that does not last |
| 4 | Song numbers are keyed by file path, so fixing a typo in a file name gives the song a **new number** and drops its sync offset | data model | punishes cleanup |
| 5 | Any phone holding the link can Quit, remove folders, rebuild (renumber) the book and turn the remote off: there is no host/guest split | security/UX | one tap by a guest breaks the night |
| 6 | Visual language is the stock "AI neon" template: purple radial blobs, pink→cyan gradient wordmark, glows, emoji transport icons, every control the same rounded box | UI | looks generated, hierarchy is flat |
| 7 | TV idle screen is a manual (a `<pre>` key list) instead of an attract screen; the number-entry overlay draws on top of the wordmark (see screenshot notes) | UI | the first screen guests see is the weakest |

---

## Part A: adding songs + lyrics (main question)

### A1. How it works today

```text
yt-dlp / download → ~/Downloads
  → karaokeimp            (CLI: clean name, pair files, lrclib lookup, move to songs/, register folder, scan the DB)
  → app still shows old book until  S → Scan  ("a running app picks them up after S -> Scan", tools/import_songs.py:117)
  → sing → lyrics missing / out of sync → notice on stage → nudge with , . < >  (saved by absolute path in config.json)
  → missing lyrics: leave the app, rename file, run karaokelrc, rescan → song gets a NEW number
```

What the real library shows (`songs/`, 48 MP3 + 42 LRC):

- 6 songs have no lyrics: `Coez - Parla piano You Are My Lady (con California)`, `Coma_Cose - Honolulu`,
  `Fabri Fibra - Come Finirà`, `Fabri Firba - Tutto Andrà Bene` (typo), `Fedezz - Stupido Stupido` (typo),
  `FragrantProtocol98 - Station in White`.
- 0 of 42 LRCs are word-timed, so every song uses the evenly-spread line timing (`lyrics.py:275-281`).
- `Coma_Cose` keeps its underscore: `clean_stem` doesn't turn `_` into a space (`library.py:41-49`).
- `Marracash - Stupido`: the audio is 288 s and the last lyric is at 228 s, so the file carries ~30 s of video intro.
  lrclib matched on duration (within 8 s), but the timing belongs to another cut. Fixed by hand with a +29.95 s offset.

### A2. Findings (ordered by value)

**P0: the app should pick up new songs by itself**
- `__main__.py:22-46` never scans at startup; `library.scan` only runs from Settings or `karaokeimp`. Files copied in
  by hand never appear.
- Fix (small):
  1. Scan in the background at startup (numbers are stable, so this is safe).
  2. Have `import_songs.py` POST `/api/scan` to the running server. The token is in `config.json` and the port in
     `cfg["port"]`. Skip it quietly if nothing is listening.
  3. Optional: a cheap watcher thread that compares folder mtimes every ~10 s (stdlib only, no inotify dependency) and
     rescans when one changes.

**P0: make "has lyrics" a first-class fact**
- The DB has no lyrics column (`library.py:15-19`). Add `lyrics TEXT` = `word | line | embedded | cdg | none`,
  filled in `walk()`: a sibling `.lrc` exists or not; MIDI/KAR/Chorus are `embedded`; CDG is `cdg`.
- UI: a small "no lyrics" marker in the song book, a **Missing lyrics (6)** filter, and a warning on the intro screen.
- Doctor: a "songs without lyrics: 6" row.

**P0: fix lyrics without leaving the app**
- New endpoint `POST /api/lyrics_fetch {id, artist?, title?}` that runs `lrclib.find` with editable artist/title
  and writes the `.lrc`. On the phone: song row → "Find lyrics" → editable artist/title fields pre-filled from the
  file name → show the top 3 candidates (artist, track, duration, Δduration) → pick one. This covers both typo cases
  without renaming anything.
- `lrclib.find` (`lrclib.py:31-44`) returns only the closest-duration hit. Return the ranked list so the user can choose.

**P0: tap-to-sync instead of ±0.25 s**
- Add a "Sync" mode: press `T` (or tap a big button on the phone) when the singer should start the **current or next**
  line; the new offset is `pos - line.start`. One press replaces ~120. Keep `, .` for fine trimming afterwards.
- Store the result **in the `.lrc` file** as the standard `[offset:±ms]` tag, not in `config.json["offsets"]` keyed by
  absolute path (`config.py:30`, `engine.py:158-170`). The fix then survives renames, moves, re-imports and copying the
  library to another machine. `parse_lrc` (`lyrics.py:263`) should read `[offset:]` (LRC convention: a positive value
  shows lyrics earlier, so watch the sign) and keep the config-dict only as a fallback for non-LRC formats (MIDI/Chorus).
- Keep the history clean: `config.offsets` never drops entries for deleted or renamed songs.

**P1: song identity should survive renames**
- `scan()` keys rows on `path` (`library.py:110-114`). When a path disappears and a new one shows up in the same scan
  with the same size + mtime (a rename) or the same `nkey`, move the old number to it instead of handing out a new one.
  After that, fixing `Fabri Firba` → `Fabri Fibra` keeps the song's number.

**P1: lrclib matching quality**
- `lrclib.py:40`: an 8 s duration tolerance with no sanity check is how the 30 s-intro file got album timing. Add a cheap
  plausibility check: if the last lyric ends more than ~40 s before the audio ends, or the first lyric starts more than
  ~25 s after the audio starts, save the lyrics but flag them `suspect` (shown in the song book and on the intro screen
  as "lyrics may be out of sync, press T to sync").
- Try lrclib's exact `GET /api/get?artist_name&track_name&duration` first (designed for this), then `search`, then a
  **title-only** search (this one catches artist typos like `Fedezz`).
- `_call` (`lrclib.py:13-20`) retries every `URLError`, including a 404 or 400 `HTTPError`, sleeping 2+4+6+8 s.
  Retry only 429/5xx/timeouts.
- When only `plainLyrics` exist, save them anyway (e.g. `.txt`) and show them as scrolling pages without word fill.
  Better than a blank screen; today the result is just "no synced match".
- Write a header into fetched files (`[ar:] [ti:] [length:] [re:lrclib]`) so their origin is visible later.

**P1: name cleaning gaps**
- `clean_stem`: turn `_` into a space; move `ft. / feat. / featuring …` from the title to the artist (`Everyday ft. Rod
  Stewart, Miguel, Mark Ronson` gets truncated in the song book); handle `Artist_-_Title`.
- `walk()` ignores embedded tags; `import_songs.tags()` (`:28-34`) only uses them when the file name has no " - ".
  Reading tags during scan (ffprobe, cached by mtime) would make hand-dropped files usable too.

**P2: smaller importer bugs**
- `import_songs.py:98`: CDG + MP3 pairs trigger an lrclib lookup and write an `.lrc` that the player never uses
  (CDG lyrics come from graphics, `player.py:177-180`). Skip lyrics when the group has a `.cdg`.
- `import_songs.py:92`: "already in library" only compares the target file name. A second download of the same song
  with a different name is imported again; compare `library.norm(title, artist)` against the DB.
- `import_songs.py:114`: `library.query(limit=1000)` misses new songs once the book is larger than 1000.
- `fetch_lrc.py:10-12`: defaults to the repo's `songs/` instead of the configured folders and only looks at AUDIO
  (videos are skipped, although `import_songs` handles them).
- `plan()` pairs files by exact stem: `Song.mp3` + `Song (lyrics).lrc` are not paired.

**P2: in-app import (optional, biggest UX jump)**
- An "Inbox" in Settings: shows what `plan()` would do with `~/Downloads` (or a configured inbox folder), with
  checkboxes and an **Import** button that calls the same code. The CLI stays for power use; the dry-run table already
  exists as data.

### A3. Proposed target flow

```text
download → (karaokeimp | Settings → Inbox → Import)
  → server notified → background scan → numbers kept across renames
  → song book shows: ✓ word / ✓ line / ⚠ suspect / ✕ none     filter: "Missing lyrics"
  → missing: Find lyrics (edit artist/title, pick from candidates)  → .lrc written
  → out of sync: T on the first line  → [offset:] written into the .lrc
```

---

## Part B: other code review findings

| Sev | Where | Finding |
|---|---|---|
| High | `server.py:95-136` | No role split. A guest with the link can `quit`, `folder_del`, `scan rebuild` (renumbers the whole book), change `port` or `remote`, and add any folder on disk. Fix: the loopback/display client is the host; LAN clients get queue + transport only unless they use a second admin token. |
| High | `app.js:163`, `index.html:81` | Folder remove and Clear queue act immediately. Removing a folder deletes its rows on rescan, so re-adding it renumbers. Needs a confirmation or an undo toast. |
| Med | `server.py:41`, `app.js:214` | The remote URL and QR show on the TV even when `remote` is off (server bound to 127.0.0.1). The link cannot work. |
| Med | `server.py:41`, idle screen | The full token URL is printed on the TV in plain text (the README screenshot had to blur it). The QR alone is enough; show the host:port only. |
| Med | `app.js:58-61` | `loadSong` runs inside `poll()`; a failed lyrics/CDG fetch throws into the poll catch and shows "offline" even though the server is fine. |
| Med | `config.py:30`, `engine.py:170` | `offsets` grows forever, keyed by absolute path; moving the library drops every fix (see A2). |
| Low | `engine.py:110` | `_fail` reads `self.song` outside the lock (it can already be the next song when logged). |
| Low | `server.py:189-194` | Every 400 ms poll per client does 2 mpv IPC round-trips plus a new SQLite connection every 12th poll. Fine for 1–3 phones; consider long-poll or SSE if guests multiply. |
| Low | `library.py:140` | A text search sorts by artist, so the number column looks random (`1005` between `10006` and `10007`, see screenshot). Fine, but show artist group headers or allow "sort by number". |
| Low | engine state `intro_left` | Computed (`engine.py:197`) but never used by the UI: no intro countdown is shown. |

---

## Part C: UI/UX audit

### C1. Why it reads as "AI-sloppy"

These are the defaults that generated UIs land on. Each one alone is fine; together they look like a template:

1. **Palette**: near-black purple `#0b0620` + hot pink `#ff3d9a` + cyan `#29e0ff` (`style.css:2-3`). Neon synthwave by default.
2. **Background blobs**: two radial gradients drifting on a 30 s infinite animation (`style.css:21-23`). They add
   nothing, compete with lyrics, animate `background-position` (repaints the whole TV every frame) and ignore
   `prefers-reduced-motion`.
3. **Gradient wordmark** with wide tracking, `KURAOKE KAMI` pink→cyan (`style.css:41`), plus a **pink glow** on the
   intro title (`:38`) and a cyan glow on the count-in dots (`:33`). Glow is used instead of hierarchy.
4. **Emoji as icons**: `⟲ ⏯ ⏭ ＋ ⤒ ✕` (`index.html:48-50`, `app.js:113-114,185-186`). On the phone `⏯ ⏭` render as
   blue emoji tiles and `⟲` as a stray glyph (see the remote screenshot). This is the most "unfinished" signal in the app.
5. **One button style for everything**: same fill, 1px border, 10px radius, 44px min (`style.css:10`). Reserve (primary),
   `0` reset, `Quit`, a chip and a queue ✕ all look alike. No primary/secondary/destructive scale.
6. **Uppercase, letter-spaced, cyan section headers** (`style.css:90`): "LANGUAGE / COUNTRY FILTERS (NONE SELECTED =
   SHOW ALL)" is a sentence in all caps.
7. **Three accent colours on one screen** (intro: cyan number, pink-glow title, cyan up-next, lavender artist).
   Nothing is clearly the most important.
8. **Copy formatting**: `Melody: OFF` / `Chorus: ON` with shouted states, `·` and `—` separators mixed in the same
   label (`app.js:30`), `No.` prefix repeated everywhere.

### C2. Surface by surface

**TV: idle (the first thing guests see)**
- It is a manual: a 10-line `<pre>` of key bindings sits centred (`index.html:26`). The QR, the one thing a guest
  needs, is small (14vh) and pushed to the bottom edge.
- The number-entry badge (`#entry`, `style.css:49`) is placed absolutely at top-left and **overlaps the wordmark**
  ("No. 100" over "KU…", seen in the test screenshot).
- Typing a number gives no preview of the song: you learn what you reserved only after Enter.
  The server already supports number-prefix lookup (`library.py:129-130`).
- The hint wraps with a one-word orphan ("…the song / book"): add `text-wrap: balance`.
- Better attract screen: left = big number slot ("Type a song number", live title preview as you type),
  right = big QR "Scan to pick songs", bottom = the queue (next 3). Key help only on `H`.

**TV: intro**
- Good idea, weak execution: shows no countdown although `intro_left` exists; "Up next" is the same weight as the
  artist. Add a thin progress bar for the intro and, if added, the singer name (karaoke queues are about **who** sings).

**TV: lyrics**
- The basics are right (two lines, word fill, count-in dots). Fix:
  - The outline `-webkit-text-stroke: .02em #000a` (`style.css:32`) is too thin for video/CDG backgrounds; use a
    proper 0.06–0.08em dark stroke (classic karaoke look) and drop the drop-shadow filter (expensive on 120px text).
  - The HUD (`app.js:212-213`) always prints `Key 0 · Tempo 100% · Melody OFF · Chorus ON`. Show values only when they
    differ from default, and fade the HUD out after a few seconds.
  - No song progress or time left on stage.
  - The pink fill on near-black purple is the weakest contrast pair on screen; pick a fill colour by checking it against
    both the plain background and the video-dim overlay.

**Phone remote: Sing tab**
- Emoji transport (above). Use inline SVG icons (e.g. Lucide) with `aria-label`.
- The Lyrics sync row has a fake `±2 s` output between `−2/+2` buttons (`index.html:60`). Replace it with one
  **Tap to sync** button plus a fine stepper.
- Each stepper has a second reset button (`0`, `100`) with no label. Make the value itself tappable to reset.
- Melody/Chorus are text toggles that wrap ("Melody:\nOFF"); use switch rows. With no song, Chorus shows "ON" in
  disabled grey, so the state is unclear.
- Song number + Reserve sit at the bottom of the Sing tab. On a phone, picking songs is the main job, so the Songs tab
  should be the default and transport a compact sticky "now playing" bar.
- No `touch-action: manipulation`: fast double taps on `+` (key, volume) trigger double-tap zoom on mobile.
- No `<meta name="theme-color">` / `color-scheme: dark`, so the phone browser chrome stays white.

**Phone remote: Songs tab**
- Each row has `＋` and `⤒` icon buttons (cryptic, 44px each) and a raw `AUDIO`/`CHORUS` kind tag that means nothing
  to a guest. Make the whole row tappable → bottom sheet: *Add to queue* / *Sing next* / *Find lyrics*.
  Show a lyrics badge instead of the file kind.
- Language chips `en` `it` are raw codes; show names (`Intl.DisplayNames`).
- Titles truncate early because of `ft. …` in the title (fix in A2).

**Phone remote: Settings**
- **Quit** sits in "General" between Intro and SoundFont (`index.html:90`): a destructive button in the middle of a form.
- **Rebuild database (renumber)** sits next to **Scan**, same size, guarded by a native `confirm()` (`app.js:294`).
  Renumbering invalidates every printed song number. Move it under an "Advanced" section, with a typed confirmation.
- Add-folder form layout is broken on phones: the Country input stretches to two rows high and "Language" is truncated
  to "Languag" (seen in the test screenshot). The start number defaults to `1` while the docs say `10000`.
- Settings mixes guest prefs (UI language) with host admin (folders, SoundFont path, port, diagnostics). Split into
  **Host** (only on the TV/loopback) and hide it on guest phones (see B, role split).
- "Allow phones… (restart to apply)" can be unticked from a phone, which then locks every phone out.

### C3. Web Interface Guidelines checks (`file:line`)

```text
web/index.html:5   - no theme-color meta; no color-scheme: dark
web/index.html:42  - ✕ close button: icon-only, title but no aria-label
web/index.html:48-50 - ⟲ ⏯ ⏭ icon-only buttons, no aria-label; emoji glyphs render inconsistently
web/index.html:53-62 - <label> elements not tied to any control (no for=, no wrapping)
web/index.html:69  - #numin: no label, no autocomplete="off", no enterkeyhint="go"
web/index.html:73  - #q search: no label (placeholder only)
web/index.html:27  - #qr alt="" but it is meaningful ("QR code for the phone remote")
web/index.html:130 - #toast: no aria-live="polite" / role="status"
web/style.css:21-23 - infinite background animation; animates background-position; no prefers-reduced-motion
web/style.css:28   - transition on opacity ok; filter: drop-shadow on 120px text is costly per frame
web/style.css:10-11 - hover only changes border colour; no :focus-visible style (focus barely visible on dark)
web/style.css:57   - offline indicator 12px red text in a corner: too small to notice
web/style.css      - no touch-action: manipulation; no overscroll-behavior: contain on #app main
web/style.css:42   - idle hint needs text-wrap: balance
web/app.js:113,114,163,185,186 - generated icon buttons use title only; add aria-label
web/app.js:294     - native confirm() for destructive action in a kiosk window
web/app.js:163     - folder remove: destructive, no confirm/undo
web/app.js:30      - mixed separators "·" and "—"
web/app.js:183     - raw language codes shown; use Intl.DisplayNames
web/app.js:276     - active tab not in URL (?tab=); phone reload resets to Sing
web/i18n.js:17     - key help as a preformatted string; render as a <dl>/<table> so it can be styled and translated per row
```

### C4. Suggested visual direction (concrete, not more neon)

- **Stage = black, lyrics = hero.** Flat `#0a0a0a` (or a very slow, dim, single-colour vignette that respects reduced
  motion). No blobs or glows. Unsung text white with a thick dark stroke; sung fill in **one** warm accent
  (e.g. amber `#ffb000` or a saturated coral). Everything else is grey type at 60% opacity.
- **One accent, used only for "your action / current state"**: the active tab, the primary button, the sung fill,
  the current queue item.
- **Type does the hierarchy**: a condensed display face for numbers and titles (song numbers are the core
  interaction: make them huge and tabular), and a plain sans for the rest. Sentence case, no tracking on body headings.
- **Real icons** (inline SVG set, 24px, 1.75 stroke), with labels where space allows.
- **Three button tiers**: primary (filled accent), secondary (subtle fill, no border), destructive (text-red, only in
  Host/Advanced).
- **TV layout grid**: safe margins of 5vw, the bottom strip reserved for the queue ticker, the top-right for transient
  status (key/tempo changes as a 2 s toast, not a permanent HUD).

---

## Suggested order of work

1. Auto-scan on startup + importer notifies the running app (A2 P0, small).
2. `lyrics` column + "missing lyrics" badge/filter + doctor row (A2 P0).
3. Tap-to-sync + `[offset:]` stored in the `.lrc` (A2 P0).
4. Host/guest split; move Quit/Rebuild/folders to Host (B High).
5. In-app "Find lyrics" with candidate picker (A2 P0).
6. Visual pass: icons, palette, button tiers, attract screen with live number preview (C).
7. Rename-stable numbers, lrclib plausibility check, name-cleaning fixes (A2 P1).
