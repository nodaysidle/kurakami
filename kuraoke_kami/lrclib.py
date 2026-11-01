"""Timed-lyrics lookup on lrclib.net (free community database). Sends only artist, title and track length."""
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://lrclib.net/api/search?"


def _call(q, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(API + urllib.parse.urlencode(q), headers={"User-Agent": "kuraoke-kami/0.1"})
            return json.load(urllib.request.urlopen(req, timeout=15))
        except (urllib.error.URLError, ValueError):  # 503 "server busy" is common: back off and retry
            time.sleep(2 * (i + 1))
    return None


def length(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout)
    except ValueError:
        return 0.0


def find(artist, title, dur):
    """-> (lrc_text, 'Artist - Title') or (None, reason). Matches must be within 8 s of the file length."""
    from .library import TRAIL
    title = TRAIL.sub("", re.sub(r"\s*[\(\[].*?[\)\]]", "", title)).strip()
    hits = _call({"artist_name": artist, "track_name": title})
    if not hits:
        hits = _call({"q": f"{artist} {title}".strip()})
    if hits is None:
        return None, "service unavailable"
    ok = [h for h in hits if h.get("syncedLyrics") and abs((h.get("duration") or 0) - dur) <= 8]
    if not ok:
        return None, "no synced match"
    best = min(ok, key=lambda h: abs(h["duration"] - dur))
    return best["syncedLyrics"], f"{best['artistName']} - {best['trackName']}"
