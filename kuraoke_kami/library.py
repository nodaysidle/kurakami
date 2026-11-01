"""Folder scan -> SQLite song book. Song numbers are stable per file path."""
import os
import re
import sqlite3
from pathlib import Path

from . import config
from .lyrics import parse_ini

AUDIO = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".opus"}
VIDEO = {".mp4", ".mkv", ".webm", ".m4v"}  # what Chromium can decode; .mpg/.avi would play as sound over a black screen
MIDI = {".mid", ".midi", ".kar"}
PRIO = {"video": 1, "cdg": 2, "chorus": 3, "midi": 4, "audio": 5}  # best format wins when de-duplicating

SCHEMA = """CREATE TABLE IF NOT EXISTS songs(
 id INTEGER PRIMARY KEY, number INTEGER UNIQUE, path TEXT UNIQUE, root TEXT, kind TEXT,
 title TEXT, artist TEXT, lang TEXT, country TEXT, nkey TEXT, prio INT);
CREATE INDEX IF NOT EXISTS songs_nkey ON songs(nkey);
CREATE INDEX IF NOT EXISTS songs_root ON songs(root, number)"""


def db():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_FILE, timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def norm(title, artist):
    s = re.sub(r"[\(\[].*?[\)\]]", "", f"{artist} {title}".lower())
    return re.sub(r"[^\w]+", "", s)


JUNK = re.compile(r"\s*[\(\[][^\)\]]*\b(official|video|audio|lyrics?|visuali[sz]er|hd|hq|4k|karaoke|sanremo|clip|mv)\b[^\)\]]*[\)\]]", re.I)


TRAIL = re.compile(r"\s+(official\s+(music\s+)?(video|audio|visuali[sz]er|lyric\s+video)|(lyrics?|lyric)\s+video|video\s+ufficiale|audio\s+ufficiale|videoclip)\s*$", re.I)


def clean_stem(stem):
    """'ARTIST - CUORICINI (Official Video - Sanremo 2025) [dQw4w9WgXcQ]' -> 'Artist - Cuoricini'."""
    s = re.sub(r"\s*\[[\w-]{11}\]$", "", stem)          # yt-dlp video id
    s = JUNK.sub("", s)
    s = TRAIL.sub("", s)            # "Title Official Video" without brackets
    s = re.sub(r"\s*-\s*Topic$", "", s)
    s = re.sub(r'[/\\:*?"<>|]', "", s)
    s = " ".join(s.split())
    return " - ".join(p.title() if p.isupper() and len(p) > 3 else p for p in s.split(" - "))


def split_name(stem):
    """'Artist - Title' (optionally prefixed by a disc code like 'SC1234-05 - ') -> (title, artist)."""
    parts = [p.strip() for p in stem.split(" - ")]
    if len(parts) >= 3 and len(parts[0]) <= 12 and any(c.isdigit() for c in parts[0]):
        parts = parts[1:]
    if len(parts) >= 2:
        return " - ".join(parts[1:]), parts[0]
    return stem.strip(), ""


def walk(root):
    """Yield (path, kind, title, artist) for every playable item under root."""
    for dp, dirs, files in os.walk(root):
        dirs.sort()
        low = {f.lower(): f for f in files}
        if "song.ini" in low:  # a Chorus (Clone Hero) song folder: one song, don't look inside
            dirs[:] = []
            try:
                ini = parse_ini(Path(dp, low["song.ini"]).read_text(errors="replace"))
            except OSError:
                ini = {}
            t, a = split_name(Path(dp).name)
            yield dp, "chorus", ini.get("name") or t, ini.get("artist") or a
            continue
        stems_cdg = {Path(f).stem.lower() for f in files if f.lower().endswith(".cdg")}
        for f in sorted(files):
            stem, ext = Path(f).stem, Path(f).suffix.lower()
            if ext == ".cdg":
                kind = "cdg" if any(Path(g).stem.lower() == stem.lower() and Path(g).suffix.lower() in AUDIO for g in files) else None
            elif ext in AUDIO:
                kind = None if stem.lower() in stems_cdg else "audio"
            else:
                kind = "midi" if ext in MIDI else "video" if ext in VIDEO else None
            if kind:
                t, a = split_name(stem)
                yield os.path.join(dp, f), kind, t, a


def next_number(con, root, start):
    m = con.execute("SELECT MAX(number) FROM songs WHERE root=?", (root,)).fetchone()[0]
    n = max(start, (m or start - 1) + 1)
    while con.execute("SELECT 1 FROM songs WHERE number=?", (n,)).fetchone():
        n += 1
    return n


def scan(cfg, rebuild=False, progress=None):
    """Index all folders. rebuild=True wipes the book and renumbers; otherwise numbers are kept."""
    con = db()
    if rebuild:
        con.execute("DELETE FROM songs")
    seen, count = set(), 0
    for fo in cfg["folders"]:
        root, start = fo["path"], int(fo.get("start") or 1)
        for path, kind, title, artist in walk(root):
            seen.add(path)
            vals = (root, kind, title, artist, fo.get("lang", ""), fo.get("country", ""),
                    norm(title, artist) or path, PRIO[kind])
            if con.execute("SELECT 1 FROM songs WHERE path=?", (path,)).fetchone():
                con.execute("UPDATE songs SET root=?,kind=?,title=?,artist=?,lang=?,country=?,nkey=?,prio=? WHERE path=?", vals + (path,))
            else:
                con.execute("INSERT INTO songs(number,path,root,kind,title,artist,lang,country,nkey,prio) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (next_number(con, root, start), path) + vals)
            count += 1
            if progress and count % 50 == 0:
                progress(count)
    for (p,) in con.execute("SELECT path FROM songs").fetchall():
        if p not in seen:
            con.execute("DELETE FROM songs WHERE path=?", (p,))
    con.commit()
    con.close()
    return count


def query(q="", langs=(), countries=(), dedupe=False, limit=200, offset=0):
    where, args = [], []
    q = q.strip()
    if q.isdigit():
        where.append("number LIKE ?"); args.append(q + "%")
    else:
        for w in q.lower().split():
            where.append("(lower(title) LIKE ? OR lower(artist) LIKE ?)"); args += [f"%{w}%"] * 2
    for col, vals in (("lang", langs), ("country", countries)):
        if vals:  # songs with no label are never hidden
            where.append(f"({col}='' OR {col} IN ({','.join('?' * len(vals))}))"); args += list(vals)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    inner = f"SELECT *, ROW_NUMBER() OVER (PARTITION BY nkey ORDER BY prio, number) rn FROM songs {w}" if dedupe else f"SELECT *, 1 rn FROM songs {w}"
    con = db()
    rows = con.execute(f"SELECT * FROM ({inner}) WHERE rn=1 ORDER BY {'number' if q.isdigit() else 'artist COLLATE NOCASE, title COLLATE NOCASE'} LIMIT ? OFFSET ?",
                       args + [limit + 1, offset]).fetchall()
    con.close()
    return [dict(r) for r in rows[:limit]], len(rows) > limit


def get(song_id=None, number=None):
    con = db()
    r = con.execute("SELECT * FROM songs WHERE id=?" if song_id is not None else "SELECT * FROM songs WHERE number=?",
                    (song_id if song_id is not None else number,)).fetchone()
    con.close()
    return dict(r) if r else None


def facets():
    con = db()
    out = {c: [r[0] for r in con.execute(f"SELECT DISTINCT {c} FROM songs WHERE {c}!='' ORDER BY 1")] for c in ("lang", "country")}
    out["total"] = con.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    con.close()
    return out
