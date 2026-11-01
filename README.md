<div align="center">
  <img src="docs/assets/icon.svg" width="144" alt="Kuraoke Kami icon">
  <h1>Kuraoke Kami</h1>
  <p><strong>An offline home karaoke machine for Omarchy / Hyprland.</strong></p>
  <p>Type a song number → Enter → sing. Big word-by-word lyrics, your own legally owned files, nothing leaves your machine.</p>

  <p>
    <img src="https://img.shields.io/badge/Linux-Arch%20%2F%20Omarchy%20%2F%20Hyprland-1793D1?style=flat-square&logo=arch-linux&logoColor=white" alt="Arch / Omarchy / Hyprland">
    <img src="https://img.shields.io/badge/Wayland-app%20window-151518?style=flat-square" alt="Wayland">
    <img src="https://img.shields.io/badge/Python-stdlib%20only-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python, standard library only">
    <img src="https://img.shields.io/badge/audio-mpv%20%2B%20ffmpeg%20%2B%20fluidsynth-8e8e96?style=flat-square" alt="mpv, ffmpeg, fluidsynth">
    <img src="https://img.shields.io/badge/UI-English%20%2B%20Tagalog-ff3d9a?style=flat-square" alt="English and Tagalog">
    <img src="https://img.shields.io/badge/tests-11%20py%20%2B%20node-4c8c6b?style=flat-square" alt="Tests passing">
    <img src="https://img.shields.io/badge/telemetry-none-4c8c6b?style=flat-square" alt="No telemetry">
    <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="License MIT">
    <img src="https://img.shields.io/badge/version-0.1.0-8e8e96?style=flat-square" alt="Version 0.1.0">
  </p>
</div>

<table>
  <tr>
    <td width="64%" align="center"><img src="docs/screenshots/lyrics.png" alt="Lyrics filling word by word"></td>
    <td width="36%" align="center"><img src="docs/screenshots/remote.png" alt="Phone remote"></td>
  </tr>
</table>

Linux only, shaped around Omarchy and Hyprland. A small Python server (standard library, no pip) plays the audio with
`mpv`, renders MIDI with `fluidsynth` and mixes stems with `ffmpeg`. The screen is a Chromium app window, so it tiles like
any other Hyprland window; **F** makes it fullscreen. Your phone is the remote.

## The journey

```text
Drop songs in a folder
  → scan: every file gets a stable song number
  → type 10002 + Enter (or browse, or use the phone)
  → intro screen: number, title, artist, what is up next
  → sing: lyrics fill word by word, key / tempo / melody / chorus change live
  → next song starts by itself
  → close the window: everything stops
```

| Stage | What happens |
|---|---|
| **Scan** | Folders are walked once. Numbers are stored per file, so rescans never renumber; each folder has its own start number (`10000`, `20000`...). |
| **Reserve** | By number on the keyboard, from the song book, or from a phone. Queue: add, sing next, remove. |
| **Intro** | A few seconds with the song number, title, artist and the next song. `Space` skips it. |
| **Sing** | Lyrics sit in the middle of the screen, two lines at a time, with count-in dots before the first line and after long breaks. |
| **Close** | Closing the window (or **Settings → Quit**) stops the server and mpv. |

## What’s on screen

| Surface | Role |
|---|---|
| **Stage** | The TV window: idle screen with a key cheat sheet and QR code, intro, lyrics, a small key / tempo strip, the “Up next” bar. |
| **Song book** (`/`) | Search by number, title or artist. **＋** reserves, **⤒** sings next. Language chips filter the list. |
| **Queue** (`Q`) | Reorder, remove, clear. |
| **Settings** (`S`) | Folders and start numbers, language / country filters, duplicate filter, intro length, SoundFont, remote on / off, language (English / Tagalog), Quit. |
| **Phone remote** | The same app in a phone layout: transport, key, tempo, volume, melody, chorus, number pad, song book, queue. |

<table>
  <tr>
    <td width="50%" align="center"><img src="docs/screenshots/idle.png" alt="Idle screen with key cheat sheet"></td>
    <td width="50%" align="center"><img src="docs/screenshots/intro.png" alt="Intro screen"></td>
  </tr>
</table>

## Song formats

| Type | Drop in | Lyrics |
|---|---|---|
| **MIDI / KAR** | `.mid` `.midi` `.kar` | lyric events or KAR text events, per-word timing |
| **MP3** (wav, flac, ogg, m4a, opus) | `Artist - Title.mp3` | optional `Artist - Title.lrc` next to it (plain or word-timed) |
| **MP4** (mkv, webm, m4v; H.264) | video with burned-in lyrics | optional `.lrc`; a second audio track is the guide vocal |
| **CDG** | `.cdg` + same-name audio | drawn from the CDG graphics (decoded in the browser) |
| **Chorus** | a [Clone Hero](https://wiki.clonehero.net/) song folder: `song.ini` + `notes.mid` or `notes.chart` + audio | `PART VOCALS` lyrics with phrase breaks |

File names `Artist - Title` (optionally prefixed by a disc code such as `SC1234-05 - `) give artist and title.

### Melody and chorus

These are real, separate tracks, so they switch on the fly. If a song has no such track the button is greyed out.

| Source | Melody (lead / guide) | Chorus (backing) |
|---|---|---|
| **Chorus folders** | `vocals.*` | `vocals_1.*` `vocals_2.*` `harmony*` `backing*` |
| **MIDI / KAR** | tracks named *melody, vocal, voice, vox* | tracks named *chorus, backing, harmony, choir* |
| **MP4** | audio track 2 | none |
| **MP3 / CDG** | none | none |

MIDI is rendered once per song with `fluidsynth` into three stems (cached in `~/.cache/kuraoke-kami/`), then mixed live.
Key shifting uses `rubberband`, tempo uses mpv’s own pitch-preserving speed, so the lyrics stay in sync at any tempo.

## Keyboard

Click the window once, then:

| Key | Action | Key | Action |
|---|---|---|---|
| `0-9` `Enter` | reserve by number | `+` / `-` | key up / down (±12 semitones) |
| `Space` | pause / skip intro | `[` / `]` | tempo slower / faster (50–150 %) |
| `N` | next song | `M` / `C` | melody / chorus on / off |
| `R` | restart | `↑` / `↓` | volume |
| `/` | song book | `Q` `S` | queue / settings |
| `F` | fullscreen | `Tab` `H` `Esc` | menu / key help / close |

Key and tempo reset for every song. Melody, chorus and volume are remembered.

## Phone remote

The server listens on your LAN (port 8890). The idle screen and **Settings → Remote control** show a link with an access
token (`http://192.168.x.x:8890/?t=…`) and a QR code. Open it on a phone on the same Wi-Fi.

- Every request needs the token; keep the link private.
- The server also checks the `Host` header, so a web page on the internet cannot talk to it (DNS rebinding).
- Omarchy’s firewall blocks incoming connections. Allow the port once: `sudo ufw allow 8890/tcp`.
- To keep it on this machine only, untick it in Settings and restart.

## Adding songs: `karaokeimp`

```fish
karaokeimp --dry-run     # show the plan, change nothing
karaokeimp               # ask, then move
```

Takes freshly downloaded songs and: cleans the name to `Artist - Title.ext` (drops “(Official Video)”, video ids, ALL CAPS),
keeps CDG + audio pairs and Chorus folders together, fetches **timed lyrics** from [lrclib.net](https://lrclib.net) (free,
community; only artist, title and length are sent), moves everything into `songs/`, registers the folder and rescans so
the songs get their numbers. It never overwrites. `karaokelrc` fetches lyrics again for songs that still have none. Step-by-step in **[USERGUIDE.md](USERGUIDE.md)**.

## Install

```bash
sudo pacman -S mpv ffmpeg fluidsynth soundfont-fluid qrencode   # soundfont-fluid: MIDI/KAR. qrencode: optional QR code
git clone https://github.com/nodaysidle/kurakami.git
cd kurakami
./install.sh      # `kuraoke-kami` and `karaokeimp` commands, an icon, and Apps → Kuraoke Kami in the Omarchy menu
```

Needs a Chromium-based browser for the app window (Omarchy default; Helium and Chromium both work). `omarchy-launch-webapp`
is used when it is there.

**First run:** open **Kuraoke Kami** from the menu, press `S`, add a folder with a start number (for example `10000`),
click **Scan**, then type a song number and press Enter. No songs yet? `python3 tests/fixtures.py ~/karaoke-demo` makes
one demo song of every format (needs ffmpeg).

## Where things live

| What | Where |
|---|---|
| Preferences, access token | `~/.config/kuraoke-kami/config.json` |
| Song book | `~/.local/share/kuraoke-kami/library.db` |
| Rendered MIDI / stem cache | `~/.cache/kuraoke-kami/` (safe to delete) |
| Your songs | wherever you add them (the repo’s `songs/` is git-ignored) |

## Stack

| Layer | Technology |
|---|---|
| Server | Python 3, `http.server`, `sqlite3`: standard library only |
| Audio | `mpv` over JSON IPC; live mixing via `lavfi-complex`; `rubberband` for key |
| MIDI | own SMF reader / writer; `fluidsynth` + any `.sf2` / `.sf3` SoundFont |
| Stems | `ffmpeg` (`amix`, FLAC in Matroska) |
| UI | vanilla JS and CSS, no build step; CDG decoder in `web/cdg.js`; own i18n (English, Tagalog) |
| Window | Chromium app window via `omarchy-launch-webapp`; fullscreen / close through `hyprctl` |
| Lyrics | MIDI / KAR events, Clone Hero `PART VOCALS`, `.chart` events, LRC (line or word timed) |

```text
kuraoke_kami/   lyrics.py  library.py  player.py  engine.py  server.py  lrclib.py  config.py
web/            index.html  app.js  cdg.js  lyricpage.js  i18n.js  style.css
tools/          import_songs.py (karaokeimp)  fetch_lrc.py
tests/          test_core.py  test_lyricpage.js  fixtures.py
```

## Tests

```bash
python3 -m unittest discover -s tests -v   # parsers, numbering, filters, de-duplication, mixer graph, name cleaning
node tests/test_lyricpage.js               # which lyric lines are on screen
```

Verified on Arch / Omarchy with Hyprland 0.56: every format played through the live server, key / tempo / melody / chorus
changed during playback, real MIDI rendering with FluidR3, queue and auto-advance, the unplayable-file path, window
open / close.

## Privacy

No accounts, no telemetry, no analytics. The only network call is the optional lyrics lookup in `karaokeimp` /
`fetch_lrc.py`, which sends the artist, title and track length to lrclib.net. Use it for songs you own.

## Known limits

- Titles and artists come from file or folder names, not embedded tags.
- `.mpg` / `.avi` videos are skipped (the browser cannot decode them). Convert: `ffmpeg -i in.mpg -c:v libx264 -pix_fmt yuv420p -c:a aac out.mp4`.
- `.sng` files and zipped CDG are not read; unpack them first.
- Plain (line-timed) LRC spreads each line’s words evenly, so word timing is approximate; word-timed LRC and MIDI are exact.
- Chorus word highlighting is capped at 3 s per word (note lengths are not read).
- CDG fine-scroll offsets are ignored; whole-tile scrolls work.
- Lyrics for a song come only from lrclib or from an `.lrc` you add yourself.

## License

[MIT](LICENSE). The songs and lyrics you add are yours and stay on your machine.
