"""Health check: `kuraoke-kami --doctor`, or Settings -> Diagnostics. Prints what is wrong and how to fix it."""
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from . import config, library, log
from .player import find_soundfont

OK, BAD, WARN = "ok", "FAIL", "warn"


def _first_line(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return (r.stdout or r.stderr).strip().splitlines()[0][:70]
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


def checks(cfg, engine=None):
    out = []
    add = lambda st, name, detail="": out.append((st, name, detail))
    add(OK, "python", sys.version.split()[0])
    for tool, flag in (("mpv", "--version"), ("ffmpeg", "-version"), ("ffprobe", "-version"), ("fluidsynth", "--version")):
        add(OK if shutil.which(tool) else BAD, tool, _first_line([tool, flag]) if shutil.which(tool) else f"missing: sudo pacman -S {tool}")
    add(OK if shutil.which("qrencode") else WARN, "qrencode", "" if shutil.which("qrencode") else "optional (QR code on the TV): sudo pacman -S qrencode")
    try:
        add(OK, "SoundFont (MIDI)", find_soundfont(cfg))
    except RuntimeError as e:
        add(WARN, "SoundFont (MIDI)", str(e))
    browser = shutil.which("omarchy-launch-webapp") or shutil.which("helium-browser") or shutil.which("chromium")
    add(OK if browser else BAD, "app window launcher", browser or "need omarchy-launch-webapp or a Chromium-based browser")
    add(OK if shutil.which("hyprctl") else WARN, "hyprctl", "" if shutil.which("hyprctl") else "fullscreen / close from the remote need Hyprland")
    # audio
    pa = _first_line(["pactl", "info"]) if shutil.which("pactl") else ""
    add(OK if pa else WARN, "audio server", _first_line(["sh", "-c", "pactl info | grep 'Server Name'"]) or "pactl not answering")
    # library
    try:
        f = library.facets()
        add(OK if f["total"] else WARN, "song book", f"{f['total']} songs" if f["total"] else "empty: Settings -> add a folder -> Scan")
    except Exception as e:
        add(BAD, "song book", f"database error: {e}")
    for fo in cfg["folders"]:
        ok = os.path.isdir(fo["path"])
        add(OK if ok else BAD, "folder", f"{fo['path']} (start {fo.get('start')})" if ok else f"{fo['path']} does not exist")
    # server
    port = cfg["port"]
    if engine is not None:
        s = engine.state()
        add(OK, "server", f"running on port {port}: {s['phase']}, {len(s['queue'])} queued")
    else:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            up = sock.connect_ex(("127.0.0.1", port)) == 0
        add(OK if up else WARN, "server", f"answering on port {port}" if up else f"not running (it starts when you open Kuraoke Kami)")
    ufw = _first_line(["systemctl", "is-active", "ufw"]) if shutil.which("systemctl") else ""
    if cfg["remote"] and ufw == "active":
        add(WARN, "firewall", f"ufw is active: phones need `sudo ufw allow {port}/tcp` (ignore if you already did)")
    # leftovers
    run = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    stale = [p.name for p in Path(run).glob("kuraoke-kami-mpv-*.sock") if not Path("/proc", p.name.split("-")[-1].split(".")[0]).exists()]
    add(WARN if stale else OK, "stale mpv sockets", ", ".join(stale) if stale else "none")
    errs = log.tail(12, only_errors=True)
    add(WARN if errs else OK, "recent errors", f"see {config.LOG_FILE}" if errs else "none in the log")
    return out, errs


def report(cfg, engine=None):
    rows, errs = checks(cfg, engine)
    mark = {OK: "  ok ", BAD: " FAIL", WARN: " warn"}
    text = [f"{mark[st]}  {name:<20} {detail}" for st, name, detail in rows]
    if errs:
        text += ["", "last errors:"] + ["  " + e for e in errs]
    text += ["", f"log: {config.LOG_FILE}"]
    return "\n".join(text)
