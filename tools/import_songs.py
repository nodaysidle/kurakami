#!/usr/bin/env python3
"""Turn a folder of freshly downloaded songs into a tidy karaoke library.

    python3 tools/import_songs.py ~/Downloads                  # show the plan, ask, then move
    python3 tools/import_songs.py ~/Downloads --dry-run        # show the plan only
    python3 tools/import_songs.py ~/Downloads --dest ~/Music/Karaoke-TL --lang tl --yes

For every song it: cleans the name to `Artist - Title.ext` (drops "(Official Video)", video ids, SHOUTING),
keeps CDG + audio pairs and Chorus (song.ini) folders together, fetches timed lyrics from lrclib.net when the
song has none, moves everything into the destination (default: ./songs), registers that folder in the app if
it isn't yet, and rescans so the new songs get their numbers. Existing files are never overwritten.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kuraoke_kami import config, library, lrclib  # noqa: E402
from kuraoke_kami.lyrics import parse_ini  # noqa: E402

SONG_EXT = library.AUDIO | library.VIDEO | library.MIDI | {".cdg"}


def tags(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=artist,title", "-of", "json", str(path)], capture_output=True, text=True)
    try:
        t = {k.lower(): v for k, v in json.loads(r.stdout)["format"]["tags"].items()}
        return t.get("artist"), t.get("title")
    except (KeyError, ValueError):
        return None, None


def target_name(stem, path):
    name = library.clean_stem(stem)
    if " - " in name:
        return name
    a, t = tags(path)  # no "Artist - Title" in the file name: try the embedded tags
    return library.clean_stem(f"{a} - {t}") if a and t else None


def plan(inbox):
    """-> (groups, skipped). group = {name, files:[Path], dir:bool}"""
    groups, skipped, by_stem = [], [], {}
    for p in sorted(inbox.iterdir()):
        if p.is_dir() and (p / "song.ini").exists():
            ini = parse_ini((p / "song.ini").read_text(errors="replace"))
            name = library.clean_stem(f"{ini.get('artist', '')} - {ini.get('name', '')}") if ini.get("artist") and ini.get("name") else library.clean_stem(p.name)
            groups.append({"name": name, "files": [p], "dir": True})
        elif p.is_file() and p.suffix.lower() in SONG_EXT | {".lrc"}:
            by_stem.setdefault(p.stem, []).append(p)
    for stem, files in by_stem.items():
        main = next((f for f in files if f.suffix.lower() in SONG_EXT), None)
        if not main:
            continue  # a lone .lrc
        name = target_name(stem, main)
        (groups if name else skipped).append({"name": name, "files": files, "dir": False} if name else main)
    return groups, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inbox", nargs="?", default="~/Downloads")
    ap.add_argument("--dest", default=str(ROOT / "songs"))
    ap.add_argument("--lang", default="", help="language label if this destination is new to the app (e.g. tl, en)")
    ap.add_argument("--country", default="")
    ap.add_argument("--copy", action="store_true", help="copy instead of move")
    ap.add_argument("--no-lyrics", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    a = ap.parse_args()
    inbox, dest = Path(a.inbox).expanduser().resolve(), Path(a.dest).expanduser().resolve()
    groups, skipped = plan(inbox)

    print(f"{inbox}  ->  {dest}\n")
    for g in groups:
        ext = ",".join(sorted({f.suffix.lower() for f in g["files"] if not g["dir"]})) or "folder"
        print(f"  {g['name']}   [{ext}]")
    for s in skipped:
        print(f"  ?? {s.name}   (no 'Artist - Title' in the name or tags: rename it, then run again)")
    if not groups:
        return print("Nothing to import.")
    if a.dry_run or not (a.yes or (sys.stdin.isatty() and input(f"\n{'Copy' if a.copy else 'Move'} {len(groups)} song(s)? [y/N] ").lower() == "y")):
        return print("\nNothing changed.")

    dest.mkdir(parents=True, exist_ok=True)
    done = []
    for g in groups:
        if (dest / g["name"]).exists() if g["dir"] else any((dest / f"{g['name']}{f.suffix.lower()}").exists() for f in g["files"] if f.suffix.lower() in SONG_EXT):
            print(f"skip (already in library): {g['name']}"); continue
        have_lrc = any(f.suffix.lower() == ".lrc" for f in g["files"])
        for f in g["files"]:
            out = dest / (g["name"] if g["dir"] else f"{g['name']}{f.suffix.lower()}")
            (shutil.copytree if g["dir"] and a.copy else shutil.copy2 if a.copy else shutil.move)(f, out)
            if out.suffix.lower() in library.AUDIO | library.VIDEO and not have_lrc and not a.no_lyrics:
                title, artist = library.split_name(g["name"])
                text, info = lrclib.find(artist, title, lrclib.length(out))
                if text:
                    out.with_suffix(".lrc").write_text(text, encoding="utf-8")
                print(f"  {g['name']}: lyrics {'saved (' + info + ')' if text else info}")
        done.append(g["name"])

    cfg = config.load()
    if not any(dest == Path(f["path"]) or Path(f["path"]) in dest.parents for f in cfg["folders"]):
        start = max([int(f.get("start") or 0) for f in cfg["folders"]] + [0]) // 10000 * 10000 + 10000
        cfg["folders"].append({"path": str(dest), "start": max(start, 10000), "lang": a.lang, "country": a.country})
        config.save(cfg)
        print(f"registered {dest} (start number {cfg['folders'][-1]['start']})")
    library.scan(cfg)  # numbers of existing songs are kept
    print("\nNow in the song book:")
    for r in library.query(limit=1000)[0]:
        if any(r["path"].startswith(str(dest / n)) for n in done):
            print(f"  {r['number']}  {r['artist']} - {r['title']}  [{r['kind']}]")
    print("(a running app picks them up after S -> Scan)")


main()
