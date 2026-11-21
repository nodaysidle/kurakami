"""Optional speech recognition (faster-whisper in its own venv, see tools/setup_whisper.sh): time a song's lyrics from
its audio, or transcribe a song that has none. The app only starts a subprocess; it never imports faster-whisper."""
import json
import os
import subprocess
from pathlib import Path

from . import align, config, library, lrclib

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tools" / "whisper_words.py"


def python(cfg):
    p = cfg.get("whisper_python") or str(config.DATA_DIR / "whisper" / "bin" / "python")
    return os.path.expanduser(p)


def available(cfg):
    py = python(cfg)
    if not os.path.isfile(py):
        return False
    try:
        return subprocess.run([py, "-c", "import faster_whisper"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def transcribe(cfg, path, lang="auto"):
    r = subprocess.run([python(cfg), str(RUNNER), str(path), lang or "auto", cfg.get("whisper_model") or "small"],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode:
        raise RuntimeError((r.stderr.strip().splitlines() or ["speech recognition failed"])[-1])
    return json.loads(r.stdout)


def tag_lyrics(path):
    """Lyrics stored inside the audio file's tags (some downloads carry them), or ''."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)],
                           capture_output=True, text=True, timeout=20)
        tags = {k.lower(): v for k, v in json.loads(r.stdout).get("format", {}).get("tags", {}).items()}
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    return next((v for k, v in tags.items() if k in ("lyrics", "unsyncedlyrics") or k.startswith("lyrics-")), "")


def time_song(cfg, song, lang="auto"):
    """Write word-timed lyrics for one audio/video song. -> (lrc_text, (what, share)): what is
    'timed' (known words, new times), 'transcribed' (no words known: the recogniser's words), with the match share."""
    path = song["path"]
    old = library.lrc_for(path)
    old_text = old.read_text(errors="replace") if old else ""
    lines = align.text_lines(old_text) or align.text_lines(tag_lyrics(path))
    res = transcribe(cfg, path, lang)
    segs = res.get("segments") or []
    if not any(s.get("words") for s in segs):
        raise RuntimeError("no singing recognised")
    dur = lrclib.length(path)
    head = [f"[ar:{song.get('artist') or ''}]", f"[ti:{song.get('title') or ''}]"]
    if dur:
        head.append(f"[length:{int(dur // 60):02d}:{int(dur % 60):02d}]")
    if lines:
        timed, share, _ = align.align(lines, segs)
        head.append(f"[re:timed by speech recognition ({res.get('language')}), {share:.0%} of words heard]")
        text, info = align.to_lrc(head, timed), ("timed", share)
    else:
        head.append(f"[re:transcribed by speech recognition ({res.get('language')}): words may be wrong]")
        text, info = align.transcript_lrc(head, segs), ("transcribed", 1.0)
    return text, info   # times come straight from the audio: an old [offset:] would only shift them off again
