"""Speech-recognition timing: turn a word-timestamped transcript into word-timed LRC. Pure stdlib.

Two cases:
- the words are known (an untimed or badly timed .lrc, or lyrics stored in the file's tags): each known word takes the time
  of the transcript word it matches; words in between are interpolated; lines with no recognised word share the gap
  before the next recognised line.
- nothing is known: the transcript itself becomes the lyrics (machine-made, may contain mistakes).

A transcript is [{"start", "end", "text", "words": [{"w", "s", "e"}]}] as written by tools/whisper_words.py.
"""
import difflib
import re

# [Verse 1], (Chorus), [Outro x2]: headers, not sung. Other lines in parentheses, "(Ah)", are sung ad-libs and stay.
SECTION = re.compile(r"^\s*(\[[^\]]*\]|\((intro|verse|pre-?chorus|chorus|refrain|hook|bridge|outro|interlude|"
                     r"instrumental|break|solo|ritornello|strofa|rit\.?)[^)]*\))\s*$", re.I)
STAMP = re.compile(r"\[\d+:\d+(?:\.\d+)?\]|<\d+:\d+(?:\.\d+)?>")
TAG = re.compile(r"^\s*\[[a-z]+:.*\]\s*$", re.I)                # [ar:..] [offset:..] [kk:..]


def stamp(t):
    t = max(0.0, t)
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def norm(w):
    return re.sub(r"[^\w]", "", w.lower())


def text_lines(text):
    """Plain sung lines from an .lrc or from tag lyrics: stamps, LRC tags and [Verse] headers removed."""
    out = []
    for ln in text.splitlines():
        if TAG.match(ln) and not re.match(r"^\s*\[\d", ln):
            continue
        ln = " ".join(STAMP.sub(" ", ln).split())
        if ln and not SECTION.match(ln):
            out.append(ln)
    return out


def transcript_words(segs):
    return [(norm(w["w"]), float(w["s"])) for s in segs for w in s.get("words") or [] if norm(w["w"])]


def align(lines, segs):
    """-> (timed lines [[ [word, t], ... ], ...], share of words matched, per-line matched flags)."""
    tw = transcript_words(segs)
    lw = [(li, w) for li, ln in enumerate(lines) for w in ln.split()]
    t = [None] * len(lw)
    sm = difflib.SequenceMatcher(None, [norm(w) for _, w in lw], [w for w, _ in tw], autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            t[blk.a + k] = tw[blk.b + k][1]
    known = [i for i, x in enumerate(t) if x is not None]
    hit = [False] * len(lines)
    for i in known:
        hit[lw[i][0]] = True
    for i in range(len(t)):                          # interpolate inside and around matched words
        if t[i] is None:
            prv = max((k for k in known if k < i), default=None)
            nxt = min((k for k in known if k > i), default=None)
            if prv is not None and nxt is not None:
                t[i] = t[prv] + (t[nxt] - t[prv]) * (i - prv) / (nxt - prv)
            elif prv is not None:
                t[i] = t[prv] + 0.4 * (i - prv)
            elif nxt is not None:
                t[i] = t[nxt] - 0.4 * (nxt - i)
            else:
                t[i] = 0.0
    out = [[] for _ in lines]
    for (li, w), x in zip(lw, t):
        out[li].append([w, x])
    _spread_unmatched(out, hit)
    return out, len(known) / max(1, len(lw)), hit


def _spread_unmatched(out, hit):
    """Runs of lines without a recognised word: share the time before the next recognised line, one typical gap each."""
    starts = [ln[0][1] if ln else 0.0 for ln in out]
    gaps = sorted(b - a for a, b, h1, h2 in zip(starts, starts[1:], hit, hit[1:]) if h1 and h2 and b > a)
    gap = gaps[len(gaps) // 2] if gaps else 4.0
    i = 0
    while i < len(out):
        if hit[i] or not out[i]:
            i += 1
            continue
        j = i
        while j < len(out) and not hit[j]:
            j += 1
        nxt = starts[j] if j < len(out) else None
        prv = out[i - 1][-1][1] + 0.4 if i and out[i - 1] else None
        lo = max(prv or 0.0, (nxt - gap * (j - i)) if nxt is not None else (prv or 0.0))
        hi = nxt - 0.2 if nxt is not None else lo + gap * (j - i)
        step = max(0.3, (hi - lo) / (j - i))
        for k in range(i, j):
            st, n = lo + step * (k - i), len(out[k])
            for m, wx in enumerate(out[k]):
                wx[1] = st + step * 0.8 * m / n
        i = j


def to_lrc(header, timed):
    rows = list(header)
    for ln in timed:
        if ln:
            rows.append(f"[{stamp(ln[0][1])}]" + " ".join(f"<{stamp(x)}>{w}" for w, x in ln))
    return "\n".join(rows) + "\n"


def transcript_lines(segs, width=45):
    """The transcript as lyric lines: one per segment, cut in two at the longest pause before a capital when long."""
    lines = []
    for s in segs:
        ws = [(w["w"], float(w["s"]), float(w["e"])) for w in s.get("words") or [] if w["w"].strip()]
        if not ws:
            continue
        parts = [ws]
        if len("".join(w for w, _, _ in ws)) > width:
            cut = max((k for k in range(2, len(ws) - 1) if ws[k][0].strip()[:1].isupper()),
                      key=lambda k: ws[k][1] - ws[k - 1][2], default=None)
            if cut is not None:
                parts = [ws[:cut], ws[cut:]]
        lines += parts
    return lines


def transcript_lrc(header, segs):
    rows = list(header)
    for p in transcript_lines(segs):
        # each token keeps its own leading space from the recogniser, so "dell" + "'amico" glue back together
        rows.append(f"[{stamp(p[0][1])}]" + "".join(f"<{stamp(s)}>{w.lstrip() if i == 0 else w}" for i, (w, s, _) in enumerate(p)))
    return "\n".join(rows) + "\n"
