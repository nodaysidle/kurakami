#!/usr/bin/env python3
"""Fetch timed lyrics (.lrc) for songs that have none.   karaokelrc   (or: python3 tools/fetch_lrc.py [folder ...])"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kuraoke_kami import config, importer, library, lrclib  # noqa: E402

PLAYABLE = library.AUDIO | library.VIDEO


def main(argv):
    cfg = config.load()
    folders = ([Path(a).expanduser() for a in argv[1:]] or [Path(f["path"]).expanduser() for f in cfg["folders"]]
               or [importer.ROOT / "songs"])
    saved = 0
    for folder in folders:
        for f in sorted(folder.rglob("*")):
            if f.suffix.lower() not in PLAYABLE or library.lrc_for(f):
                continue
            if (f.parent / "song.ini").exists() or f.with_suffix(".cdg").exists():
                continue  # Chorus (embedded lyrics) and CDG (graphics) need no .lrc
            title, artist = library.split_name(f.stem)
            text, info = lrclib.find(artist, title, lrclib.length(f))
            print(f"{f.name}: {'saved (' + info + ')' if text else info}")
            if text:
                library.lrc_target(f).write_text(text, encoding="utf-8")
                library.refresh(f)
                saved += 1
    if saved and importer.notify_running_app(cfg):
        print("\nthe open app updates by itself")


if __name__ == "__main__":
    main(sys.argv)
