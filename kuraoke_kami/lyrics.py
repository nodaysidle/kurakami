"""Lyric + MIDI parsing. Pure stdlib.

Lyrics are always `lines`: list of lines, each a list of [start_s, end_s, text] tokens.
Token text keeps its own spaces, so syllables glue together and words stay apart.
"""
import bisect
import re
import struct

# ---------------------------------------------------------------- SMF reading / writing

def _vlq(b, i):
    n = 0
    while True:
        c = b[i]; i += 1
        n = (n << 7) | (c & 0x7F)
        if not c & 0x80:
            return n, i


def _vlq_bytes(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def _track(b):
    """-> [(tick, status, meta_type, data)]; status 0xFF = meta, 0xF0/0xF7 = sysex."""
    ev, i, t, run = [], 0, 0, 0
    while i < len(b):
        d, i = _vlq(b, i)
        t += d
        s = b[i]
        if s == 0xFF:
            mt = b[i + 1]
            ln, j = _vlq(b, i + 2)
            ev.append((t, 0xFF, mt, bytes(b[j:j + ln])))
            i = j + ln
            if mt == 0x2F:
                break
        elif s in (0xF0, 0xF7):
            ln, j = _vlq(b, i + 1)
            ev.append((t, s, 0, bytes(b[j:j + ln])))
            i = j + ln
        else:
            if s & 0x80:
                run = s; i += 1
            n = 1 if (run & 0xF0) in (0xC0, 0xD0) else 2
            ev.append((t, run, 0, bytes(b[i:i + n])))
            i += n
    return ev


def read_smf(data):
    if data[:4] != b"MThd":
        raise ValueError("not a MIDI file")
    _fmt, ntrk, div = struct.unpack(">HHH", data[8:14])
    if div & 0x8000:
        raise ValueError("SMPTE-timed MIDI is not supported")
    pos = 8 + struct.unpack(">I", data[4:8])[0]
    tracks = []
    while pos + 8 <= len(data) and len(tracks) < ntrk:
        ln = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        if data[pos:pos + 4] == b"MTrk":
            tracks.append(_track(data[pos + 8:pos + 8 + ln]))
        pos += 8 + ln
    return div, tracks


def write_smf(div, tracks):
    out = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), div)
    for ev in tracks:
        body, last = b"", 0
        for t, s, m, d in sorted(ev, key=lambda e: e[0]):  # stable: same-tick order is kept
            body += _vlq_bytes(t - last); last = t
            if s == 0xFF:
                body += bytes([0xFF, m]) + _vlq_bytes(len(d)) + d
            elif s in (0xF0, 0xF7):
                body += bytes([s]) + _vlq_bytes(len(d)) + d
            else:
                body += bytes([s]) + d
        out += b"MTrk" + struct.pack(">I", len(body)) + body
    return out


def is_note(e):
    t, s, m, d = e
    return s < 0xF0 and (s & 0xF0) in (0x80, 0x90)


def make_tempo(div, changes):
    """changes: [(tick, usec_per_quarter)] -> tick->seconds function."""
    pts = [(0, 0.0, 500000)]
    for t, u in sorted(changes):
        pt, ps, pu = pts[-1]
        pts.append((t, ps + (t - pt) * pu / 1e6 / div, u))
    keys = [p[0] for p in pts]

    def f(tick):
        pt, ps, pu = pts[bisect.bisect_right(keys, tick) - 1]
        return ps + (tick - pt) * pu / 1e6 / div
    return f


def smf_tempo(div, tracks):
    return make_tempo(div, [(t, int.from_bytes(d, "big")) for tr in tracks
                            for t, s, m, d in tr if s == 0xFF and m == 0x51 and d])


def _dec(b):
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252", "replace")


def track_name(tr):
    for t, s, m, d in tr:
        if s == 0xFF and m == 0x03:
            return _dec(d).strip()
    return ""


# ---------------------------------------------------------------- stem classification (MIDI)

MEL_RE = re.compile(r"melod|vocal|voice|vox|singer|guide", re.I)
CHO_RE = re.compile(r"chor|backing|backup|harm|bgv|bvox|choir", re.I)


def midi_groups(tracks):
    """-> list parallel to tracks: 'melody' | 'chorus' | 'base' (only tracks that carry notes are classified)."""
    out = []
    for tr in tracks:
        n = track_name(tr)
        if not any(is_note(e) for e in tr):
            out.append("base")
        elif CHO_RE.search(n):
            out.append("chorus")
        elif MEL_RE.search(n):
            out.append("melody")
        else:
            out.append("base")
    return out


def split_midi(div, tracks, groups):
    """-> {group: smf_bytes}; each file keeps every non-note event but notes only of that group."""
    out = {}
    for g in ("base", "melody", "chorus"):
        if g != "base" and g not in groups:
            continue
        out[g] = write_smf(div, [[e for e in tr if not is_note(e) or groups[k] == g]
                                 for k, tr in enumerate(tracks)])
    return out


# ---------------------------------------------------------------- lyric line building

def build_lines(toks, cap=3.0):
    """toks: [(start_s, text, break_before)] -> lines of [start, end, text]."""
    lines, cur, width = [], [], 0
    for i, (t, x, brk) in enumerate(toks):
        nxt = toks[i + 1][0] if i + 1 < len(toks) else t + 1.5
        e = min(nxt, t + cap) if nxt > t else t + 0.3
        if cur:
            gap = t - cur[-1][0]
            wordb = x.startswith(" ") or cur[-1][2].endswith(" ")
            if brk or gap > 4.0 or (width > 44 and wordb):
                lines.append(cur); cur, width = [], 0
        cur.append([t, e, x]); width += len(x)
    if cur:
        lines.append(cur)
    return lines


def midi_lyrics(div, tracks):
    """Standard lyric events (0x05), else KAR-style text events (0x01 after '@' headers)."""
    f = smf_tempo(div, tracks)
    raw = [(t, _dec(d)) for tr in tracks for t, s, m, d in tr if s == 0xFF and m == 0x05]
    if not raw:
        for tr in tracks:
            ev = [(t, _dec(d)) for t, s, m, d in tr if s == 0xFF and m == 0x01]
            if any(x.startswith("@") for _, x in ev):
                raw += [(t, x) for t, x in ev if not x.startswith("@")]
    raw.sort(key=lambda r: r[0])
    toks, pending = [], False
    for t, x in raw:
        brk = pending or x.startswith(("/", "\\"))
        x = x.lstrip("/\\")
        pending = x.endswith(("\n", "\r"))
        x = x.strip("\r\n")
        if x == "":
            pending = pending or brk
            continue
        toks.append((f(t), x, brk))
    return build_lines(toks)


# ---------------------------------------------------------------- Chorus (Clone Hero) lyrics

def ch_token(x):
    """Rock Band / Clone Hero lyric conventions -> display text or None to skip."""
    x = x.strip()
    if not x or x.startswith(("[", "+")):
        return None
    x = x.rstrip("#^*%$")
    if x.endswith("="):
        return x[:-1] + "-"
    if x.endswith("-"):
        return x[:-1]
    return x + " "


def ch_lines(f, lyr, phrase_starts):
    """lyr: [(tick, text)], phrase_starts: sorted ticks -> lines."""
    toks, last = [], None
    for t, x in sorted(lyr):
        x = ch_token(x)
        if x is None:
            continue
        p = bisect.bisect_right(phrase_starts, t) - 1 if phrase_starts else None
        toks.append((f(t), x, last is not None and p != last))
        last = p
    return build_lines(toks)


def chorus_mid_lyrics(div, tracks):
    f = smf_tempo(div, tracks)
    for tr in tracks:
        if track_name(tr).upper() == "PART VOCALS":
            lyr = [(t, _dec(d)) for t, s, m, d in tr if s == 0xFF and m == 0x05]
            ph = sorted(t for t, s, m, d in tr if (s & 0xF0) == 0x90 and len(d) == 2 and d[0] == 105 and d[1] > 0)
            return ch_lines(f, lyr, ph)
    return []


def chart_lyrics(text):
    sec = {n: b for n, b in re.findall(r"\[(\w+)\]\s*\{(.*?)\}", text, re.S)}
    m = re.search(r"Resolution\s*=\s*(\d+)", sec.get("Song", ""))
    div = int(m.group(1)) if m else 192
    tempo = [(int(t), int(6e10 / int(b))) for t, b in re.findall(r"(\d+)\s*=\s*B\s+(\d+)", sec.get("SyncTrack", "")) if int(b)]
    f = make_tempo(div, tempo)
    ev = [(int(t), x) for t, x in re.findall(r'(\d+)\s*=\s*E\s+"([^"]*)"', sec.get("Events", ""))]
    lyr = [(t, x[6:]) for t, x in ev if x.startswith("lyric ")]
    ph = sorted(t for t, x in ev if x == "phrase_start")
    return ch_lines(f, lyr, ph)


def parse_ini(text):
    out = {}
    for ln in text.splitlines():
        if "=" in ln and not ln.lstrip().startswith((";", "#", "[")):
            k, v = ln.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


# ---------------------------------------------------------------- LRC (line + enhanced word timing)

def parse_lrc(text):
    """Plain `[mm:ss.xx] line` and enhanced `[..] <mm:ss.xx>word <..>word` LRC."""
    toks, plain = [], []
    for ln in text.splitlines():
        stamps = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", ln)
        body = re.sub(r"\[\d+:\d+(?:\.\d+)?\]", "", ln)
        words = re.findall(r"<(\d+):(\d+(?:\.\d+)?)>([^<]*)", body)
        if words:
            toks += [(int(a) * 60 + float(b), w, i == 0) for i, (a, b, w) in enumerate(words) if w.strip()]
        elif body.strip():
            plain += [(int(a) * 60 + float(b), body.split()) for a, b in stamps]
    plain.sort(key=lambda r: r[0])
    # line-timed LRC: spread each line's words over the time until the next line, so the fill still moves word by word
    for i, (t, ws) in enumerate(plain):
        span = max(1.0, min((plain[i + 1][0] if i + 1 < len(plain) else t + 4) - t - 0.2, 0.45 * len(ws) + 0.8))
        total, at = sum(len(w) + 1 for w in ws), t
        for k, w in enumerate(ws):
            toks.append((at, w + " ", k == 0))
            at += span * (len(w) + 1) / total
    toks.sort(key=lambda r: r[0])
    return build_lines(toks)
