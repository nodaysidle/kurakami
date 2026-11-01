# karaokeimp: user guide

`karaokeimp` is the fish command that turns songs you just downloaded into karaoke songs:

1. it fixes the file name to `Artist - Title`,
2. it looks up **timed lyrics** and saves them next to the song,
3. it moves the song into your library folder `~/dev/nodaysidle/kuraoke-kami/songs`,
4. it gives the song a number in the app.

You never rename or move anything by hand.

---

## Quick start (copy these steps exactly)

**Step 0, one time only.** Set up the command:

```fish
cd ~/dev/nodaysidle/kuraoke-kami
./install.sh
exec fish
```

Check that it works: `type karaokeimp` should print `karaokeimp is a function`.

**Step 1. Download your songs** with the browser or downloader as usual. They land in `~/Downloads`.
Songs named like `Artist - Title.mp3` work best (YouTube-style names such as
`Calcutta - Milano (Official Video).mp3` are fine).

**Step 2. Look before you move.** Run:

```fish
karaokeimp --dry-run
```

Nothing is changed. You get a list of what it found and the **new** names:

```
/home/you/Downloads  ->  /home/you/dev/nodaysidle/kuraoke-kami/songs

  Calcutta - Milano   [.mp3]

Nothing changed.
```

- Names look right? Go to step 3.
- A line starting with `??` means it could not find "Artist - Title" for that file. Rename that file
  yourself (for example `Artist - Title.mp3`) and run `karaokeimp --dry-run` again.
- `Nothing to import.` means no song files are in `~/Downloads` (see "Problems").

**Step 3. Import for real.** Run:

```fish
karaokeimp
```

It shows the same list and asks:

```
Move 1 song(s)? [y/N]
```

Type `y` and press Enter. Any other answer cancels and nothing moves.

**Step 4. Read the result.**

```
  Calcutta - Milano: lyrics saved (Calcutta - Milano)

Now in the song book:
  10003  Calcutta - Milano  [audio]
```

- `10003` is the number you type in the karaoke app.
- `lyrics saved (...)`: timed lyrics were found and saved.
- `lyrics no synced match`: that song has no timed lyrics on the lyrics site. It still plays, without words.
- `lyrics service unavailable`: the lyrics site was busy. This is common. Do step 6 a few minutes later.

**Step 5. Sing.** Open Kuraoke Kami from the app menu (or run `kuraoke-kami`). In the app:

1. press **S** (Settings), then click **Scan (keep numbers)**, then press **Esc**,
2. type the song number, for example `10003`, and press **Enter**.

**Step 6. Missing lyrics? Fetch them again.** Run:

```fish
karaokelrc
```

(Run it from any folder. It looks in `~/dev/nodaysidle/kuraoke-kami/songs`; give another folder as an argument if you use one.
No `venv`, no `pip`: the project uses only what Python already ships with. If `karaokelrc` is not found, run `./install.sh` again and `exec fish`.)

It only tries songs that have no lyrics file yet, so it is safe to run as often as you like.
After it prints `saved (...)`, press **S → Scan** in the app (or just start the song, lyrics are read when a song starts).

---

## All commands

| Command | What it does |
|---------|--------------|
| `karaokeimp --dry-run` | show the plan, change nothing |
| `karaokeimp` | import from `~/Downloads`, ask first |
| `karaokeimp ~/Downloads/karaoke` | import from a different folder |
| `karaokeimp --copy` | copy instead of move (the original stays in Downloads) |
| `karaokeimp --yes` | do not ask "Move N song(s)?" (use only after a dry run) |
| `karaokeimp --no-lyrics` | do not look for lyrics |
| `karaokeimp --dest ~/Music/Karaoke-TL --lang tl --country PH` | import into another library folder, labelled Tagalog |
| `karaokeimp --help` | show every option |

Options can be combined: `karaokeimp ~/Downloads/karaoke --copy --dry-run`.

**Tip:** make a folder `~/Downloads/karaoke`, save only karaoke downloads there, and always use
`karaokeimp ~/Downloads/karaoke`. Then the script never looks at anything else.

---

## What it does to each file

| In your download folder | After the import |
|-------------------------|------------------|
| `YUNG LEAN - FOREVER YUNG (Official Video) [dQw4w9WgXcQ].mp3` | `Yung Lean - Forever Yung.mp3` + `Yung Lean - Forever Yung.lrc` (the lyrics) |
| `Song (Karaoke).mp3` and `Song (Karaoke).cdg` | both renamed the same, kept together |
| a Clone Hero / "Chorus" folder (has `song.ini`) | moved as a whole folder, named `Artist - Title` |

- It removes `(Official Video)`, `(Lyrics)`, `[video id]`, `- Topic`, characters that are not allowed in file names,
  and ALL-CAPS words. Other brackets such as `(Red Bull 64 Bars)` stay.
- If the name has no `Artist - Title`, it tries the artist and title stored inside the file. If there are none, the file is
  listed with `??` and left alone.
- It **never overwrites**: a song already in the library is reported as `skip (already in library)` and stays in Downloads.
- It only looks at the top level of the folder you give it, and ignores files that are not songs (images, `.txt`, `.zip`...).
- Supported: mp3, wav, flac, ogg, m4a, opus, mp4, mkv, webm, m4v, mid, midi, kar, cdg, and Chorus folders.
  `.mpg` and `.avi` are not supported because the app cannot show them. Convert first:
  `ffmpeg -i in.mpg -c:v libx264 -pix_fmt yuv420p -c:a aac out.mp4`

## Lyrics, in detail

Lyrics come from [lrclib.net](https://lrclib.net), a free community database of **timed** lyrics. Only the artist,
the title and the length of the song are sent. A result is used only if its length is within 8 seconds of your file,
so you never get the lyrics of a different version.

Lyrics you copy from Google are plain text without times, so the app cannot use them. If lrclib has no match:

1. search the web for `<artist> <title> lrc` and download an `.lrc` file,
2. save it **next to the song with exactly the same name**: `songs/Artist - Title.lrc`,
3. press **S → Scan** in the app.

Lyrics with one time per line are shown word by word by spreading the words across the line, so the fill moves smoothly
but the timing of single words is approximate.

## In the app: keys

Click the karaoke window once, then:

| Key | What it does |
|-----|--------------|
| `0-9` then `Enter` | sing a song by number |
| `/` | open the song book (click **＋** to reserve, **⤒** to sing next) |
| `Space` | pause, or skip the intro |
| `N` / `R` | next song / restart |
| `+` / `-` | key up / down |
| `[` / `]` | slower / faster |
| `M` / `C` | melody / chorus on or off |
| `↑` / `↓` | volume |
| `F` | fullscreen |
| `Q` / `S` | queue / settings |
| `Tab` | menu with big buttons |
| `H` | show or hide this key list |
| `Esc` | close |

The same list is on the idle screen. After an update of the app, press `Ctrl+R` in the karaoke window to load it.

## Closing the app

Close the karaoke window like any other window (your normal Hyprland close key), or open **S → Quit Kuraoke Kami**.
Both stop everything: the window, the music and the phone remote. Opening it again from the menu starts it fresh.
(If you use the phone only, started with `kuraoke-kami --no-ui`, it keeps running until you press Quit.)

## When something goes wrong

Everything is logged, so nothing needs to be reproduced. Run:

```fish
karaokedoctor
```

It checks the tools (mpv, ffmpeg, fluidsynth), the SoundFont, your folders, the song book, the firewall and the audio server,
and shows the **last errors from the log** with the file and line. The same report is in the app: **S → Diagnostics → Run checks**.
Errors inside the app window are written to the same log. To see the log itself: `kuraoke-kami --logs`
(file: `~/.local/state/kuraoke-kami/kuraoke.log`, mpv's own messages in `mpv.log` next to it).
If you ask for help, paste the output of `karaokedoctor`.

## Problems

| You see | Do this |
|---------|---------|
| `karaokeimp: command not found` | run `./install.sh` again in the project folder, then `exec fish` |
| `Nothing to import.` | there are no song files at the top of that folder. Check `ls ~/Downloads`, or give the right folder: `karaokeimp ~/Downloads/karaoke` |
| a `??` line | rename that file to `Artist - Title.mp3` and run again |
| the song is imported but not in the app | press **S → Scan (keep numbers)** in the app |
| a name came out wrong | rename the file in `songs/` by hand to `Artist - Title.ext` (and its `.lrc`), then **S → Scan**. A renamed file gets a new number |
| `lyrics service unavailable` | the lyrics site is busy. Run step 6 again in a few minutes |
| lyrics start too early or too late | the lyrics file is for another version of the song. Delete the `.lrc` and use another one (see "Lyrics, in detail") |
| MIDI songs are silent | install a SoundFont: `sudo pacman -S soundfont-fluid` |
| the phone remote does not connect | `sudo ufw allow 8890/tcp` |
