#!/usr/bin/env python3
"""Word-timestamped transcript of one song, as JSON on stdout. Runs inside the speech-recognition venv
(tools/setup_whisper.sh), never inside the app: the app stays standard-library only.

    whisper-venv/bin/python tools/whisper_words.py SONG [LANG|auto] [MODEL]
"""
import json
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel

path = sys.argv[1]
lang = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "auto" else None
name = sys.argv[3] if len(sys.argv) > 3 else "small"

# decode with ffmpeg ourselves: works with every format mpv plays and every PyAV version
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                     capture_output=True, check=True).stdout
audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
model = WhisperModel(name, device="cpu", compute_type="int8")
segs, info = model.transcribe(audio, language=lang, word_timestamps=True, vad_filter=False,
                              condition_on_previous_text=False, beam_size=5)
json.dump({"language": info.language,
           "segments": [{"start": s.start, "end": s.end, "text": s.text.strip(),
                         "words": [{"w": w.word, "s": w.start, "e": w.end} for w in s.words or []]} for s in segs]},
          sys.stdout, ensure_ascii=False)
