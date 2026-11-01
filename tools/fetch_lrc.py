#!/usr/bin/env python3
"""Fetch timed lyrics (.lrc) for audio files that have none.   karaokelrc   (or: python3 tools/fetch_lrc.py [folder])"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kuraoke_kami import lrclib  # noqa: E402
from kuraoke_kami.library import AUDIO, split_name  # noqa: E402

folder = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "songs"
for f in sorted(folder.rglob("*")):
    if f.suffix.lower() in AUDIO and not f.with_suffix(".lrc").exists():
        title, artist = split_name(f.stem)
        text, info = lrclib.find(artist, title, lrclib.length(f))
        print(f"{f.name}: {'saved (' + info + ')' if text else info}")
        if text:
            f.with_suffix(".lrc").write_text(text, encoding="utf-8")
