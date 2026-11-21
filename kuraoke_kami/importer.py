"""Inbox -> library. Groups downloaded files, fetches lyrics, moves them into a folder. Used by the CLI and the app."""
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

from . import config, library, lrclib
from .lyrics import parse_ini

ROOT = Path(__file__).resolve().parent.parent
SONG_EXT = library.AUDIO | library.VIDEO | library.MIDI | {".cdg"}
LRC = ".lrc"


def tags(path):
    """Embedded (artist, title) via ffprobe; (None, None) when the file has none or ffprobe is missing."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=artist,title",
                            "-of", "json", str(path)], capture_output=True, text=True)
        t = {k.lower(): v for k, v in json.loads(r.stdout)["format"]["tags"].items()}
        return t.get("artist"), t.get("title")
    except (KeyError, ValueError, OSError):
        return None, None


def target_name(stem, path):
    """'Artist - Title' from the file name, else from the tags; None when neither says who sings it."""
    name = library.clean_stem(stem)
    if " - " in name:
        return name
    a, t = tags(path)
    return library.clean_stem(f"{a} - {t}") if a and t else None


def plan(inbox):
    """-> (groups, skipped). group = {name, files:[Path], dir:bool, has_lrc:bool, kind:'cdg'|'chorus'|'song'}"""
    groups, skipped, by_name = [], [], {}
    for p in sorted(Path(inbox).expanduser().iterdir()):
        if p.is_dir() and (p / "song.ini").exists():
            ini = parse_ini((p / "song.ini").read_text(errors="replace"))
            name = library.clean_stem(f"{ini.get('artist', '')} - {ini.get('name', '')}") if ini.get("artist") and ini.get("name") else library.clean_stem(p.name)
            has = any((p / n).exists() for n in ("notes.mid", "notes.chart"))  # lyrics are inside the chart
            groups.append({"name": name, "files": [p], "dir": True, "has_lrc": has, "kind": "chorus"})
        elif p.is_file() and p.suffix.lower() in SONG_EXT | {LRC}:
            by_name.setdefault(library.clean_stem(p.stem).lower(), []).append(p)  # also pairs 'X (lyrics).lrc'
    for files in by_name.values():
        main = [f for f in files if f.suffix.lower() in SONG_EXT]
        if not main:
            continue  # a lone .lrc
        name = target_name(main[0].stem, main[0])
        if not name:
            skipped.append(main[0])
            continue
        kind = "cdg" if any(f.suffix.lower() == ".cdg" for f in main) else "song"
        lrcs = [f for f in files if f.suffix.lower() == LRC]
        groups.append({"name": name, "files": main + lrcs, "dir": False, "has_lrc": kind == "cdg" or bool(lrcs), "kind": kind})
    return groups, skipped


def _known():
    """nkeys of the songs already in the book."""
    con = library.db()
    rows = con.execute("SELECT title, artist FROM songs").fetchall()
    con.close()
    return {library.norm(r["title"], r["artist"]) for r in rows}


def _exists(g, dest, known):
    """True when this song is already in dest or in the book under another file name."""
    if g["dir"]:
        return (dest / g["name"]).exists()
    if any(p.stem.lower() == g["name"].lower() for p in dest.iterdir()):
        return True
    key = library.norm(*library.split_name(g["name"]))
    return bool(key) and key in known


def import_groups(groups, dest, copy=False, fetch_lyrics=True, cfg=None, say=print):
    """Move (or copy) planned groups into dest. -> names imported. Never overwrites, skips what is already there."""
    dest = Path(dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    known, done = _known(), []
    for g in groups:
        name = g["name"]
        if _exists(g, dest, known):
            say(f"skip (already in library): {name}")
            continue
        wrote, have_lrc = False, g["has_lrc"]
        for f in g["files"]:
            out = dest / (name if g["dir"] else f"{name}{f.suffix.lower()}")
            if out.exists():
                say(f"skip (already in library): {out.name}")
                continue
            if g["dir"]:
                (shutil.copytree if copy else shutil.move)(f, out)
            else:
                (shutil.copy2 if copy else shutil.move)(f, out)
            wrote = True
            if (not g["dir"] and fetch_lyrics and not have_lrc and g["kind"] == "song"
                    and out.suffix.lower() in library.AUDIO | library.VIDEO):
                title, artist = library.split_name(name)
                text, info = lrclib.find(artist, title, lrclib.length(out))
                if text:
                    out.with_suffix(LRC).write_text(text, encoding="utf-8")
                    have_lrc = True  # every format of this song shares the one .lrc
                say(f"  {name}: lyrics {'saved (' + info + ')' if text else info}")
        if wrote:
            done.append(name)
            known.add(library.norm(*library.split_name(name)))
    return done


def ensure_folder(cfg, dest, lang="", country=""):
    """Register dest in cfg['folders'] (saving cfg) when no configured folder covers it. -> True when added."""
    dest = Path(dest).expanduser()
    roots = [Path(f["path"]).expanduser() for f in cfg.get("folders") or []]
    if any(dest == r or r in dest.parents for r in roots):
        return False
    start = max([int(f.get("start") or 0) for f in cfg.get("folders") or []] + [0]) // 10000 * 10000 + 10000
    cfg.setdefault("folders", []).append({"path": str(dest), "start": max(start, 10000), "lang": lang, "country": country})
    config.save(cfg)
    return True


def notify_running_app(cfg):
    """POST /api/scan to the app on 127.0.0.1. -> True when it answered; quietly False when it is not running."""
    req = urllib.request.Request(f"http://127.0.0.1:{int(cfg.get('port') or 8890)}/api/scan", data=b"{}", method="POST",
                                 headers={"X-Token": cfg.get("token", ""), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1) as r:
            return 200 <= r.status < 300
    except (OSError, ValueError):  # refused, timeout, not the app on that port
        return False


def default_dest(cfg):
    """First configured folder, else ./songs in the repo."""
    folders = cfg.get("folders") or []
    return Path(folders[0]["path"]).expanduser() if folders else ROOT / "songs"
