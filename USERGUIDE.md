# karaokeimp: user guide

`karaokeimp` takes songs you just downloaded and puts them into your karaoke library: it fixes the file names, fetches
timed lyrics, moves everything into `~/dev/nodaysidle/kuraoke-kami/songs`, and gives each song a number in the app.

## One-time setup

```fish
cd ~/dev/nodaysidle/kuraoke-kami
./install.sh
```

This creates the fish command `karaokeimp`. Open a new terminal (or run `exec fish`) and check it:

```fish
type karaokeimp
```

## Every time you download songs

1. **Put the downloads in one folder.** By default the script looks in `~/Downloads`. Use a dedicated folder
   (for example `~/Downloads/karaoke`) if that folder holds other things, see "Pick another folder" below.
2. **Look first (changes nothing):**
   ```fish
   karaokeimp --dry-run
   ```
   You see a list like:
   ```
   /home/arch/Downloads  ->  /home/arch/dev/nodaysidle/kuraoke-kami/songs

     Yung Lean - Forever Yung   [.mp3]
     Disc Girl - Cdg Song   [.cdg,.mp3]
     ?? random name.mp3   (no 'Artist - Title' in the name or tags: rename it, then run again)
   ```
   - The names on the left are the **new** names. Check they are right.
   - A line starting with `??` could not be named. Rename that file yourself to `Artist - Title.mp3`.
3. **Do it:**
   ```fish
   karaokeimp
   ```
   It repeats the list and asks `Move N song(s)? [y/N]`. Type `y` and press Enter. Anything else cancels.
4. **Read the result.** For each song it prints whether lyrics were saved:
   - `lyrics saved (Artist - Title)`: timed lyrics found.
   - `lyrics no synced match`: no timed lyrics exist on lrclib.net for that song; it will play without words (see "No lyrics" below).
   - `lyrics service unavailable`: lrclib was busy. Run `python3 tools/fetch_lrc.py songs/` again in a few minutes.

   At the end you get the song numbers, for example `10003  Yung Lean - Forever Yung  [audio]`.
5. **In the app:** press **S** → **Scan (keep numbers)**. Then type the number and press Enter to sing.

## Options

| Command | What it does |
|---------|--------------|
| `karaokeimp` | import from `~/Downloads`, ask first |
| `karaokeimp --dry-run` | show the plan, change nothing |
| `karaokeimp ~/Downloads/karaoke` | import from another folder |
| `karaokeimp --copy` | copy instead of move (originals stay) |
| `karaokeimp --yes` | skip the question (use only after a dry run) |
| `karaokeimp --no-lyrics` | don't look for lyrics |
| `karaokeimp --dest ~/Music/Karaoke-TL --lang tl` | import into another library folder, labelled Tagalog |

Options can be combined, for example `karaokeimp ~/Downloads/karaoke --copy --dry-run`.

### Pick another folder
`karaokeimp ~/Downloads/karaoke` imports only from that folder. The script only looks at the top level of the folder you give
it and ignores files that aren't songs (`.txt`, `.zip`, images...).

### A second library (for example Tagalog songs)
```fish
karaokeimp --dest ~/Music/Karaoke-TL --lang tl --country PH
```
The first time, that folder is added to the app with the language label `tl` and its own number block (20000, 30000...).
Then in the app (S → Settings) you can show or hide languages with the filters.

## What it does to each file

| In your download folder | After import |
|-------------------------|--------------|
| `YUNG LEAN - FOREVER YUNG (Official Video) [dQw4w9WgXcQ].mp3` | `Yung Lean - Forever Yung.mp3` + `Yung Lean - Forever Yung.lrc` |
| `Song (Karaoke).mp3` + `Song (Karaoke).cdg` | both renamed the same, kept together |
| a Clone Hero / Chorus folder with `song.ini` | moved as a whole folder, named `Artist - Title` |

- It removes: `(Official Video)`, `(Lyrics)`, `[video id]`, `- Topic`, characters not allowed in file names, and ALL CAPS words.
- It keeps other brackets such as `(Red Bull 64 Bars)`.
- If a file has no `Artist - Title` in its name it reads the embedded artist/title tags. If there are none, it is listed with `??` and left alone.
- It **never overwrites**: a song already in the library is reported as `skip (already in library)` and left in the download folder.
- Supported: mp3, wav, flac, ogg, m4a, opus, mp4, mkv, webm, m4v, mid, midi, kar, cdg, and Chorus folders.
  `.mpg` and `.avi` videos are not supported (the app can't show them); convert them first:
  `ffmpeg -i in.mpg -c:v libx264 -pix_fmt yuv420p -c:a aac out.mp4`.

## Lyrics

Lyrics come from [lrclib.net](https://lrclib.net), a free community database. Only the artist, title and length of the song are sent.
A lyrics file is accepted only if the song length matches yours within 8 seconds, so you don't get the wrong version.

### No lyrics for a song
Lyrics from Google are plain text without times, so they don't work. Instead:
1. Search for `"<artist> <title> lrc"`, download an `.lrc` file.
2. Save it **next to the song with exactly the same name**: `songs/Artist - Title.lrc`.
3. In the app: S → Scan.

Fetch lyrics later for songs already in the library:
```fish
python3 ~/dev/nodaysidle/kuraoke-kami/tools/fetch_lrc.py ~/dev/nodaysidle/kuraoke-kami/songs
```

## Problems

| You see | Do this |
|---------|---------|
| `karaokeimp: command not found` | run `./install.sh` again in the project folder, then open a new terminal |
| `Nothing to import.` | the folder has no songs with a name it can read, or you pointed at the wrong folder: add the folder, e.g. `karaokeimp ~/Downloads/karaoke` |
| a song is in the library but not in the app | S → Scan in the app |
| a name came out wrong | rename the file in `songs/` by hand to `Artist - Title.ext` (also rename its `.lrc`), then S → Scan. The song keeps its number only if the file path stays the same, a renamed file gets a new number |
| lyrics are slightly off | line-timed lyrics are spread over each line, so word timing is approximate; this is normal |
| the app can't play MIDI | install a SoundFont: `sudo pacman -S soundfont-fluid` |

Run `karaokeimp --help` to see all options.
