"""Folder scan -> SQLite song book. Song numbers are stable per file, renames included."""
import os
import re
import sqlite3
from pathlib import Path

from . import config
from .lyrics import lrc_is_suspect, lrc_kind, parse_ini

AUDIO = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".opus"}
VIDEO = {".mp4", ".mkv", ".webm", ".m4v"}  # what Chromium can decode; .mpg/.avi would play as sound over a black screen
MIDI = {".mid", ".midi", ".kar"}
PRIO = {"video": 1, "cdg": 2, "chorus": 3, "midi": 4, "audio": 5}  # best format wins when de-duplicating

SCHEMA = """CREATE TABLE IF NOT EXISTS songs(
 id INTEGER PRIMARY KEY, number INTEGER UNIQUE, path TEXT UNIQUE, root TEXT, kind TEXT,
 title TEXT, artist TEXT, lang TEXT, country TEXT, nkey TEXT, prio INT,
 lyrics TEXT, size INT, mtime REAL);
CREATE INDEX IF NOT EXISTS songs_nkey ON songs(nkey);
CREATE INDEX IF NOT EXISTS songs_root ON songs(root, number)"""

NEW_COLS = (("lyrics", "TEXT"), ("size", "INT"), ("mtime", "REAL"))  # song books from older versions get them


def db():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_FILE, timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(songs)")}
    for col, typ in NEW_COLS:
        if col not in have:
            try:
                con.execute(f"ALTER TABLE songs ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass  # another connection migrated it first
    con.commit()
    return con


def norm(title, artist):
    s = re.sub(r"[\(\[].*?[\)\]]", "", f"{artist} {title}".lower())
    return re.sub(r"[^\w]+", "", s)


JUNK = re.compile(r"\s*[\(\[][^\)\]]*\b(official|video|audio|lyrics?|visuali[sz]er|hd|hq|4k|karaoke|sanremo|clip|mv)\b[^\)\]]*[\)\]]", re.I)


TRAIL = re.compile(r"\s+(official\s+(music\s+)?(video|audio|visuali[sz]er|lyric\s+video)|(lyrics?|lyric)\s+video|video\s+ufficiale|audio\s+ufficiale|videoclip)\s*$", re.I)

FEAT = re.compile(r"\s*[\(\[]?\s*(?<![A-Za-z])(feat\.|featuring|ft\.)\s+(.+?)\s*[\)\]]?\s*$", re.I)  # "Song ft. Guest"


def clean_stem(stem):
    """'ARTIST_-_CUORICINI (Official Video - Sanremo 2025) [dQw4w9WgXcQ]' -> 'Artist - Cuoricini'."""
    s = re.sub(r"\s*\[[\w-]{11}\]$", "", stem)          # yt-dlp video id
    s = s.replace("_", " ")                             # Coma_Cose -> Coma Cose
    s = JUNK.sub("", s)
    s = TRAIL.sub("", s)            # "Title Official Video" without brackets
    s = re.sub(r"\s*-\s*Topic$", "", s)
    s = re.sub(r"\s+[–—|]\s+", " - ", s)          # "Artist – Title", "Artist | Title"
    if " - " not in s:                             # "Artist 'Title'", "Artist “Title”"
        s = re.sub(r"^(.+?)\s+['\"‘“«](.+)['\"’”»]$", r"\1 - \2", s.strip())
    s = re.sub(r'[/\\:*?"<>|]', "", s)
    s = " ".join(s.split())
    return " - ".join(p.title() if p.isupper() and len(p) > 3 else p for p in s.split(" - "))


def split_name(stem):
    """'Artist - Title (feat. Guest)' -> (title, artist). Display only: files are never renamed."""
    s = " ".join(stem.replace("_", " ").split())
    parts = [p.strip() for p in s.split(" - ")]
    if len(parts) >= 3 and len(parts[0]) <= 12 and any(c.isdigit() for c in parts[0]):
        parts = parts[1:]
    if len(parts) >= 2:
        title, artist = " - ".join(parts[1:]), parts[0]
    else:
        title, artist = s, ""
    m = FEAT.search(title)  # "Everyday ft. Rod Stewart" by A$AP Rocky -> Everyday / A$AP Rocky ft. Rod Stewart
    if m and artist and title[:m.start()].strip():
        title, artist = title[:m.start()].strip(), f"{artist} {m.group(1).lower()} {m.group(2)}"
    return title.strip(), artist.strip()


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


# ---------------------------------------------------------------- lyrics beside the song

def lrc_for(song_path):
    """The sibling .lrc of a song (case-insensitive stem), or None. Chorus folders carry theirs inside."""
    p = Path(song_path)
    if p.is_dir() or (p / "song.ini").is_file():
        return None
    try:
        exact = p.with_suffix(".lrc")
    except ValueError:
        return None
    if exact.is_file():
        return exact
    want = p.stem.lower() + ".lrc"
    try:
        for f in sorted(p.parent.iterdir()):
            if f.is_file() and f.name.lower() == want:
                return f
    except OSError:
        return None
    return None


def lrc_target(song_path):
    """Where a newly fetched .lrc goes."""
    return Path(song_path).with_suffix(".lrc")


def lyrics_status(path, kind):
    """word | line | suspect | embedded | cdg | none."""
    p = Path(path)
    if kind == "cdg":
        return "cdg"
    if kind == "midi":
        return "embedded"
    if kind == "chorus":
        try:
            names = {f.lower() for f in os.listdir(p)}
        except OSError:
            names = set()
        return "embedded" if names & {"notes.mid", "notes.chart"} else "none"
    f = lrc_for(p)
    if not f:
        return "none"
    try:
        text = f.read_text(errors="replace")
    except OSError:
        return "none"
    return "suspect" if lrc_is_suspect(text) else lrc_kind(text)


def next_number(con, root, start):
    m = con.execute("SELECT MAX(number) FROM songs WHERE root=?", (root,)).fetchone()[0]
    n = max(start, (m or start - 1) + 1)
    while con.execute("SELECT 1 FROM songs WHERE number=?", (n,)).fetchone():
        n += 1
    return n


def _stat(path):
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    return st.st_size, st.st_mtime


def _listing(cfg, progress, cache):
    """Every playable file in the configured folders, one dict per row, with its lyrics status."""
    items = []
    for fo in cfg["folders"]:
        root = fo["path"]
        for path, kind, title, artist in walk(root):
            size, mtime = _stat(path)
            key = (path, kind)
            if key not in cache:
                cache[key] = lyrics_status(path, kind)
            items.append({"path": path, "root": root, "kind": kind, "title": title, "artist": artist,
                          "lang": fo.get("lang", ""), "country": fo.get("country", ""),
                          "nkey": norm(title, artist) or path, "prio": PRIO[kind], "lyrics": cache[key],
                          "size": size, "mtime": mtime, "start": int(fo.get("start") or 1)})
            if progress and len(items) % 50 == 0:
                progress(len(items))
    return list({it["path"]: it for it in items}.values())  # the same file can sit in two folders


def _renames(items, gone):
    """Give vanished rows to new paths of the same root: identical (size, mtime), else same nkey+kind."""
    by_file, by_key, new_key = {}, {}, {}
    for r in gone:
        if r["size"] is not None and r["mtime"] is not None:
            by_file.setdefault((r["root"], r["size"], r["mtime"]), []).append(r)
        by_key.setdefault((r["root"], r["nkey"], r["kind"]), []).append(r)
    for it in items:
        new_key.setdefault((it["root"], it["nkey"], it["kind"]), []).append(it)
    for it in items:
        k = (it["root"], it["nkey"], it["kind"])
        cand = by_file.get((it["root"], it["size"], it["mtime"])) if it["size"] is not None and it["mtime"] is not None else None
        r = cand.pop(0) if cand else None
        if r is None and len(new_key[k]) == 1 and len(by_key.get(k, [])) == 1:
            r = by_key[k].pop(0)
            fk = (r["root"], r["size"], r["mtime"])
            if r in by_file.get(fk, []):
                by_file[fk].remove(r)
        if r is not None:
            bk = (r["root"], r["nkey"], r["kind"])
            if r in by_key.get(bk, []):
                by_key[bk].remove(r)
            it["take"] = r


def scan(cfg, rebuild=False, progress=None, renamed=None):
    """Index all folders. rebuild=True wipes the book and renumbers; numbers survive renames between scans.

    `renamed(old_path, new_path)` is called for every row whose file was renamed (its number and id are kept).
    """
    con = db()
    if rebuild:
        con.execute("DELETE FROM songs")
    old = {r["path"]: dict(r) for r in con.execute("SELECT * FROM songs")}
    items = _listing(cfg, progress, {})
    seen = {it["path"] for it in items}
    gone = [r for p, r in old.items() if p not in seen]
    new = [it for it in items if it["path"] not in old]
    _renames(new, gone)
    moved, kept = [], set()
    for it in items:
        vals = (it["root"], it["kind"], it["title"], it["artist"], it["lang"], it["country"], it["nkey"], it["prio"],
                it["lyrics"], it["size"], it["mtime"])
        take = it.get("take")
        if it["path"] in old:
            con.execute("UPDATE songs SET root=?,kind=?,title=?,artist=?,lang=?,country=?,nkey=?,prio=?,"
                        "lyrics=?,size=?,mtime=? WHERE path=?", vals + (it["path"],))
        elif take:
            con.execute("UPDATE songs SET path=?,root=?,kind=?,title=?,artist=?,lang=?,country=?,nkey=?,prio=?,"
                        "lyrics=?,size=?,mtime=? WHERE id=?", (it["path"],) + vals + (take["id"],))
            moved.append((take["path"], it["path"]))
            kept.add(take["id"])
        else:
            con.execute("INSERT INTO songs(number,path,root,kind,title,artist,lang,country,nkey,prio,lyrics,size,mtime)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (next_number(con, it["root"], it["start"]), it["path"]) + vals)
    for r in gone:
        if r["id"] not in kept:
            con.execute("DELETE FROM songs WHERE id=?", (r["id"],))
    con.commit()
    con.close()
    if renamed:
        for old_path, new_path in moved:  # the caller moves anything keyed by the old path (config offsets)
            renamed(old_path, new_path)
    return len(items)


def refresh(path):
    """Re-read one row's lyrics status after its .lrc was written or edited. -> status, None if not in the book."""
    path = os.fspath(path)
    con = db()
    r = con.execute("SELECT kind FROM songs WHERE path=?", (path,)).fetchone()
    if not r:
        con.close()
        return None
    st = lyrics_status(path, r["kind"])
    size, mtime = _stat(path)
    if size is None:
        con.execute("UPDATE songs SET lyrics=? WHERE path=?", (st, path))
    else:
        con.execute("UPDATE songs SET lyrics=?,size=?,mtime=? WHERE path=?", (st, size, mtime, path))
    con.commit()
    con.close()
    return st


def query(q="", langs=(), countries=(), dedupe=False, limit=200, offset=0, missing=False):
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
    if missing:
        where.append("lyrics IN ('none','suspect')")
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
    out["missing"] = con.execute("SELECT COUNT(*) FROM songs WHERE lyrics IN ('none','suspect')").fetchone()[0]
    con.close()
    return out
