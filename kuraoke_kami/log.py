"""One rotating log file (~/.local/state/kuraoke-kami/kuraoke.log). `kuraoke-kami --doctor` and Settings show its errors."""
import logging
import logging.handlers
import sys
import threading

from . import config

log = logging.getLogger("kk")


def setup():
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(config.LOG_FILE, maxBytes=500_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    sys.excepthook = lambda *a: log.error("uncaught exception", exc_info=a)
    threading.excepthook = lambda a: log.error("thread %s crashed", a.thread.name, exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def tail(n=40, only_errors=False):
    try:
        lines = config.LOG_FILE.read_text(errors="replace").splitlines()
    except OSError:
        return []
    if only_errors:  # keep ERROR lines and the traceback lines after them
        keep, on = [], False
        for ln in lines:
            on = " ERROR " in ln[:40] or (on and not ln[:4].isdigit())
            if on:
                keep.append(ln)
        lines = keep
    return lines[-n:]
