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
- `lyrics saved (... (untimed))`: only plain lyrics were found; the app spread them over the track by guesswork.
- `lyrics saved (... (suspect))`: lyrics were saved, but the last line ends far from the end of the file, so the timing
  is probably from another cut of the song. Press **T** while it plays (see "Fixing lyrics inside the app").
- `lyrics no synced match`: that song has no timed lyrics on the lyrics site. It still plays, without words.
- `lyrics service unavailable`: the lyrics site was busy. This is common. Do step 6 a few minutes later.

**Step 5. Sing.** Open Kuraoke Kami from the app menu (or run `kuraoke-kami`). The app scans when it starts and watches
your folders, and `karaokeimp` already told it to reload, so the new song is there within a few seconds. Just type the song
number, for example `10003`, and press **Enter**.

**Step 6. Missing lyrics? Fetch them again.** Run:

```fish
karaokelrc
```

(Run it from any folder. It looks in `~/dev/nodaysidle/kuraoke-kami/songs`; give another folder as an argument if you use one.
No `venv`, no `pip`: the project uses only what Python already ships with. If `karaokelrc` is not found, run `./install.sh` again and `exec fish`.)

It only tries songs that have no lyrics file yet, so it is safe to run as often as you like.
When it saves something, the open app is told to reload, so nothing needs to be pressed. Lyrics are also read when a song
starts.

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

**Or do it inside the app.** **S → Import** lists what is waiting in the inbox folder (`~/Downloads` by default), one line
per song with a checkbox. **Import** moves the picked songs into your library, fetches their lyrics and rescans. Same rules
as `karaokeimp`: names are cleaned, nothing is overwritten.

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

## If the lyrics fail: what to do

After an import, look at the line for your song. It says one of these:

| You see | What it means | What to do |
|---------|---------------|------------|
| `lyrics saved (...)` | done | nothing |
| `lyrics saved (... (untimed))` | only plain lyrics existed; line times are spread over the track by guesswork | sing it, or **Fixing lyrics inside the app** to adjust |
| `lyrics saved (... (suspect))` | saved, but the timing looks like another cut of the song | **Fixing lyrics inside the app** (`T`) |
| `lyrics service unavailable` | the lyrics site was busy (common) | **Step 1** |
| `lyrics no synced match` | no timed lyrics were found for that name and length | **Find lyrics in the app (`L`)**, else **Step 2** and **Step 3** |

A song without lyrics still plays and can be sung. You can fix the lyrics any time later; nothing is lost.

**Step 1: busy site. Wait and try again.** Wait a few minutes, then run (from any folder):

```fish
karaokelrc
```

It only tries songs that have no lyrics yet. Run it again later if it still says `service unavailable`.

**Step 2: check the name. Most "no match" cases are a name problem.** Look at the song's name in the import list
(or run `ls ~/dev/nodaysidle/kuraoke-kami/songs`). The name must be exactly `Artist - Title.mp3`. Extra words such as
`Official Video`, `HD`, `Lyrics`, `Audio`, `feat. ...` or a year make the search fail. Fix it with `mv`, then fetch again:

```fish
cd ~/dev/nodaysidle/kuraoke-kami/songs
mv "Marracash - Stupido Official Video.mp3" "Marracash - Stupido.mp3"
karaokelrc
```

(Replace the two names with yours. Keep the quotes. Use the real artist and title spelling.)
A rename **keeps the song's number**, and the open app notices the change within ten seconds, so there is nothing to press.
If the first word before ` - ` is not the artist (for example `Title - Artist.mp3`), swap them in the same way.

**Step 3: still no match? Add the lyrics file yourself.** Timed lyrics are `.lrc` files.

1. Search the web for `<artist> <title> lrc` (or search on [lrclib.net](https://lrclib.net)) and download the `.lrc` file.
2. Put it next to the song with **exactly the same name**, only the ending is `.lrc`. For example:

```fish
mv ~/Downloads/stupido.lrc ~/dev/nodaysidle/kuraoke-kami/songs/"Marracash - Stupido.lrc"
```

3. Sing the song. The lyrics are read when the song starts, so you do not have to rescan.

Check it worked: the song's lyrics should appear on the TV window while it plays. If they do not, run `karaokedoctor`.

**You only found plain lyrics (words with no times at all).** The app cannot use those: karaoke needs the time of each
line. Look for the `.lrc` version, or sing that song without lyrics on screen. (When lrclib itself has only plain lyrics,
`karaokeimp` / `karaokelrc` save them anyway with guessed line times and mark them `untimed`.)

**Skip lyrics completely.** Import with `karaokeimp --no-lyrics`. The songs just play.

---

## Fixing lyrics inside the app

The song book shows a lyrics status on every row. The **Missing lyrics** filter shows only the songs that still need
attention (`none` and `suspect`). A song that is out of sync does not need a new file, and a song with a typo in its name
does not need renaming:

| Status | What it means | Fix it with |
|--------|---------------|-------------|
| `word` | word-by-word `.lrc` | — |
| `line` | line-by-line `.lrc` (words spread across the line) | nudge, or **T** |
| `suspect` | saved but probably timed for another cut | **T** |
| `none` | no lyrics yet | **L** |
| `embedded` / `cdg` | inside the MIDI/KAR/Chorus file, or drawn by the CDG | — |

**Find lyrics without leaving the app (`L`).** Choose a song in the book (or press **L** while it plays). Artist and title are
pre-filled from the file name and you can correct them — handy when the file says `Fedezz` or `Fabri Firba`. The app asks
lrclib for the exact artist + title + length first, then does broader searches, and finally searches by title only, so a
misspelled artist still finds the song. You get a list of matches with artist, title, album, length, how far that length is
from your file, and the first lines. Pick one: it is saved next to the song as `Artist - Title.lrc`, and if a song is
playing it reloads at once. An existing `.lrc` is kept once as `.lrc.bak`, so nothing is lost. This applies to audio and
video songs; MIDI, Chorus and CDG keep their lyrics inside the file.

**Tap-to-sync (`T`): one press instead of a hundred.** Downloaded videos often have a few seconds added at the start (an
intro or a black screen), so the timed lyrics run early. While the song plays:

1. press **T** at the moment the singer starts a line you can recognise,
2. choose that line with **←** / **→**,
3. press **T** or **Enter**. The lyrics jump to where they belong.

Now trim it if needed:

- **`.`** moves the lyrics later by 0.25 s per press; **`>`** (Shift + `.`) by 2 s,
- **`,`** moves them earlier by 0.25 s per press; **`<`** (Shift + `,`) by 2 s,

and the current value pops up on screen. The value is stored inside the song's `.lrc` as the standard `[offset:]` tag, so
it survives a rename or a move, and you only do it once. The first nudge or tap also clears the `suspect` mark.

If a nudge cannot fix it (the words belong to a different edit of the song), do not keep pressing: press **L** and pick
another match, or delete the `.lrc` and use another one from Step 3 (do not run `karaokelrc` again for this, it would fetch
the same file):

```fish
rm ~/dev/nodaysidle/kuraoke-kami/songs/"Marracash - Stupido.lrc"
```

---

## Lyrics, in detail

Lyrics come from [lrclib.net](https://lrclib.net), a free community database of **timed** lyrics. Only the artist,
the title and the length of the song are sent. An import keeps a result only if its length is within 8 seconds of your
file, so you do not get the lyrics of a different version; the in-app **Find lyrics** (`L`) shows you the matches and lets
you choose instead. When lrclib has only plain lyrics, they are still saved: the line times are spread over the track and
the file is marked `untimed`.

Lyrics you copy from Google are plain text without times, so the app cannot use them. If lrclib has no match:

1. search the web for `<artist> <title> lrc` and download an `.lrc` file,
2. save it **next to the song with exactly the same name**: `songs/Artist - Title.lrc`,
3. sing the song. The app notices the new file by itself (a manual rescan is **S → Scan**).

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
| `,` / `.` | lyrics earlier / later (`<` `>` = 2 s steps), saved with the song |
| `T` | tap-to-sync: `←` `→` choose a line, `T` / `Enter` sets it |
| `L` | find lyrics: pick a match from lrclib |
| `↑` / `↓` | volume |
| `F` | fullscreen |
| `Q` / `S` | queue / settings |
| `Tab` | menu with big buttons |
| `H` | show or hide this key list |
| `Esc` | close |

The same list is on the idle screen. After an update of the app, press `Ctrl+R` in the karaoke window to load it.

## Closing the app

Close the karaoke window like any other window (your normal Hyprland close key), or open **S → Quit Kuraoke Kami**.
Both stop everything: the window and the music. Opening it again from the menu starts it fresh.

## When something goes wrong

Everything is logged, so nothing needs to be reproduced. Run:

```fish
karaokedoctor
```

It checks the tools (mpv, ffmpeg, fluidsynth), the SoundFont, your folders, the song book (including how many songs have no
lyrics or suspect lyrics) and the audio server, and shows the **last errors from the log** with the file and line. The same report is in the app: **S → Diagnostics → Run checks**.
Errors inside the app window are written to the same log. To see the log itself: `kuraoke-kami --logs`
(file: `~/.local/state/kuraoke-kami/kuraoke.log`, mpv's own messages in `mpv.log` next to it).
If you ask for help, paste the output of `karaokedoctor`.

## Problems

| You see | Do this |
|---------|---------|
| `karaokeimp: command not found` | run `./install.sh` again in the project folder, then `exec fish` |
| `Nothing to import.` | there are no song files at the top of that folder. Check `ls ~/Downloads`, or give the right folder: `karaokeimp ~/Downloads/karaoke` |
| a `??` line | rename that file to `Artist - Title.mp3` and run again |
| the song is imported but not in the app | the app rescans by itself within ten seconds. Still missing? press **S → Scan (keep numbers)** |
| a name came out wrong | rename the file in `songs/` by hand to `Artist - Title.ext` (and its `.lrc`). The number is kept; do not copy and delete, that makes a new song |
| `lyrics service unavailable` | the lyrics site is busy. Run step 6 again in a few minutes |
| lyrics start too early or too late | press **T** to tap-to-sync, then trim with `,` `.` `<` `>`. Wrong edit of the song? **L** to pick another match (see "Fixing lyrics inside the app") |
| MIDI songs are silent | install a SoundFont: `sudo pacman -S soundfont-fluid` |
