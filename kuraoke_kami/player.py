"""Audio side: mpv over JSON IPC, and turning every song type into 'stems' (base / melody / chorus)."""
import glob
import hashlib
import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

from . import config
from .lyrics import (chart_lyrics, chorus_mid_lyrics, midi_groups, midi_lyrics,
                     parse_lrc, read_smf, split_midi)

SF_GLOBS = ["/usr/share/soundfonts/*.sf2", "/usr/share/soundfonts/*.sf3", "/usr/share/sounds/sf2/*.sf2",
            "~/.local/share/soundfonts/*.sf2", "~/.local/share/soundfonts/*.sf3"]
AUDIO_EXT = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".opus")


class Mpv:
    def __init__(self, on_eof):
        run = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
        self.path = f"{run}/kuraoke-kami-mpv-{os.getpid()}.sock"  # per process: two instances never share one
        self.on_eof, self.pending, self.rid = on_eof, {}, 0
        self.slock = threading.Lock()
        try:
            os.unlink(self.path)
        except OSError:
            pass
        try:
            self.proc = subprocess.Popen(
                ["mpv", "--idle=yes", "--no-video", "--no-terminal", "--pause", "--audio-display=no",
                 "--volume-max=130", f"--input-ipc-server={self.path}", *os.environ.get("KURAOKE_MPV_OPTS", "").split()],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise RuntimeError("mpv is not installed: sudo pacman -S mpv")
        for _ in range(60):
            try:
                self.s = socket.socket(socket.AF_UNIX)
                self.s.connect(self.path)
                break
            except OSError:
                self.s.close(); time.sleep(0.1)
        else:
            raise RuntimeError("mpv did not start")
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.s.makefile("r"):
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if "request_id" in m:
                w = self.pending.pop(m["request_id"], None)
                if w:
                    w[1].update(m); w[0].set()
            elif m.get("event") == "end-file":
                # own thread: the handler talks to mpv, which this reader thread must stay free to answer
                threading.Thread(target=self.on_eof, args=(m.get("reason"),), daemon=True).start()

    def cmd(self, *a, timeout=3):
        ev, res = threading.Event(), {}
        with self.slock:
            self.rid += 1
            rid = self.rid
            self.pending[rid] = (ev, res)
            self.s.sendall(json.dumps({"command": list(a), "request_id": rid}).encode() + b"\n")
        if not ev.wait(timeout):
            self.pending.pop(rid, None)
            raise TimeoutError("mpv not answering")
        if res.get("error") != "success":
            raise RuntimeError(res.get("error"))
        return res.get("data")

    def get(self, name):
        try:
            return self.cmd("get_property", name, timeout=1)
        except (RuntimeError, TimeoutError):
            return None

    def set(self, name, value):
        self.cmd("set_property", name, value)

    def close(self):
        self.proc.terminate()
        try:
            os.unlink(self.path)
        except OSError:
            pass


def graph(layers, melody, chorus, key):
    """mpv lavfi-complex string: mix the stems with live volumes, then pitch-shift by `key` semitones."""
    vols = [("base", 1)] + [(n, int(on)) for n, on in (("melody", melody), ("chorus", chorus)) if layers.get(n)]
    parts = [f"[aid{layers[n]}]volume={v}[s{i}]" for i, (n, v) in enumerate(vols)]
    mix = "".join(f"[s{i}]" for i in range(len(vols))) + f"amix=inputs={len(vols)}:normalize=0"
    tail = f"rubberband=pitch={2 ** (key / 12):.5f}" if key else "anull"
    return ";".join(parts + [f"{mix},{tail}[ao]"])


def _run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{args[0]} failed: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}")


def _audio_streams(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return len(r.stdout.split())


def _sibling(path, exts):
    p = Path(path)
    for f in sorted(p.parent.iterdir()):
        if f.stem.lower() == p.stem.lower() and f.suffix.lower() in exts:
            return str(f)


def _lrc(path):
    f = _sibling(path, (".lrc",))
    return parse_lrc(Path(f).read_text(errors="replace")) if f else []


def find_soundfont(cfg):
    if cfg.get("soundfont") and os.path.isfile(cfg["soundfont"]):
        return cfg["soundfont"]
    for g in SF_GLOBS:
        hits = sorted(glob.glob(os.path.expanduser(g)))
        if hits:
            return hits[0]
    raise RuntimeError("No SoundFont found for MIDI. Install one: sudo pacman -S soundfont-fluid")


def _mix_stems(out, groups):
    """groups: {name: [files]} (base first) -> one .mka with a stream per group. Returns layers {name: aid}."""
    args, filt, names = ["ffmpeg", "-v", "error", "-y"], [], []
    idx = 0
    for name, files in groups.items():
        for f in files:
            args += ["-i", f]
        ins = "".join(f"[{idx + k}:a]" for k in range(len(files)))
        filt.append(f"{ins}amix=inputs={len(files)}:normalize=0[{name}]" if len(files) > 1 else f"{ins}anull[{name}]")
        idx += len(files); names.append(name)
    args += ["-filter_complex", ";".join(filt)]
    for n in names:
        args += ["-map", f"[{n}]"]
    _run(args + ["-c:a", "flac", str(out)])
    return {n: i + 1 for i, n in enumerate(names)}


def _cached(tag, fn, *deps):
    key = hashlib.sha1("|".join(str(d) for d in deps).encode()).hexdigest()[:16]
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out, meta = config.CACHE_DIR / f"{tag}-{key}.mka", config.CACHE_DIR / f"{tag}-{key}.json"
    if out.exists() and meta.exists():
        return str(out), json.loads(meta.read_text())
    tmp = out.with_suffix(".part.mka")
    layers = fn(tmp)
    tmp.replace(out)
    meta.write_text(json.dumps(layers))
    return str(out), layers


def prepare(song, cfg):
    """-> {audio, layers:{base,melody?,chorus?}, lyrics, video?, cdg?}. Heavy work (MIDI render, stem mix) is cached."""
    path, kind = song["path"], song["kind"]
    out = {"audio": path, "layers": {"base": 1}, "lyrics": [], "video": None, "cdg": None}
    if kind == "audio":
        out["lyrics"] = _lrc(path)
    elif kind == "video":
        out["video"], out["lyrics"] = path, _lrc(path)
        if _audio_streams(path) >= 2:  # classic karaoke video: track 1 backing, track 2 guide vocal
            out["layers"]["melody"] = 2
    elif kind == "cdg":
        out["audio"], out["cdg"] = _sibling(path, AUDIO_EXT), path
        if not out["audio"]:
            raise RuntimeError("CDG has no matching audio file")
    elif kind == "midi":
        sf = find_soundfont(cfg)
        div, tracks = read_smf(Path(path).read_bytes())
        out["lyrics"] = midi_lyrics(div, tracks)

        def render(tmp):
            parts = split_midi(div, tracks, midi_groups(tracks))
            wavs = {}
            for g, data in parts.items():
                mid, wav = f"{tmp}.{g}.mid", f"{tmp}.{g}.wav"
                Path(mid).write_bytes(data)
                _run(["fluidsynth", "-ni", "-q", "-g", "0.7", "-r", "44100", "-T", "wav", "-F", wav, sf, mid])
                wavs[g] = [wav]
            try:
                return _mix_stems(tmp, wavs)
            finally:
                for g in wavs:
                    for ext in ("mid", "wav"):
                        try: os.unlink(f"{tmp}.{g}.{ext}")
                        except OSError: pass
        out["audio"], out["layers"] = _cached("midi", render, path, os.path.getmtime(path), sf)
    elif kind == "chorus":
        out.update(_prepare_chorus(path))
    return out


def _prepare_chorus(folder):
    files = {f.stem.lower(): f for f in Path(folder).iterdir() if f.suffix.lower() in AUDIO_EXT}
    if not files:
        raise RuntimeError("Chorus song has no audio file")
    mel = [files[n] for n in ("vocals", "vocals_main") if n in files]
    cho = [files[n] for n in sorted(files) if re.fullmatch(r"vocals_\d+|harmony\d*|backing\d*", n)]
    base = [f for n, f in files.items() if f not in mel + cho and n not in ("preview", "crowd")]
    if not base:  # only vocal stems present: play them as the backing
        base, mel = mel, []
    res = {}
    mid, chart = Path(folder, "notes.mid"), Path(folder, "notes.chart")
    if mid.exists():
        res["lyrics"] = chorus_mid_lyrics(*read_smf(mid.read_bytes()))
    elif chart.exists():
        res["lyrics"] = chart_lyrics(chart.read_text(errors="replace"))
    if len(base) == 1 and not mel and not cho:
        return {**res, "audio": str(base[0])}
    groups = {"base": [str(f) for f in base]}
    if mel: groups["melody"] = [str(f) for f in mel]
    if cho: groups["chorus"] = [str(f) for f in cho]
    audio, layers = _cached("chorus", lambda tmp: _mix_stems(tmp, groups), folder, *(os.path.getmtime(f) for g in groups.values() for f in g), *groups)
    return {**res, "audio": audio, "layers": layers}
