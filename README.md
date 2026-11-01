# Kuraoke Kami

A free, offline home karaoke machine for Arch / Omarchy (Hyprland, Wayland). Drop in the song files you own,
scan the folders, and sing: big word-by-word lyrics, an intro screen, a reservation queue, live key / tempo /
melody / chorus controls, English + Tagalog UI, and a phone remote on your Wi-Fi.

## How it works

```
 TV window (Chromium app window)  <──HTTP──>  kuraoke_kami (Python, stdlib only)  ──IPC──>  mpv   (audio, key, tempo)
 phone remote (same web app)      <──HTTP──>        │                                   ──────>  ffmpeg / fluidsynth (stems, MIDI)
                                                    └── SQLite song book + JSON preferences
```

Everything is local. No accounts, no internet at runtime.

## Install

```bash
sudo pacman -S mpv ffmpeg fluidsynth soundfont-fluid qrencode    # soundfont-fluid: needed for MIDI/KAR; qrencode: optional QR on the TV
./install.sh                                                      # links `kuraoke-kami` into ~/.local/bin + an app-launcher entry
kuraoke-kami
```

Needs a Chromium-based browser for the app window (Omarchy default; Helium and Chromium both work).
`omarchy-launch-webapp` is used when present, so the window tiles like any other Hyprland window.
Press **F** (or the Fullscreen button on the remote) to make it fullscreen.

## First run

1. Press **S** → *Song folders* → enter a folder path, a **start number** (e.g. `10000`), and optional language / country labels
   (`tl` / `PH`, `en` / `US`...) → *Add folder & scan*. Use a different start number per folder to get number "blocks".
2. Numbers are stored per file, so rescans never renumber. *Rebuild database* wipes the book and renumbers from the start numbers.
3. Type a song number on the keyboard + **Enter** (like a real machine), or browse with **/**, or use the phone.

Try it without your own files: `python3 tests/fixtures.py ~/karaoke-demo` (needs ffmpeg) makes one demo song of every format.

## Supported files

| Type | What to drop in | Lyrics |
|------|-----------------|--------|
| MIDI / KAR | `.mid` `.midi` `.kar` | lyric events or KAR text events, per-word timing |
| MP3 (and wav/flac/ogg/m4a/opus) | `Artist - Title.mp3` | optional `Artist - Title.lrc` next to it (plain or word-timed "enhanced" LRC) |
| MP4 (and mkv/webm/m4v, H.264) | video with burned-in lyrics | optional `.lrc`; a 2nd audio track is treated as the guide vocal |
| CDG | `.cdg` + same-name `.mp3`/`.wav`/… | drawn from the CDG graphics |
| Chorus | a Clone Hero song folder: `song.ini` + `notes.mid` or `notes.chart` + audio | `PART VOCALS` lyrics with phrase breaks |

File names `Artist - Title` (optionally prefixed by a disc code like `SC1234-05 - `) give artist and title.

**"Chorus" interpretation:** I read it as the Clone Hero song format (the "Chorus" repository). The *chorus* control is then
the backing-vocal layer, and *melody* is the lead-vocal / guide layer. They are real separate tracks, so they can be switched on the fly:

* Chorus folders: `vocals.*` = melody, `vocals_1.*` `vocals_2.*` `harmony*` `backing*` = chorus, everything else = backing band.
* MIDI: tracks named like *melody / vocal / voice* = melody, *chorus / backing / harmony / choir* = chorus.
* MP4: audio track 2 = melody guide.
* If a song has no such layer the button is greyed out (MP3/CDG normally have none).

## Adding downloaded songs (names + lyrics + folder, automatically)

```bash
python3 tools/import_songs.py ~/Downloads             # shows the plan, asks, then moves into ./songs
python3 tools/import_songs.py ~/Downloads --dry-run   # plan only
```
It renames to `Artist - Title.ext` (drops "(Official Video)", video ids, ALL CAPS), keeps CDG+audio pairs and Chorus folders together,
fetches **timed lyrics** from [lrclib.net](https://lrclib.net) (a free community database; only artist, title and length are sent),
skips anything already in the library, registers the folder in the app and rescans. Files it can't name are listed so you can rename them.
`python3 tools/fetch_lrc.py songs/` fetches lyrics only. If lrclib has no match you get no lyrics for that song: the app still plays it.
Google lyrics are plain text without timing, so they can't be used as-is.

## Controls

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| `0-9` `Enter` | reserve by number | `+` / `-` | key up / down (±12 semitones) |
| `Space` | pause / skip intro | `[` / `]` | tempo slower / faster (50–150 %) |
| `N` | next song | `M` / `C` | melody / chorus on/off |
| `R` | restart | `↑` / `↓` | volume |
| `/` | song book | `Q` `S` | queue / settings |
| `F` | fullscreen | `Tab` `Esc` | menu / close |

Key and tempo reset for every song; melody, chorus and volume are remembered.

## Settings (all remembered in `~/.config/kuraoke-kami/config.json`)

Language (English / Tagalog), folders with start numbers and language/country labels, language and country filters,
duplicate filter (same artist + title: keeps the best format: MP4 > CDG > Chorus > MIDI > MP3), intro length, SoundFont path,
remote on/off. Song book: `~/.local/share/kuraoke-kami/library.db`. Rendered MIDI/stem cache: `~/.cache/kuraoke-kami/` (safe to delete).

## Phone remote

The server listens on your LAN (port 8890). The TV idle screen and *Settings → Remote control* show a link with an access token
(`http://192.168.x.x:8890/?t=…`) plus a QR code. Open it on a phone on the same Wi-Fi: same app, remote layout.
Every request needs the token; keep the link private. To turn LAN access off, untick it in Settings and restart.

Omarchy ships a firewall that blocks incoming connections. If the phone can't connect:

```bash
sudo ufw allow 8890/tcp
```

## Develop

```bash
node tests/test_lyricpage.js                 # lyric paging
python3 -m unittest discover -s tests -v    # parsers, numbering, filters, dedupe, mixer graph (no ffmpeg/mpv needed)
```

`kuraoke_kami/`: `lyrics.py` (MIDI/KAR/Chorus/LRC parsing) · `library.py` (scan, numbering, search) · `player.py` (mpv IPC, stems) ·
`engine.py` (queue and live controls) · `server.py` (HTTP + media) · `web/` (UI; `cdg.js` is the CD+G decoder).
Env `KURAOKE_MPV_OPTS` passes extra options to mpv (e.g. `--audio-device=pipewire/...`).

## Known limits

* Titles/artists come from file or folder names, not embedded tags.
* `.mpg` / `.avi` videos are skipped (browsers can't decode them). Convert: `ffmpeg -i in.mpg -c:v libx264 -pix_fmt yuv420p -c:a aac out.mp4`.
* Closing the window does not stop the server (it keeps the phone remote alive). Stop it with `pkill -f 'kuraoke_kami'`.
* `.sng` and zipped CDG (`.zip`) are not read; unpack them first.
* Chorus word highlighting is capped at 3 s per word (note lengths aren't read).
* CDG fine-scroll offsets are ignored; whole-tile scrolls work.
