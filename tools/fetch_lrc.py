#!/usr/bin/env python3
"""Fetch timed lyrics (.lrc) for audio files that have none.   python3 tools/fetch_lrc.py songs/"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kuraoke_kami import lrclib  # noqa: E402
from kuraoke_kami.library import AUDIO, split_name  # noqa: E402

for f in sorted(Path(sys.argv[1]).expanduser().rglob("*")):
    if f.suffix.lower() in AUDIO and not f.with_suffix(".lrc").exists():
        title, artist = split_name(f.stem)
        text, info = lrclib.find(artist, title, lrclib.length(f))
        print(f"{f.name}: {'saved (' + info + ')' if text else info}")
        if text:
            f.with_suffix(".lrc").write_text(text, encoding="utf-8")
