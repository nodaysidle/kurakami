"""HTTP server: serves the web UI, a small JSON API and range-capable media. Loopback only, one TV window."""
import hmac
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config, doctor, library, lrclib, whisper
from .engine import Engine, write_lrc
from .log import log
from .lyrics import lrc_set_offset

WEB = Path(__file__).resolve().parent.parent / "web"
MEDIA_TYPES = {"video": None, "cdg": "application/octet-stream"}


def _sid(b):
    """The song id in a POST body, or None."""
    try:
        return int(b.get("id"))
    except (TypeError, ValueError):
        return None


class App:
    def __init__(self, cfg):
        self.cfg, self.engine = cfg, Engine(cfg)
        self.scan = {"running": False, "count": 0, "error": "", "rev": 0, "importing": False, "log": []}
        self.httpd = None
        self.display_last = self.display_closing = 0.0   # the TV window polls with d=1; 0.0 = never seen
        self.host_ok = {"localhost", "127.0.0.1", "::1", socket.gethostname().lower()}
        self.hits = {}                                   # song id -> {dur, hits}: the last lyrics_search
        self.timing = {"running": False, "id": None, "error": "", "result": "", "share": 0.0, "status": ""}
        self._whisper = (False, 0.0)                     # (speech recognition installed?, when checked)

    # -------------------------------------------------------------- scanning
    def start_scan(self, rebuild=False):
        if self.scan["running"]:
            return
        self.scan.update(running=True, count=0, error="")

        def go():
            try:
                library.scan(self.cfg, rebuild=rebuild, progress=lambda n: self.scan.update(count=n), renamed=self._renamed)
            except Exception as e:
                log.exception("scan failed")
                self.scan["error"] = str(e)
            self.scan["running"] = False
            self.scan["rev"] += 1   # the song book reloads when this changes
        threading.Thread(target=go, daemon=True).start()

    def _renamed(self, old, new):
        """A rename keeps the song's number: keep the config offset (songs without an .lrc) with it too."""
        offsets = self.cfg["offsets"]
        if old in offsets:
            offsets[new] = offsets.pop(old)
            config.save(self.cfg)

    def folder_signature(self):
        """Cheap change detector: directory mtimes only (adding or removing a file touches its directory)."""
        sig = []
        for fo in self.cfg["folders"]:
            for dp, dirs, _ in os.walk(fo["path"]):
                dirs.sort()
                try:
                    sig.append((dp, os.stat(dp).st_mtime))
                except OSError:
                    pass
        return sig

    def watch_folders(self):
        """Rescan ~10 s after songs land in a folder or leave it (stdlib only, no inotify)."""
        sig = self.folder_signature()
        while True:
            time.sleep(10)
            new = self.folder_signature()
            if new == sig or self.scan["running"]:
                continue
            sig = new
            self.start_scan()

    def migrate_offsets(self):
        """One-shot: move every config offset into the song's .lrc as the standard [offset:] tag."""
        offsets, changed = self.cfg["offsets"], False
        for path, sec in list(offsets.items()):
            f = library.lrc_for(path)
            if not f:
                continue  # MIDI/KAR/Chorus/CDG keep the config fallback
            try:
                if sec:
                    write_lrc(f, lrc_set_offset(f.read_text(errors="replace"), float(sec)))
                    log.info("lyric offset %+.2f s moved into %s", float(sec), f)
                offsets.pop(path, None)
                changed = True
            except OSError:
                log.exception("could not write %s", f)
        if changed:
            config.save(self.cfg)

    # -------------------------------------------------------------- display window lifetime
    def watch_display(self):
        """Stop everything once the TV window is gone, so closing it really closes the app.
        The page sends a beacon when it closes (3 s grace so Ctrl+R doesn't count); 2 minutes of silence also counts."""
        while True:
            time.sleep(1)
            if not self.display_last:
                continue  # never had a window (--no-ui): keep running
            now = time.time()
            if (self.display_closing and now - self.display_closing > 3) or now - self.display_last > 120:
                return self.quit(close_window=False)

    def quit(self, close_window=True):
        if close_window:
            self.hypr_window('hl.dsp.window.close({ window = "address:%s" })', "dispatch closewindow address:%s")
        threading.Thread(target=self.httpd.shutdown, daemon=True).start()

    # -------------------------------------------------------------- Hyprland: act on our own window
    def hypr_window(self, lua, legacy):
        """Run a window dispatcher on the 'Kuraoke Kami' window. Tries the Lua API (Hyprland 0.5x+), then the old syntax."""
        try:
            cl = json.loads(subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=3).stdout)
            addr = next(c["address"] for c in cl if c["title"].startswith("Kuraoke Kami"))
            for args in (["dispatch", lua % addr], ["--batch", legacy % addr]):
                out = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=3).stdout
                if "ok" in out and "error" not in out.lower():
                    return True
        except (OSError, StopIteration, ValueError, subprocess.SubprocessError):
            pass
        return False  # the page falls back to the browser Fullscreen API

    def fullscreen(self):
        return self.hypr_window('hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle", window = "address:%s" })',
                                "dispatch focuswindow address:%s ; dispatch fullscreen 0")

    # -------------------------------------------------------------- lyrics: find + pick
    def lyrics_search(self, b):
        """Ranked lrclib matches for one song. Network + ffprobe: no engine lock is held here."""
        sid = _sid(b)
        song = library.get(song_id=sid) if sid is not None else None
        if not song:
            return {"ok": False, "error": "notfound", "candidates": []}
        artist = str(b.get("artist") or song["artist"] or "").strip()
        title = str(b.get("title") or song["title"] or "").strip()
        try:
            dur = lrclib.length(song["path"])
        except (OSError, subprocess.SubprocessError):
            dur = 0.0
        hits, err = lrclib.candidates(artist, title, dur)
        self.hits[song["id"]] = {"dur": dur, "hits": hits}   # the full lyrics stay here, not in the response
        return {"ok": err is None, "error": err, "candidates": [
            {"idx": i, "artist": h.get("artist"), "title": h.get("title"), "album": h.get("album"),
             "duration": h.get("duration"), "delta": h.get("delta"), "synced": h.get("synced"),
             "preview": h.get("preview") or []}
            for i, h in enumerate(hits)]}

    def lyrics_save(self, b):
        """Write the picked candidate into the song's .lrc (atomic, one .lrc.bak copy) and refresh the row."""
        sid = _sid(b)
        song, hit = (library.get(song_id=sid) if sid is not None else None), self.hits.get(sid)
        if not song:
            return {"ok": False, "error": "notfound"}
        if not hit:
            return {"ok": False, "error": "search first"}
        try:
            cand = hit["hits"][int(b.get("idx", 0))]
        except (TypeError, ValueError, IndexError):
            return {"ok": False, "error": "no such candidate"}
        return {"ok": True, "status": self._write_lyrics(song, lrclib.to_lrc(cand, hit["dur"]))}

    def _write_lyrics(self, song, text):
        """Atomic write of a song's .lrc (the first previous version is kept as .lrc.bak), then refresh + reload."""
        target = library.lrc_for(song["path"]) or library.lrc_target(song["path"])
        bak = target.with_name(target.name + ".bak")
        if target.exists() and not bak.exists():   # keep what the user had, but only the first time
            try:
                write_lrc(bak, target.read_text(errors="replace"))
            except OSError:
                log.exception("could not back up %s", target)
        write_lrc(target, text)
        library.refresh(song["path"])
        self.engine.reload_lyrics(song["id"])
        return library.lyrics_status(song["path"], song["kind"])

    # -------------------------------------------------------------- lyrics: speech recognition (optional)
    def whisper_ready(self):
        """Cached: is the speech-recognition venv installed? Re-checked at most every 30 s."""
        ok, when = self._whisper
        if time.time() - when > 30:
            self._whisper = (ok, time.time())   # check in the background: a state poll never waits for it
            threading.Thread(target=lambda: setattr(self, "_whisper", (whisper.available(self.cfg), time.time())),
                             daemon=True).start()
        return ok

    def lyrics_time(self, b):
        """Time (or transcribe) one song's lyrics from its audio, in the background; progress in app.timing."""
        sid = _sid(b)
        song = library.get(song_id=sid) if sid is not None else None
        if not song:
            return {"ok": False, "error": "notfound"}
        if song["kind"] not in ("audio", "video"):
            return {"ok": False, "error": "kind"}
        if self.timing["running"]:
            return {"ok": False, "error": "busy"}
        if not whisper.available(self.cfg):
            return {"ok": False, "error": "unavailable"}
        lang = str(b.get("lang") or "auto")
        self.timing = {"running": True, "id": song["id"], "error": "", "result": "", "share": 0.0, "status": ""}

        def go():
            try:
                text, (what, share) = whisper.time_song(self.cfg, song, lang)
                status = self._write_lyrics(song, text)
                self.timing.update(result=what, share=round(share, 2), status=status)
                log.info("speech recognition %s %s (%.0f%% of words heard)", what, song["path"], share * 100)
            except Exception as e:
                log.exception("speech recognition failed for %s", song["path"])
                self.timing["error"] = str(e) or "failed"
            finally:
                self.timing["running"] = False
        threading.Thread(target=go, daemon=True).start()
        return {"ok": True}

    # -------------------------------------------------------------- inbox (downloads -> library)
    @staticmethod
    def _inbox_path(cfg):
        return Path(str(cfg.get("inbox") or "~/Downloads")).expanduser()

    def inbox(self):
        """What `karaokeimp` would do with the inbox folder, as data for the Inbox page."""
        from . import importer
        inbox = self._inbox_path(self.cfg)
        try:
            groups, skipped = importer.plan(inbox)
        except OSError as e:
            log.warning("inbox %s: %s", inbox, e)
            groups, skipped = [], []
        return {"inbox": str(inbox), "dest": str(importer.default_dest(self.cfg)),
                "groups": [{"name": g["name"], "kind": g.get("kind", "song"), "has_lrc": bool(g.get("has_lrc")),
                            "files": [Path(f).name for f in g["files"]]} for g in groups],
                "skipped": [Path(str(s)).name for s in skipped]}

    def inbox_import(self, b):
        """Copy the picked groups into the library in the background; progress shows in app.scan."""
        from . import importer
        if self.scan["importing"]:
            return {"ok": False, "error": "busy"}
        names = {str(n) for n in b.get("names") or []}
        try:
            groups, _ = importer.plan(self._inbox_path(self.cfg))
        except OSError as e:
            return {"ok": False, "error": str(e)}
        picked = [g for g in groups if str(g["name"]) in names]
        if not picked:
            return {"ok": False, "error": "nothing selected"}
        self.scan.update(importing=True, log=[])

        def say(msg):
            self.scan["log"] = (self.scan["log"] + [str(msg)])[-30:]

        def go():
            try:
                got = importer.import_groups(picked, importer.default_dest(self.cfg), cfg=self.cfg, say=say)
                if got:
                    say(f"imported {len(got)}: " + ", ".join(got))
                else:
                    say("nothing imported")
            except Exception as e:
                log.exception("inbox import failed")
                say(f"error: {e}")
            finally:
                self.scan["importing"] = False
                self.start_scan()
        threading.Thread(target=go, daemon=True).start()
        return {"ok": True}

    # -------------------------------------------------------------- POST /api/<action>
    def act(self, name, b):
        e, cfg = self.engine, self.cfg
        if name == "reserve":
            s = library.get(song_id=b.get("id")) if "id" in b else library.get(number=int(b.get("number", 0)))
            if not s:
                return {"ok": False, "error": "notfound"}
            e.reserve(s, bool(b.get("top")))
            return {"ok": True, "song": s}
        if name == "unqueue": e.unqueue(int(b["qid"]))
        elif name == "top": e.move_top(int(b["qid"]))
        elif name == "clear": e.clear()
        elif name == "next": e.next()
        elif name == "pause": e.pause()
        elif name == "restart": e.restart()
        elif name == "key": e.set_key(b.get("value"), int(b.get("delta", 0)))
        elif name == "tempo": e.set_tempo(b.get("value"), float(b.get("delta", 0)))
        elif name in ("melody", "chorus"): e.toggle(name)
        elif name == "volume": e.set_volume(b.get("value", cfg["volume"]) if "delta" not in b else cfg["volume"] + int(b["delta"]))
        elif name == "sync": e.set_sync(b.get("value"), float(b.get("delta", 0)))
        elif name == "sync_line":
            off = e.sync_line(int(b.get("line", -1)))
            return {"ok": off is not None, "offset": off}
        elif name == "lyrics_search": return self.lyrics_search(b)
        elif name == "lyrics_save": return self.lyrics_save(b)
        elif name == "lyrics_time": return self.lyrics_time(b)
        elif name == "inbox_import": return self.inbox_import(b)
        elif name == "fullscreen": return {"ok": self.fullscreen()}
        elif name == "display_closed": self.display_closing = time.time()
        elif name == "quit": self.quit()
        elif name == "clientlog": log.error("browser: %s", str(b.get("msg", ""))[:600])
        elif name == "scan": self.start_scan(bool(b.get("rebuild")))
        elif name == "config":
            cfg.update({k: v for k, v in b.items() if k in config.EDITABLE})
            config.save(cfg)
        elif name == "folder_add":
            p = str(Path(str(b.get("path", ""))).expanduser())
            if not os.path.isdir(p):
                return {"ok": False, "error": "notdir"}
            cfg["folders"] = [f for f in cfg["folders"] if f["path"] != p] + [
                {"path": p, "start": max(1, int(b.get("start") or 1)), "lang": b.get("lang", ""), "country": b.get("country", "")}]
            config.save(cfg)
            self.start_scan()
        elif name == "folder_del":
            cfg["folders"] = [f for f in cfg["folders"] if f["path"] != b.get("path")]
            config.save(cfg)
            self.start_scan()
        else:
            return {"ok": False, "error": "unknown"}
        return {"ok": True}

    def public_cfg(self):
        return {k: v for k, v in self.cfg.items() if k != "token"}


def handler(app):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "KuraokeKami"

        def log_message(self, *a): pass

        # ---- helpers
        def send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=()):
            if isinstance(body, str): body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in extra: self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD": self.wfile.write(body)

        def json(self, obj, code=200):
            self.send(code, json.dumps(obj, ensure_ascii=False), "application/json")

        def authed(self, q):
            tok = self.headers.get("X-Token") or (q.get("t") or [""])[0]
            return hmac.compare_digest(tok, app.cfg["token"])

        def host_ok(self):  # blocks DNS-rebinding: only IP-literal / localhost / .local hosts
            h = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            return h in app.host_ok or h.endswith(".local") or bool(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", h))

        # ---- GET
        def do_HEAD(self): self.do_GET()

        def do_GET(self):
            u = urlparse(self.path); q = parse_qs(u.query); p = u.path
            if not self.host_ok(): return self.send(403, "bad host")
            if p == "/":
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    return self.send(403, "Kuraoke Kami runs its screen on this machine.")
                page = (WEB / "index.html").read_text()
                boot = json.dumps({"token": app.cfg["token"], "display": "display" in q})
                return self.send(200, page.replace("/*BOOT*/", f"window.KK={boot};"), "text/html; charset=utf-8")
            if p.startswith("/static/"):
                f = (WEB / p[8:]).resolve()
                if WEB not in f.parents or not f.is_file(): return self.send(404, "nope")
                return self.send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            if not self.authed(q): return self.send(401, "token required")
            e = app.engine
            if p == "/api/state":
                if "d" in q:
                    app.display_last, app.display_closing = time.time(), 0.0
                s = e.state()
                s.update(scan=app.scan, cfg=app.public_cfg(), facets=library.facets() if "facets" in q else None,
                         timing=app.timing, whisper=app.whisper_ready())
                return self.json(s)
            if p == "/api/lyrics": return self.json(e.lyrics())
            if p == "/api/doctor": return self.json({"report": doctor.report(app.cfg, e)})
            if p == "/api/inbox": return self.json(app.inbox())
            if p == "/api/songs":
                rows, more = library.query((q.get("q") or [""])[0], app.cfg["lang_filter"], app.cfg["country_filter"],
                                           app.cfg["dedupe"], 100, int((q.get("offset") or ["0"])[0]),
                                           missing=(q.get("missing") or ["0"])[0] not in ("", "0"))
                return self.json({"songs": [{k: r[k] for k in ("id", "number", "title", "artist", "kind", "lang", "country", "lyrics")}
                                            for r in rows], "more": more})
            m = re.fullmatch(r"/media/(\d+)/(video|cdg)", p)
            if m:
                f = e.media(int(m[1]), m[2])
                return self.media(f, MEDIA_TYPES[m[2]]) if f else self.send(404, "no such media")
            self.send(404, "nope")

        def media(self, path, ctype):
            size = os.path.getsize(path)
            ctype = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
            a, b, code = 0, size - 1, 200
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if m and (m[1] or m[2]):
                code = 206
                if m[1]: a = int(m[1])
                if m[2]: b = min(int(m[2]), size - 1) if m[1] else size - 1
                if not m[1]: a = max(0, size - int(m[2]))
                if a > b: return self.send(416, "", extra=[("Content-Range", f"bytes */{size}")])
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(b - a + 1))
            if code == 206: self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
            self.end_headers()
            if self.command == "HEAD": return
            try:
                with open(path, "rb") as fh:
                    fh.seek(a)
                    left = b - a + 1
                    while left > 0:
                        chunk = fh.read(min(1 << 16, left))
                        if not chunk: break
                        self.wfile.write(chunk); left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        # ---- POST
        def do_POST(self):
            u = urlparse(self.path); q = parse_qs(u.query)
            if not self.host_ok(): return self.send(403, "bad host")
            if not self.authed(q): return self.send(401, "token required")
            m = re.fullmatch(r"/api/(\w+)", u.path)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n < 1 << 20 else {}
                if not m: return self.send(404, "nope")
                self.json(app.act(m[1], body))
            except (ValueError, KeyError, TypeError) as e:
                self.json({"ok": False, "error": f"bad request: {e}"}, 400)
            except Exception as e:  # a bug: log the traceback, keep the server alive
                log.exception("POST %s failed", self.path.split("?")[0])
                self.json({"ok": False, "error": f"server error: {e}"}, 500)
    return H


class Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):  # a closed tab is not an error
            log.exception("request from %s crashed", client_address[0])


def serve(cfg):
    app = App(cfg)
    try:
        httpd = Server(("127.0.0.1", cfg["port"]), handler(app))   # one TV window on this machine: nothing else connects
    except OSError:
        app.engine.mpv.close()   # port taken: leave no orphan mpv behind (a second launch just opens the screen)
        raise
    httpd.daemon_threads = True
    app.httpd = httpd
    app.migrate_offsets()
    app.start_scan()
    threading.Thread(target=app.watch_display, daemon=True).start()
    threading.Thread(target=app.watch_folders, daemon=True).start()
    return app, httpd
