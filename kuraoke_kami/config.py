"""Preferences: one JSON file, saved on every change."""
import json
import os
import secrets
import threading
from pathlib import Path

_h = Path.home()
CFG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", _h / ".config")) / "kuraoke-kami"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", _h / ".local/share")) / "kuraoke-kami"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", _h / ".cache")) / "kuraoke-kami"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", _h / ".local/state")) / "kuraoke-kami"
LOG_FILE = STATE_DIR / "kuraoke.log"
CFG_FILE = CFG_DIR / "config.json"
DB_FILE = DATA_DIR / "library.db"

DEFAULTS = {
    "lang": "en",            # UI language: en | tl
    "folders": [],           # {path, start, lang, country}
    "lang_filter": [],       # empty = show all
    "country_filter": [],
    "dedupe": False,
    "volume": 80,
    "melody": False,         # guide-vocal layer audible by default?
    "chorus": True,          # backing-vocal layer audible by default?
    "remote": True,          # listen on the LAN
    "port": 8890,
    "soundfont": "",
    "intro": 5,              # seconds of intro screen
    "offsets": {},           # song path -> seconds the lyrics are shifted later (+) or earlier (-)
    "token": "",
}
# keys the web UI may change through /api/config
EDITABLE = {"lang", "lang_filter", "country_filter", "dedupe", "volume", "melody", "chorus",
            "remote", "port", "soundfont", "intro"}

_lock = threading.Lock()


def load():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CFG_FILE.read_text()))
    except (OSError, ValueError):
        pass
    if not cfg["token"]:
        cfg["token"] = secrets.token_urlsafe(12)
        save(cfg)
    return cfg


def save(cfg):
    with _lock:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CFG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
        os.chmod(tmp, 0o600)  # holds the remote token
        tmp.replace(CFG_FILE)
