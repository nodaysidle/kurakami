# AGENTS.md: debugging Kuraoke Kami

Start here when something is wrong. Do not ask the user to reopen or reproduce first.

**Rule from the owner:** a change is not done, and is never pushed, until the installed app was launched from the Omarchy
menu (Apps → Kuraoke Kami) on a real workspace and the changed flows were used in that window. Headless screenshots and
isolated instances are for checking along the way, not a replacement.

1. `bin/kuraoke-kami --doctor` : environment + song book + lyrics counts (none / suspect) + recent errors (works with the app closed).
2. `bin/kuraoke-kami --logs` or read `~/.local/state/kuraoke-kami/kuraoke.log` (tracebacks; browser errors are `ERROR browser: ...`). mpv: `mpv.log` beside it.
3. With the app running: `GET /api/doctor`, `GET /api/state` (header `X-Token` from `~/.config/kuraoke-kami/config.json`).
   The server binds `127.0.0.1` only and `/` answers loopback clients only: nothing outside this machine can connect.
4. Reproduce on an isolated instance, never on the user's: set `XDG_CONFIG_HOME XDG_DATA_HOME XDG_CACHE_HOME XDG_STATE_HOME` to a temp dir, `KURAOKE_MPV_OPTS=--ao=null`, write a config with another `port`, run `bin/kuraoke-kami --no-ui`.
   `python3 tests/fixtures.py DIR` builds a demo song of every format.
5. Tests: `python3 -m unittest discover -s tests` (`test_core.py`, `test_pipeline.py`, `test_align.py`: 63 tests, no mpv/ffmpeg/whisper) and `node tests/test_lyricpage.js`.
   The repo-root `package.json` (`"type": "commonjs"`) is what lets the node test load `web/lyricpage.js` as CommonJS: a
   `package.json` higher up (`~/dev/package.json`, `"type": "module"`) otherwise makes Node treat `tests/*.js` as ESM, and
   `require` fails.

Startup and lyrics
- `server.serve()` runs `app.migrate_offsets()` at startup (offsets saved in `config["offsets"]` are written into the matching `.lrc` as the standard `[offset:]` tag, then dropped from the config; entries without an `.lrc` stay as the fallback), then `app.start_scan()`. A watcher thread compares folder mtimes every 10 s and rescans; `karaokeimp` / `karaokelrc` also POST `/api/scan` to an open app. So a song added by hand appears without pressing Scan.
- `library.lyrics_status()` gives `word | line | suspect | embedded | cdg | none`; `GET /api/songs?missing=1` keeps `none` + `suspect`. `karaokedoctor` and `library.facets()["missing"]` report the same two.
- In-app lyrics: `POST /api/lyrics_search {id, artist?, title?}` returns ranked lrclib candidates (full lyrics stay in the server's memory), `POST /api/lyrics_save {id, idx}` writes `<song>.lrc` (keeping one `.lrc.bak`) and reloads a playing song; `POST /api/sync_line {line}` sets the offset from mpv's `time-pos`; `POST /api/sync {delta|value}` nudges it.
- Offsets live in the `.lrc` `[offset:N]` line (N = −ms, LRC convention: positive shows lyrics earlier). `config["offsets"]` is only the fallback for MIDI / KAR / Chorus / CDG, and `scan(renamed=...)` moves those entries when a file is renamed.
- Song identity: `scan()` matches a renamed file to its old row by identical (size, mtime), else by the same normalised name + kind, and keeps its number and id. A rewritten file (not a pure rename) gets a new number.
- Importer: `kuraoke_kami/importer.py` (`plan`, `import_groups`, `ensure_folder`, `notify_running_app`, `default_dest`) backs both `karaokeimp` and the in-app Import (`Settings → Import`): `GET /api/inbox`, `POST /api/inbox_import {names}`. It never overwrites and skips songs already in the book.

Gotchas
- The server quits ~3 s after the display window closes (page sends a beacon) and after 120 s without display polls, but never if no display was ever seen (`--no-ui`). Headless screenshots therefore end the server unless something keeps polling `/api/state?d=1`.
- Hyprland here uses the Lua dispatch API (`hyprctl dispatch 'hl.dsp.window.close({ window = "address:0x.." })'`); old `dispatch exec [rule] cmd` syntax fails.
- Never `pkill -f kuraoke` / `pkill mpv`, and never kill by process name (`awk ... /kuraoke_kami/`): that also matches the user's **running app**. Check `ss -ltn | grep :8890` before every test; start test servers with `& echo $!` and kill exactly that PID (test ports 188xx, never 8890).
- `songs/` holds the user's own files and is git-ignored. Do not commit or upload them.
- Pushing to `main` is blocked by the user's pre-push hook until they approve it.
- Speech recognition is optional and lives outside the app: `tools/setup_whisper.sh` makes a venv in
  `~/.local/share/kuraoke-kami/whisper` (or `whisper_python` in the config); `kuraoke_kami/whisper.py` runs
  `tools/whisper_words.py` there as a subprocess and `align.py` (stdlib) turns the transcript into word-timed LRC.
  Never import faster-whisper in the app. `POST /api/lyrics_time {id, lang}` runs in the background; progress is
  `timing` in `/api/state`, availability is `whisper`.
