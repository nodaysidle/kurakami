#!/usr/bin/env python3
"""Turn a folder of freshly downloaded songs into a tidy karaoke library.

    python3 tools/import_songs.py ~/Downloads                  # show the plan, ask, then move
    python3 tools/import_songs.py ~/Downloads --dry-run        # show the plan only
    python3 tools/import_songs.py ~/Downloads --dest ~/Music/Karaoke-TL --lang tl --yes

For every song it: cleans the name to `Artist - Title.ext` (drops "(Official Video)", video ids, SHOUTING),
keeps CDG + audio pairs and Chorus (song.ini) folders together, fetches timed lyrics from lrclib.net when the
song has none, moves everything into the destination (default: your first configured folder, else ./songs),
registers that folder in the app if it isn't yet, rescans and tells the running app to reload. Existing files
are never overwritten. The work itself lives in kuraoke_kami/importer.py (the app's Inbox uses the same code).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kuraoke_kami import config, importer, library  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inbox", nargs="?", default="~/Downloads")
    ap.add_argument("--dest", default="", help="destination folder (default: your first configured folder, else ./songs)")
    ap.add_argument("--lang", default="", help="language label if this destination is new to the app (e.g. tl, en)")
    ap.add_argument("--country", default="")
    ap.add_argument("--copy", action="store_true", help="copy instead of move")
    ap.add_argument("--no-lyrics", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    a = ap.parse_args()
    cfg = config.load()
    inbox = Path(a.inbox).expanduser().resolve()
    dest = Path(a.dest).expanduser().resolve() if a.dest else importer.default_dest(cfg).resolve()
    if not inbox.is_dir():
        return print(f"no such folder: {inbox}")
    groups, skipped = importer.plan(inbox)

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

    done = importer.import_groups(groups, dest, copy=a.copy, fetch_lyrics=not a.no_lyrics, cfg=cfg)
    if importer.ensure_folder(cfg, dest, a.lang, a.country):
        print(f"registered {dest} (start number {cfg['folders'][-1]['start']})")
    library.scan(cfg)  # numbers of existing songs are kept
    print("\nNow in the song book:")
    for r in library.query(limit=10000)[0]:
        if any(r["path"].startswith(str(dest / n)) for n in done):
            print(f"  {r['number']}  {r['artist']} - {r['title']}  [{r['kind']}]")
    print("the open app updates by itself" if importer.notify_running_app(cfg)
          else "(a running app picks them up after S -> Scan)")


if __name__ == "__main__":
    main()
