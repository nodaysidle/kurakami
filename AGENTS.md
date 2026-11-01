# AGENTS.md: debugging Kuraoke Kami

Start here when something is wrong. Do not ask the user to reopen or reproduce first.

1. `bin/kuraoke-kami --doctor` : environment + song book + recent errors (works with the app closed).
2. `bin/kuraoke-kami --logs` or read `~/.local/state/kuraoke-kami/kuraoke.log` (tracebacks; browser errors are `ERROR browser: ...`). mpv: `mpv.log` beside it.
3. With the app running: `GET /api/doctor`, `GET /api/state` (header `X-Token` from `~/.config/kuraoke-kami/config.json`).
4. Reproduce on an isolated instance, never on the user's: set `XDG_CONFIG_HOME XDG_DATA_HOME XDG_CACHE_HOME XDG_STATE_HOME` to a temp dir, `KURAOKE_MPV_OPTS=--ao=null`, write a config with another `port`, run `bin/kuraoke-kami --no-ui`.
   `python3 tests/fixtures.py DIR` builds a demo song of every format.
5. Tests: `python3 -m unittest discover -s tests` and `node tests/test_lyricpage.js`.

Gotchas
- The server quits ~3 s after the display window closes (page sends a beacon) and after 120 s without display polls, but never if no display was ever seen (`--no-ui`). Headless screenshots therefore end the server unless something keeps polling `/api/state?d=1`.
- Hyprland here uses the Lua dispatch API (`hyprctl dispatch 'hl.dsp.window.close({ window = "address:0x.." })'`); old `dispatch exec [rule] cmd` syntax fails.
- Never `pkill -f kuraoke` / `pkill mpv`, and never kill by process name (`awk ... /kuraoke_kami/`): that also matches the user's **running app**. Check `ss -ltn | grep :8890` before every test; start test servers with `& echo $!` and kill exactly that PID (test ports 188xx, never 8890).
- `songs/` holds the user's own files and is git-ignored. Do not commit or upload them.
- Pushing to `main` is blocked by the user's pre-push hook until they approve it.
