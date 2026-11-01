"""The karaoke machine: queue, current song, live key/tempo/melody/chorus. One instance per process."""
import itertools
import threading
import time

from . import config
from .log import log
from .player import Mpv, graph, prepare

KEY_RANGE, TEMPO_RANGE = (-12, 12), (0.5, 1.5)


class Engine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.mpv = Mpv(self._on_end)
        self.queue, self.qid = [], itertools.count(1)
        self.phase, self.song, self.prep = "idle", None, None
        self.gen = 0          # bumps whenever the current song is abandoned
        self.rev = 0          # bumps per song so clients know to refetch lyrics
        self.key, self.tempo = 0, 1.0
        self.melody, self.chorus = cfg["melody"], cfg["chorus"]
        self.intro_until, self.error = 0.0, ""
        self.skip_intro = threading.Event()
        self.mpv.set("volume", cfg["volume"])
        log.info("engine ready")

    # ---------------------------------------------------------------- queue
    def reserve(self, song, top=False):
        with self.lock:
            item = {"qid": next(self.qid), "song": song}
            self.queue.insert(0 if top else len(self.queue), item)
            if self.phase == "idle":
                self._advance()
        return item

    def unqueue(self, qid):
        with self.lock:
            self.queue = [q for q in self.queue if q["qid"] != qid]

    def move_top(self, qid):
        with self.lock:
            hit = [q for q in self.queue if q["qid"] == qid]
            if hit:
                self.queue.remove(hit[0]); self.queue.insert(0, hit[0])

    def clear(self):
        with self.lock:
            self.queue = []

    # ---------------------------------------------------------------- playback flow
    def next(self):
        with self.lock:
            self._advance()

    def _advance(self):
        self.gen += 1
        self.skip_intro.set()
        try:
            self.mpv.cmd("stop")
        except (RuntimeError, TimeoutError):
            pass
        if not self.queue:
            self.phase, self.song, self.prep, self.error = "idle", None, None, ""
            self.rev += 1
            return
        item = self.queue.pop(0)
        self.song, self.prep, self.error = item["song"], None, ""
        self.key, self.tempo = 0, 1.0
        self.melody, self.chorus = self.cfg["melody"], self.cfg["chorus"]
        self.phase, self.rev = "prep", self.rev + 1
        self.intro_until = time.time() + self.cfg["intro"]
        self.skip_intro.clear()
        threading.Thread(target=self._run, args=(self.gen, self.song), daemon=True).start()

    def _run(self, gen, song):
        try:
            prep = prepare(song, self.cfg)
        except Exception as ex:  # missing soundfont, bad file, ffmpeg failure: show it, move on
            log.exception("could not prepare %s", song["path"])
            return self._fail(gen, str(ex))
        with self.lock:
            if gen != self.gen: return
            self.prep, self.phase = prep, "intro"
        self.skip_intro.wait(max(0.0, self.intro_until - time.time()))
        err = None
        with self.lock:
            if gen != self.gen: return
            try:
                self.mpv.set("pause", True)
                self._graph()
                self.mpv.cmd("loadfile", prep["audio"], "replace")
                for _ in range(100):  # wait for the file to be ready, then start together
                    if self.mpv.get("duration"): break
                    time.sleep(0.05)
                else:
                    raise RuntimeError("mpv could not open " + prep["audio"])
                self.mpv.set("speed", self.tempo)   # tempo may have been changed during the intro
                self.mpv.set("pause", False)
                self.phase = "playing"
            except (RuntimeError, TimeoutError) as ex:
                err = f"mpv: {ex}"
        if err:
            self._fail(gen, err)

    def _fail(self, gen, msg):
        """Show an error for a few seconds, then move on. Call without holding the lock."""
        log.error("song failed: %s (%s)", msg, self.song and self.song["path"])
        with self.lock:
            if gen != self.gen: return
            self.phase, self.error = "error", msg
        time.sleep(5)
        with self.lock:
            if gen == self.gen: self._advance()

    def _on_end(self, reason):
        with self.lock:
            if self.phase not in ("playing", "paused"): return
            gen = self.gen
            if reason == "eof":
                return self._advance()
        if reason == "error":
            self._fail(gen, "mpv could not play this file")

    # ---------------------------------------------------------------- live controls
    def _graph(self):
        if self.prep:
            self.mpv.set("lavfi-complex", graph(self.prep["layers"], self.melody, self.chorus, self.key))

    def pause(self):
        with self.lock:
            if self.phase == "intro":
                self.skip_intro.set()
            elif self.phase in ("playing", "paused"):
                self.mpv.set("pause", self.phase == "playing")
                self.phase = "paused" if self.phase == "playing" else "playing"

    def restart(self):
        with self.lock:
            if self.phase in ("playing", "paused"):
                self.mpv.cmd("seek", 0, "absolute")

    def set_key(self, value=None, delta=0):
        with self.lock:
            v = 0 if value == 0 else self.key + delta if value is None else value
            self.key = max(KEY_RANGE[0], min(KEY_RANGE[1], int(v)))
            self._graph()

    def set_tempo(self, value=None, delta=0):
        with self.lock:
            v = self.tempo + delta if value is None else value
            self.tempo = round(max(TEMPO_RANGE[0], min(TEMPO_RANGE[1], v)), 2)
            if self.phase in ("playing", "paused"):
                self.mpv.set("speed", self.tempo)

    def toggle(self, layer):
        with self.lock:
            if not (self.prep and self.prep["layers"].get(layer)):
                return  # song has no such layer
            setattr(self, layer, not getattr(self, layer))
            self.cfg[layer] = getattr(self, layer)
            config.save(self.cfg)
            self._graph()

    def set_volume(self, v):
        with self.lock:
            self.cfg["volume"] = max(0, min(130, int(v)))
            config.save(self.cfg)
            self.mpv.set("volume", self.cfg["volume"])

    # ---------------------------------------------------------------- snapshot for the UI
    def state(self):
        with self.lock:
            phase, prep = self.phase, self.prep
            s = {
                "phase": phase, "song": self.song, "rev": self.rev, "error": self.error,
                "key": self.key, "tempo": self.tempo, "melody": self.melody, "chorus": self.chorus,
                "volume": self.cfg["volume"], "kind": self.song["kind"] if self.song else None,
                "caps": {"melody": bool(prep and prep["layers"].get("melody")),
                         "chorus": bool(prep and prep["layers"].get("chorus"))},
                "intro_left": max(0.0, self.intro_until - time.time()) if phase in ("prep", "intro") else 0,
                "queue": list(self.queue), "has_video": bool(prep and prep["video"]), "has_cdg": bool(prep and prep["cdg"]),
            }
        s["pos"] = self.mpv.get("time-pos") if phase in ("playing", "paused") else None
        s["duration"] = self.mpv.get("duration") if s["pos"] is not None else None
        return s

    def lyrics(self):
        with self.lock:
            return {"rev": self.rev, "lines": self.prep["lyrics"] if self.prep else []}

    def media(self, song_id, what):
        with self.lock:
            if self.song and self.song["id"] == song_id and self.prep:
                return self.prep.get(what)
