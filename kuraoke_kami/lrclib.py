"""Timed-lyrics lookup on lrclib.net (free community database). Sends only artist, title and track length."""
import difflib
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from .library import TRAIL

BASE = "https://lrclib.net/api/"
UA = "kuraoke-kami/0.1"
TRIES = 3                         # attempts per query
BACKOFF = 2                       # seconds; multiplied by the attempt number
SUSPECT = "kk:suspect"            # a line the app reads: lyrics may be out of sync
UNTIMED = "kk:untimed"            # plain lyrics spread over the track by guesswork

LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
WORD = re.compile(r"<(\d+):(\d+(?:\.\d+)?)>")
BRACKETS = re.compile(r"\s*[\(\[].*?[\)\]]")


def _get(path, q, tries=TRIES):
    """-> (json | None, error | None). Retries 429, 5xx, timeouts and connection errors; other 4xx answer once (404 = no hit)."""
    url = BASE + path + "?" + urllib.parse.urlencode(q)
    for i in range(tries):
        wait = BACKOFF * (i + 1)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.load(r), None
        except urllib.error.HTTPError as e:  # a URLError/OSError, so it must come first
            if e.code == 404:
                return None, None
            if e.code != 429 and e.code < 500:
                return None, f"HTTP {e.code}"
            try:  # 429 and 503 carry Retry-After; the docs ask clients to honour it
                wait = max(wait, min(10.0, float((e.headers or {}).get("Retry-After") or 0)))
            except (TypeError, ValueError):
                pass
        except OSError:  # refused/reset connections and timeouts (URLError is an OSError)
            pass
        except ValueError:  # not JSON: retrying will not help
            return None, "bad response"
        if i + 1 < tries:
            time.sleep(wait)
    return None, "service unavailable"


def length(path):
    """Track length in seconds (0.0 when ffprobe cannot tell)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True)
        return float(r.stdout)
    except (OSError, ValueError):
        return 0.0


def _clean(name):
    return TRAIL.sub("", BRACKETS.sub("", name or "")).strip()


def _preview(lyrics):
    """First 4 non-empty text lines, without timestamps."""
    out = []
    for ln in (lyrics or "").splitlines():
        ln = WORD.sub("", LINE.sub("", ln)).strip()
        if ln:
            out.append(" ".join(ln.split()))
        if len(out) == 4:
            break
    return out


def _cand(h, dur):
    """One lrclib record -> candidate dict, or None when it has no usable lyrics / is way off in length."""
    text = h.get("syncedLyrics") or h.get("plainLyrics") or ""
    if not text.strip():
        return None
    d = h.get("duration") or 0
    delta = abs(d - dur) if dur > 0 else 0.0
    if dur > 0 and delta > 20:  # another cut of the song: its timing would be wrong
        return None
    return {"id": h.get("id"), "artist": h.get("artistName") or "", "title": h.get("trackName") or h.get("name") or "",
            "album": h.get("albumName") or "", "duration": d, "delta": delta, "synced": bool(h.get("syncedLyrics")),
            "lyrics": text, "preview": _preview(text)}


def candidates(artist, title, dur):
    """-> (ranked candidates, error). Exact /api/get first, then artist+title, free text, then title only (typo-proof)."""
    artist, title = (artist or "").strip(), _clean(title)
    if not title:
        return [], None
    secs = int(round(dur))
    queries = []
    if artist and 1 <= secs <= 3600:
        queries.append(("get", {"artist_name": artist, "track_name": title, "duration": secs}))
    if artist:
        queries += [("search", {"artist_name": artist, "track_name": title}), ("search", {"q": f"{artist} {title}"})]
    queries.append(("search", {"track_name": title}))
    seen, out, error = set(), [], None
    for path, q in queries:
        data, err = _get(path, q)
        if err:
            error = error or err
            continue
        for h in ([data] if isinstance(data, dict) else data or []):
            c = _cand(h, dur)
            if not c:
                continue
            key = c["id"] if c["id"] is not None else (c["artist"], c["title"], c["duration"])
            if key not in seen:
                seen.add(key)
                out.append(c)
    out.sort(key=lambda c: (not c["synced"], c["delta"]))
    return (out, None) if out else ([], error)


def plausible(lrc_text, dur):
    """False when the last stamped line starts after the track ends, or more than 45 s before it does."""
    if dur <= 0:
        return True
    starts = []
    for ln in lrc_text.splitlines():
        m = LINE.search(ln)
        if m:
            starts.append(int(m.group(1)) * 60 + float(m.group(2)))
        else:
            w = WORD.findall(ln)
            if w:
                starts.append(min(int(a) * 60 + float(b) for a, b in w))
    if not starts:
        return True
    last = max(starts)
    return last <= dur and dur - last <= 45


def _stamp(t):
    cs = int(round(max(0.0, t) * 100))
    return f"[{cs // 6000:02d}:{cs % 6000 / 100:05.2f}]"


def _header(c, dur):
    head = [f"[ar:{c['artist']}]", f"[ti:{c['title']}]"]
    if c.get("album"):
        head.append(f"[al:{c['album']}]")
    if dur > 0:
        head.append(f"[length:{int(dur) // 60:02d}:{int(dur) % 60:02d}]")
    head.append(f"[re:lrclib #{c['id']}]")
    return head


def to_lrc(c, dur):
    """Candidate -> .lrc text. Plain-only lyrics get spread line times between 8% and 92% of the track and are flagged."""
    head = _header(c, dur)
    if c.get("synced"):
        body = c["lyrics"].strip("\n")
        if body.strip():
            if not plausible(body, dur):
                head.append(f"[{SUSPECT}]")
            return "\n".join(head + body.splitlines()) + "\n"
    lines = [ln.strip() for ln in c["lyrics"].splitlines() if ln.strip()]
    head += [f"[{UNTIMED}]", f"[{SUSPECT}]"]
    if dur > 0:
        a, b = 0.08 * dur, 0.92 * dur
        step = (b - a) / max(1, len(lines) - 1)
        times = [a + i * step for i in range(len(lines))]
    else:  # no length: 4 s per line
        times = [4.0 * (i + 1) for i in range(len(lines))]
    return "\n".join(head + [f"{_stamp(t)} {ln}" for t, ln in zip(times, lines)]) + "\n"


def _key(s):
    return re.sub(r"[\W_]+", "", (s or "").lower())


def same_artist(a, b):
    """Loose artist match: catches typos (Fedezz / Fedez, Firba / Fibra) but not a different singer."""
    a, b = _key(a), _key(b)
    if not a or not b:
        return True   # nothing to compare against
    return a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def find(artist, title, dur):
    """-> (lrc_text, 'Artist - Title') or (None, reason). Best match within 8 s of the file length,
    by the same (or nearly the same) artist: the title-only search must not pick another singer's song."""
    cands, error = candidates(artist, title, dur)
    close = [c for c in cands if c["delta"] <= 8 and same_artist(artist, c["artist"])]
    if not close:
        return None, error or "no match"
    best = close[0]
    text = to_lrc(best, dur)
    info = f"{best['artist']} - {best['title']}"
    if f"[{UNTIMED}]" in text:
        return text, info + " (untimed)"
    if f"[{SUSPECT}]" in text:
        return text, info + " (suspect)"
    return text, info
