# Kuraoke Kami: user guide

Kuraoke Kami is a karaoke machine for this computer. It plays your own song files on the screen (or the TV plugged into it)
with big lyrics that fill word by word. Everything runs on this machine; the only thing that ever goes online is the
optional lyrics search.

This guide covers everything you do as a user: starting the app, picking songs, singing, adding new songs, fixing lyrics,
settings, and what to do when something goes wrong.

---

## 1. Start and stop

**Start:** open the Omarchy menu, go to **Apps → Kuraoke Kami**. (You can also run `kuraoke-kami` in a terminal.)
A window opens. Press **F** to make it fullscreen.

Click the window once so it gets your keyboard. Everything in the app works with the keyboard; the mouse works too.

**Stop:** close the window like any other window, or open **Settings (S) → Advanced → Quit Kuraoke Kami**.
Both stop the music and the app. Opening it again from the menu starts fresh; your songs, numbers and settings are kept.

If you start it while it is already running, it just opens the screen again.

---

## 2. The screens

| Screen | When | What you see |
|---|---|---|
| **Idle** | nothing is playing | a big box "Type a song number", how many songs you have, and what is queued next |
| **Intro** | a few seconds before each song | the song number, title, artist, a countdown bar, and a warning if the song has no lyrics or lyrics that may be out of sync |
| **Singing** | during the song | two lines of lyrics in the middle; sung words turn amber. At the bottom: a progress bar, time played / time left, restart and pause buttons, and "Up next" |
| **Error** | a file can't play | the reason, and "Skipping in 5 s"; then the next song starts |

Before the first line, and after a long instrumental part, amber dots count you in.

When you change key, tempo, melody or chorus, a small note shows top-right for two seconds.

---

## 3. Picking a song

### By number (fastest)

Every song has a number, for example `10003`. Just type the digits on the idle screen. While you type, the song that
number belongs to shows underneath, with a check mark if it has lyrics. Press **Enter** to reserve it.
**Backspace** removes a digit.

You can also type a number while another song is playing: it shows as a small box top-right, and **Enter** adds it
to the queue.

Numbers never change on their own: not when you add songs, not when you rename a file.

### From the song book

Press **/** (or **Tab**) to open the song book on the right.

- Type in the search box to search by number, title or artist.
- The chips under it filter by language (only shown if you gave your folders a language).
- **Missing lyrics (N)** shows only songs with no lyrics or lyrics that may be out of sync.
- Each row shows the number, title, artist and a lyrics mark:

| Mark | Meaning |
|---|---|
| ✓ | has timed lyrics |
| amber warning | lyrics may be out of sync: they run past the end of the song, stop before its halfway point, or have no timing (see section 6). A long instrumental ending alone is fine |
| **No lyrics** | the song plays without words; press **L** to find some |
| nothing | lyrics come from the file itself (MIDI, KAR, Clone Hero, CDG) |

With the keyboard: **↓ / ↑** move through the list, **Enter** adds the song to the queue, **Shift+Enter** makes it the
next song, **L** finds lyrics for it. With the mouse: click a row to get the same three buttons.

**Esc** closes the song book.

---

## 4. The queue

Reserved songs wait in the queue and play one after the other by themselves. Press **Q** to see it.

- **Move to top** puts a song next in line.
- **✕** removes one song.
- **Clear queue** removes everything. Changed your mind? Press **U** (or the Undo button on the note that appears) and
  the songs come back.

---

## 5. While singing

| Key | Does |
|---|---|
| **Space** | pause / play (during the intro: start the song now) |
| **N** | skip to the next song |
| **R** | start this song again |
| **+ / −** | key up / down, one semitone at a time (up to 12) |
| **[ / ]** | slower / faster (50 % to 150 %); the lyrics stay in sync |
| **M** | melody (guide vocal) on / off |
| **C** | chorus (backing vocals) on / off |
| **↑ / ↓** | volume |
| **T** | tap to sync the lyrics (section 6) |
| **, / .** | lyrics a little earlier / later (¼ second) |
| **< / >** | lyrics much earlier / later (2 seconds) |
| **L** | find lyrics for this song |
| **F** | fullscreen |
| **H** | show all keyboard shortcuts |
| **Esc** | close whatever is open |

Key and tempo go back to normal for every new song. Melody, chorus and volume are remembered.

Melody and chorus only work when the song really has those tracks (MIDI/KAR files with named tracks, Clone Hero folders,
karaoke videos with a second audio track). Otherwise the keys do nothing.

---

## 6. Fixing lyrics

### Lyrics are early or late: tap to sync

1. While the song plays, press **T**. The screen shows one lyric line big.
2. Use **← / →** to pick a line you know, ideally one that is coming up soon.
3. The moment the singer starts that line, press **T** (or **Enter**).

Done: the lyrics are moved to match. Fine-tune with **,** and **.** if needed. **Esc** cancels without changing anything.

The fix is saved inside the song's lyrics file, so it stays when you rename or move the song.

### No lyrics, or the wrong ones: find lyrics

1. Press **L** (during the intro or the song, or on a row in the song book).
2. Artist and title are filled in from the file name. Correct them if the name has a typo, then press **Search**.
3. You get a list of matches from lrclib.net (a free lyrics site), each with album, length, how far that length is from
   your file ("Δ 2 s"), whether it is timed or plain, and its first lines.
4. Pick the one that fits (same length, Δ close to 0, timed). It is saved next to the song and, if the song is playing,
   shows straight away.

Tips:
- No results? Try only the title, or check the spelling of the artist.
- Prefer **timed** matches. A **plain** match has no timing; the app spreads its lines over the song and marks it
  "may be out of sync", so press **T** once while singing.
- The old lyrics file is kept once as a backup (`.lrc.bak`) next to the song.

Some songs simply aren't on lrclib. They still play, just without words.

---

## 7. Adding new songs

### Where songs come from

Put songs you own in a song folder (yours is `~/dev/nodaysidle/kuraoke-kami/songs`). The app checks its folders every
ten seconds and adds new songs on its own; no button to press. New songs get the next free number in that folder.

File names like `Artist - Title.mp3` give the artist and title. Downloaded names are cleaned up when you import them
(below), for example:

| Downloaded as | Becomes |
|---|---|
| `Calcutta - Milano (Official Video) [dQw4w9WgXcQ].mp3` | `Calcutta - Milano.mp3` |
| `M83 'Midnight City' Official video [dX3k_QDnzHE].mp3` | `M83 - Midnight City.mp3` |
| `Artist – Title.mp3`, `Artist \| Title.mp3`, `Artist "Title".mp3` | `Artist - Title.mp3` |
| `Coma_Cose - CUORICINI.mp3` | `Coma Cose - Cuoricini.mp3` |

If the name has no artist at all, the tags inside the file are tried.

| Type | Files | Lyrics |
|---|---|---|
| Audio | `.mp3` `.flac` `.ogg` `.m4a` `.opus` `.wav` | a `.lrc` file with the same name, next to it |
| Video | `.mp4` `.mkv` `.webm` `.m4v` (H.264) | burned into the video, or a `.lrc` |
| MIDI | `.mid` `.midi` `.kar` | inside the file |
| CDG | `.cdg` plus an audio file with the same name | drawn by the CDG graphics |
| Clone Hero | a folder with `song.ini`, `notes.mid` or `notes.chart`, and audio | inside the chart |

`.mpg` and `.avi` videos are skipped; convert them first:
`ffmpeg -i in.mpg -c:v libx264 -pix_fmt yuv420p -c:a aac out.mp4`

### Easiest: import inside the app

1. Download songs as usual into `~/Downloads`.
2. In the app press **S**, scroll to **Import**, press **Check inbox**.
3. Every song found is listed and ticked, with its cleaned name and whether it already has lyrics. Untick any you don't want.
4. Press **Import selected**.

The app cleans the names, keeps CDG/audio pairs and Clone Hero folders together, looks up timed lyrics, moves the songs into
your library and gives them numbers. Nothing is ever overwritten; songs you already have are skipped.

Want a different inbox folder? Type it in **Inbox folder** (empty means `~/Downloads`).

### From the terminal: `karaokeimp`

```fish
karaokeimp --dry-run      # show what would happen, change nothing
karaokeimp                # same list, asks "Move N song(s)? [y/N]", then imports
```

| Command | Does |
|---|---|
| `karaokeimp ~/Downloads/karaoke` | import from another folder |
| `karaokeimp --copy` | copy instead of move |
| `karaokeimp --yes` | don't ask |
| `karaokeimp --no-lyrics` | skip the lyrics search |
| `karaokeimp --dest ~/Music/Karaoke-TL --lang tl --country PH` | import into another library folder with a language label |
| `karaokelrc` | look up lyrics again for every song that still has none |

The result lists each song's number and what happened with its lyrics:

| Message | Meaning |
|---|---|
| `lyrics saved (Artist - Title)` | timed lyrics found |
| `... (suspect)` | saved, but the lyrics run past the end of the file or stop before its halfway point, so they probably belong to another version; press **T** while singing |
| `... (untimed)` | only plain lyrics exist; spread over the song, press **T** once |
| `lyrics no match` | none found; try **L** in the app with a corrected name |
| `lyrics service unavailable` | lrclib is busy; run `karaokelrc` later |
| a `??` line | no artist in the name or tags (in the app: listed under "Skipped"); rename it `Artist - Title.mp3` and run again |

If the app is open, it shows the new songs by itself.

### Renaming songs

You can rename a song file (and its `.lrc`) in the folder at any time, for example to fix a typo. The song keeps its number
and its lyric timing. Rename; don't copy and delete, because a copy counts as a new song.

---

## 8. Settings (S)

| Section | What's in it |
|---|---|
| **General** | app language (English / Tagalog), how long the intro shows, hide duplicate songs (keeps the best format of each) |
| **Library** | your song folders. Add one with its path, a start number (the next free block, e.g. `20000`), and optional language / country codes for the filters. **✕** removes a folder (asks first). **Scan for new songs** forces a rescan |
| **Import** | the inbox import from section 7 |
| **Audio** | the SoundFont used for MIDI songs; empty means the installed one |
| **Diagnostics** | **Run checks**: a health report (section 9) |
| **Keyboard shortcuts** | every key |
| **Advanced** | **Rebuild database**: renumbers every song from scratch, so printed song lists stop matching. You must type `REBUILD` to use it; normally you never need it. **Quit Kuraoke Kami** |

Each folder numbers its songs from its own start number, so you can keep, say, Italian songs in `10000`s and Tagalog
songs in `20000`s.

---

## 9. When something goes wrong

| You see | Do this |
|---|---|
| a song has no words | press **L** and pick lyrics (section 6) |
| words come too early or late | press **T** and tap on a line (section 6) |
| a new song is not in the book | wait ten seconds; still missing? **S → Scan for new songs**. Check the file type is in the table in section 7 |
| "Skipping in 5 s" on a song | the file is damaged or unsupported; the message says why |
| MIDI / KAR songs are silent | install a SoundFont: `sudo pacman -S soundfont-fluid` |
| no sound at all | check the volume (**↑**) and your system audio output |
| an "Offline" pill top-right | the app's background part stopped; close the window and open it again from the menu |
| anything else | **S → Diagnostics → Run checks**, or `karaokedoctor` in a terminal |

The health check looks at the needed tools (mpv, ffmpeg, fluidsynth), the SoundFont, your folders, how many songs lack
lyrics, the audio server, and the last errors. Everything is logged in `~/.local/state/kuraoke-kami/kuraoke.log`
(`kuraoke-kami --logs` shows it). When asking for help, paste the `karaokedoctor` output.

---

## 10. Where your things are

| What | Where |
|---|---|
| your songs and their `.lrc` lyrics | your song folders (default `~/dev/nodaysidle/kuraoke-kami/songs`) |
| settings | `~/.config/kuraoke-kami/config.json` |
| the song book (numbers) | `~/.local/share/kuraoke-kami/library.db` |
| rendered MIDI audio | `~/.cache/kuraoke-kami/` (safe to delete) |
| the log | `~/.local/state/kuraoke-kami/kuraoke.log` |

Privacy: no accounts, no tracking. The lyrics search sends only the artist, title and song length to lrclib.net.
