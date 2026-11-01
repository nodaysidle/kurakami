"""HTTP server: serves the web UI, a small JSON API (also used by phone remotes) and range-capable media."""
import hmac
import json
import mimetypes
import os
import re
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config, library
from .engine import Engine

WEB = Path(__file__).resolve().parent.parent / "web"
MEDIA_TYPES = {"video": None, "cdg": "application/octet-stream"}


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class App:
    def __init__(self, cfg):
        self.cfg, self.engine = cfg, Engine(cfg)
        self.scan = {"running": False, "count": 0, "error": ""}
        self.host_ok = {"localhost", "127.0.0.1", "::1", lan_ip(), socket.gethostname().lower()}

    def remote_url(self):
        return f"http://{lan_ip()}:{self.cfg['port']}/?t={self.cfg['token']}"

    # -------------------------------------------------------------- scanning
    def start_scan(self, rebuild=False):
        if self.scan["running"]:
            return
        self.scan.update(running=True, count=0, error="")

        def go():
            try:
                library.scan(self.cfg, rebuild, lambda n: self.scan.update(count=n))
            except Exception as e:
                self.scan["error"] = str(e)
            self.scan["running"] = False
        threading.Thread(target=go, daemon=True).start()

    # -------------------------------------------------------------- fullscreen (Hyprland)
    def fullscreen(self):
        try:
            cl = json.loads(subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=3).stdout)
            w = next(c for c in cl if c["title"].startswith("Kuraoke Kami"))
            subprocess.run(["hyprctl", "--batch", f"dispatch focuswindow address:{w['address']} ; dispatch fullscreen 0"],
                           capture_output=True, timeout=3)
            return True
        except (OSError, StopIteration, ValueError, subprocess.SubprocessError):
            return False  # the page falls back to the browser Fullscreen API

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
        elif name == "fullscreen": return {"ok": self.fullscreen()}
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
            loop = self.client_address[0] in ("127.0.0.1", "::1")
            if p == "/":
                if not (loop or self.authed(q)): return self.send(403, "Open the remote link shown on the TV (it contains the access token).")
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
                s = e.state()
                s.update(scan=app.scan, remote=app.remote_url(), cfg=app.public_cfg(), facets=library.facets() if "facets" in q else None)
                return self.json(s)
            if p == "/api/lyrics": return self.json(e.lyrics())
            if p == "/api/songs":
                rows, more = library.query((q.get("q") or [""])[0], app.cfg["lang_filter"], app.cfg["country_filter"],
                                           app.cfg["dedupe"], 100, int((q.get("offset") or ["0"])[0]))
                return self.json({"songs": [{k: r[k] for k in ("id", "number", "title", "artist", "kind", "lang", "country")} for r in rows], "more": more})
            if p == "/api/qr.svg":
                r = subprocess.run(["qrencode", "-t", "SVG", "-m", "1", "-o", "-", app.remote_url()], capture_output=True)
                return self.send(200 if r.returncode == 0 else 404, r.stdout, "image/svg+xml")
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
    return H


def serve(cfg):
    app = App(cfg)
    host = "0.0.0.0" if cfg["remote"] else "127.0.0.1"
    httpd = ThreadingHTTPServer((host, cfg["port"]), handler(app))
    httpd.daemon_threads = True
    return app, httpd
