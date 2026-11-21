"""Pipeline tests: lrclib matching (no network) + importer planning/moving. No ffmpeg/mpv needed.

    python3 -m unittest discover -s tests -v
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kuraoke_kami import config, importer, library, lrclib, lyrics  # noqa: E402

SYNCED = {"id": 1, "trackName": "Stupido", "artistName": "Marracash", "albumName": "Persona", "duration": 288,
          "syncedLyrics": "[00:12.00] Prima riga\n[00:20.50] Seconda\n", "plainLyrics": "Prima riga\nSeconda\n"}
PLAIN = {"id": 2, "trackName": "Stupido", "artistName": "Marracash", "duration": 290,
         "syncedLyrics": None, "plainLyrics": "Prima riga\nSeconda\n"}
FAR = {"id": 3, "trackName": "Stupido (live)", "artistName": "Marracash", "duration": 400, "plainLyrics": "x\n"}


@contextmanager
def patched(obj, **kw):
    old = {k: getattr(obj, k) for k in kw}
    for k, v in kw.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(obj, k, v)


class Resp:
    """Minimal urllib response."""

    def __init__(self, data, status=200):
        self.data = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.status = status

    def read(self): return self.data
    def __enter__(self): return self
    def __exit__(self, *a): return False


def candidate(**kw):
    c = {"id": 7, "artist": "Marracash", "title": "Stupido", "album": "Persona", "duration": 100, "delta": 0,
         "synced": False, "lyrics": "One\n\nTwo\nThree\n", "preview": []}
    c.update(kw)
    return c


class LrclibCandidates(unittest.TestCase):
    def test_rank_dedupe_and_query_order(self):
        calls = []

        def fake(path, q):
            calls.append((path, dict(q)))
            if path == "get":
                return SYNCED, None
            if "artist_name" in q:
                return [SYNCED, PLAIN, FAR], None
            if "q" in q:
                return [], None
            return [PLAIN], None

        with patched(lrclib, _get=fake):
            cands, err = lrclib.candidates("Marracash", "Stupido", 288)
        self.assertIsNone(err)
        self.assertEqual([c["id"] for c in cands], [1, 2])              # synced first, the 400 s cut dropped
        self.assertTrue(cands[0]["synced"]); self.assertFalse(cands[1]["synced"])
        self.assertEqual(cands[1]["lyrics"], PLAIN["plainLyrics"])
        self.assertEqual(cands[0]["preview"], ["Prima riga", "Seconda"])
        self.assertEqual(cands[0]["delta"], 0); self.assertEqual(cands[1]["delta"], 2)
        self.assertEqual([p for p, _ in calls], ["get", "search", "search", "search"])
        self.assertEqual(calls[0][1], {"artist_name": "Marracash", "track_name": "Stupido", "duration": 288})
        self.assertEqual(calls[1][1], {"artist_name": "Marracash", "track_name": "Stupido"})
        self.assertEqual(calls[2][1], {"q": "Marracash Stupido"})
        self.assertEqual(calls[3][1], {"track_name": "Stupido"})       # catches artist typos

    def test_synced_wins_even_when_a_plain_match_is_closer(self):
        synced = dict(SYNCED, duration=296)                            # 8 s off
        plain = dict(PLAIN, duration=288)                              # exact
        with patched(lrclib, _get=lambda p, q: (synced, None) if p == "get" else ([plain], None)):
            cands, _ = lrclib.candidates("Marracash", "Stupido", 288)
        self.assertEqual([(c["id"], c["synced"]) for c in cands], [(1, True), (2, False)])

    def test_unknown_length_keeps_everything(self):
        calls = []

        def fake(path, q):
            calls.append((path, dict(q)))
            return [dict(SYNCED, duration=1000)], None

        with patched(lrclib, _get=fake):
            cands, err = lrclib.candidates("A", "B", 0)
        self.assertIsNone(err)
        self.assertEqual(calls[0][0], "search")                        # no exact call without a length
        self.assertEqual(cands[0]["delta"], 0.0)

    def test_no_title_and_errors(self):
        with patched(lrclib, _get=lambda p, q: self.fail("no request expected")):
            self.assertEqual(lrclib.candidates("", "", 100), ([], None))
        with patched(lrclib, _get=lambda p, q: (None, "service unavailable")):
            self.assertEqual(lrclib.candidates("A", "B", 100), ([], "service unavailable"))
        with patched(lrclib, _get=lambda p, q: (None, None) if p == "get" else ([], None)):
            self.assertEqual(lrclib.candidates("A", "B", 100), ([], None))

    def test_instrumental_records_are_dropped(self):
        rec = {"id": 9, "trackName": "Song", "artistName": "X", "duration": 100, "plainLyrics": None, "syncedLyrics": None}
        with patched(lrclib, _get=lambda p, q: (rec, None) if p == "get" else ([rec], None)):
            self.assertEqual(lrclib.candidates("X", "Song", 100), ([], None))


class LrclibHttp(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        self.calls = []

    def serve(self, *responses):
        def fake(req, timeout=None):
            self.calls.append(req)
            r = responses[min(len(self.calls), len(responses)) - 1]
            if isinstance(r, Exception):
                raise r
            return Resp(r)
        return fake

    def test_404_is_no_hit_and_not_retried(self):
        url = "https://lrclib.net/api/get?x=1"
        with patched(urllib.request, urlopen=self.serve(urllib.error.HTTPError(url, 404, "nope", {}, None)),
                     ), patched(lrclib.time, sleep=self.sleeps.append):
            self.assertEqual(lrclib._get("get", {"x": 1}), (None, None))
        self.assertEqual(len(self.calls), 1); self.assertEqual(self.sleeps, [])

    def test_400_is_not_retried(self):
        url = "https://lrclib.net/api/get?x=1"
        with patched(urllib.request, urlopen=self.serve(urllib.error.HTTPError(url, 400, "bad", {}, None)),
                     ), patched(lrclib.time, sleep=self.sleeps.append):
            self.assertEqual(lrclib._get("get", {"x": 1}), (None, "HTTP 400"))
        self.assertEqual(len(self.calls), 1); self.assertEqual(self.sleeps, [])

    def test_5xx_retries_and_honours_retry_after(self):
        url = "https://lrclib.net/api/search?q=x"
        busy = urllib.error.HTTPError(url, 503, "busy", {"Retry-After": "7"}, None)
        with patched(urllib.request, urlopen=self.serve(busy, busy, {"id": 9})), patched(lrclib.time, sleep=self.sleeps.append):
            self.assertEqual(lrclib._get("search", {"q": "x"}), ({"id": 9}, None))
        self.assertEqual(self.sleeps, [7, 7])
        self.assertEqual(self.calls[0].get_header("User-agent"), lrclib.UA)

    def test_timeouts_retry_then_give_up(self):
        with patched(urllib.request, urlopen=self.serve(TimeoutError("slow"), TimeoutError("slow"), TimeoutError("slow")),
                     ), patched(lrclib.time, sleep=self.sleeps.append):
            self.assertEqual(lrclib._get("search", {"q": "x"}), (None, "service unavailable"))
        self.assertEqual(self.sleeps, [2, 4])

    def test_bad_json_is_not_retried(self):
        with patched(urllib.request, urlopen=self.serve(b"<html>not json</html>")), patched(lrclib.time, sleep=self.sleeps.append):
            self.assertEqual(lrclib._get("search", {"q": "x"}), (None, "bad response"))
        self.assertEqual(len(self.calls), 1)


class LrclibLrc(unittest.TestCase):
    def test_plausible(self):
        self.assertTrue(lrclib.plausible("[00:10.00] a\n[03:00.00] b\n", 200))    # ends 20 s before the file
        self.assertTrue(lrclib.plausible("[00:37.72] a\n[03:04.00] b\n", 243))   # Midnight City: 59 s sax outro is fine
        self.assertTrue(lrclib.plausible("[00:10.00] a\n[01:41.00] b\n", 200))   # just past halfway
        self.assertFalse(lrclib.plausible("[00:10.00] a\n[03:30.00] b\n", 200))   # starts after the file ends
        self.assertFalse(lrclib.plausible("[00:10.00] a\n[02:00.00] b\n", 288))   # stops before halfway: another cut
        self.assertTrue(lrclib.plausible("no stamps at all\n", 200))
        self.assertTrue(lrclib.plausible("[04:40.00] last\n", 0))

    def test_plain_only_is_spread_and_flagged(self):
        text = lrclib.to_lrc(candidate(), 100)
        for tag in ("[ar:Marracash]", "[ti:Stupido]", "[al:Persona]", "[length:01:40]", "[re:lrclib #7]", "[kk:untimed]", "[kk:suspect]"):
            self.assertIn(tag, text)
        self.assertNotIn("[offset:", text)
        lines = lyrics.parse_lrc(text)
        self.assertEqual(["".join(w for _, _, w in l).strip() for l in lines], ["One", "Two", "Three"])
        self.assertEqual([round(l[0][0]) for l in lines], [8, 50, 92])          # 8% .. 92% of 100 s

    def test_plain_without_length_uses_four_seconds_a_line(self):
        lines = lyrics.parse_lrc(lrclib.to_lrc(candidate(), 0))
        self.assertEqual([round(l[0][0]) for l in lines], [4, 8, 12])
        self.assertNotIn("[length:", lrclib.to_lrc(candidate(), 0))

    def test_synced_kept_verbatim_unless_implausible(self):
        good = candidate(synced=True, lyrics="[00:12.00] a\n[04:30.00] b\n")     # dur 288: last line 270
        text = lrclib.to_lrc(good, 288)
        self.assertIn("[00:12.00] a", text)
        self.assertNotIn("[kk:", text)
        outro = candidate(synced=True, lyrics="[00:12.00] a\n[03:48.00] b\n")    # dur 288: 60 s outro is normal
        self.assertNotIn("[kk:", lrclib.to_lrc(outro, 288))
        bad = candidate(synced=True, lyrics="[00:12.00] a\n[02:00.00] b\n")      # dur 288: stops before halfway
        self.assertIn("[kk:suspect]", lrclib.to_lrc(bad, 288))
        self.assertNotIn("[kk:untimed]", lrclib.to_lrc(bad, 288))

    def test_find_info_strings(self):
        def find(records, dur=288):
            with patched(lrclib, _get=lambda p, q: (records[0], None) if p == "get" else (records, None)):
                return lrclib.find("Marracash", "Stupido", dur)

        good = dict(SYNCED, syncedLyrics="[00:12.00] Prima riga\n[04:30.00] Seconda\n")
        text, info = find([good])
        self.assertEqual(info, "Marracash - Stupido"); self.assertIn("[ar:Marracash]", text)
        text, info = find([dict(SYNCED, syncedLyrics=None)])
        self.assertEqual(info, "Marracash - Stupido (untimed)")
        text, info = find([SYNCED])                                       # ends 20 s in: 268 s of silence
        self.assertEqual(info, "Marracash - Stupido (suspect)")
        self.assertEqual(find([FAR])[0], None)                                  # 112 s off
        with patched(lrclib, _get=lambda p, q: (None, None)):
            self.assertEqual(lrclib.find("A", "B", 100), (None, "no match"))
        with patched(lrclib, _get=lambda p, q: (None, "service unavailable")):
            self.assertEqual(lrclib.find("A", "B", 100), (None, "service unavailable"))

    def test_find_never_picks_another_singer(self):
        good = dict(SYNCED, syncedLyrics="[00:12.00] Prima riga\n[04:30.00] Seconda\n")
        other = dict(good, artistName="Miach")
        with patched(lrclib, _get=lambda p, q: (other, None) if p == "get" else ([other], None)):
            self.assertEqual(lrclib.find("Marracash", "Stupido", 288), (None, "no match"))
        with patched(lrclib, _get=lambda p, q: (good, None) if p == "get" else ([good], None)):
            self.assertEqual(lrclib.find("Marracasch", "Stupido", 288)[1], "Marracash - Stupido")   # typo in the name
        self.assertTrue(lrclib.same_artist("Fedezz", "Fedez"))
        self.assertFalse(lrclib.same_artist("Coma Cose", "Miach"))

    def test_null_album_text_is_dropped(self):
        rec = dict(SYNCED, albumName="null", syncedLyrics="[00:12.00] a\n[04:30.00] b\n")
        with patched(lrclib, _get=lambda p, q: (rec, None) if p == "get" else ([rec], None)):
            c = lrclib.candidates("Marracash", "Stupido", 288)[0][0]
        self.assertEqual(c["album"], "")
        self.assertNotIn("[al:", lrclib.to_lrc(c, 288))


class Importer(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cfg = (config.CFG_DIR, config.CFG_FILE, config.DATA_DIR, config.DB_FILE)
        config.CFG_DIR = self.tmp / "cfg"
        config.CFG_FILE = config.CFG_DIR / "config.json"
        config.DATA_DIR = self.tmp / "data"
        config.DB_FILE = config.DATA_DIR / "lib.db"
        self._tags, self._net = importer.tags, (lrclib.find, lrclib.length)
        importer.tags = lambda p: (None, None)          # no ffprobe in tests
        lrclib.find, lrclib.length = lambda *a: (None, "no match"), lambda p: 100.0   # no network
        self.inbox = self.tmp / "inbox"
        self.inbox.mkdir()
        self.dest = self.tmp / "lib"

    def tearDown(self):
        config.CFG_DIR, config.CFG_FILE, config.DATA_DIR, config.DB_FILE = self._cfg
        importer.tags = self._tags
        lrclib.find, lrclib.length = self._net

    def make(self, *names):
        for n in names:
            (self.inbox / n).write_bytes(b"x")

    def test_plan_groups_pairs_and_kinds(self):
        self.make("Artist - Song.mp3", "Artist - Song.lrc",
                  "Other - Tune.mp3", "Other - Tune (lyrics).lrc",
                  "Disc - Cdg.mp3", "Disc - Cdg.cdg",
                  "junk.mp3", "lonely.lrc")
        chorus = self.inbox / "Chart Dude - Chorus Song"
        chorus.mkdir()
        (chorus / "song.ini").write_text("[song]\nname = Chorus Song\nartist = Chart Dude\n")
        (chorus / "notes.mid").write_bytes(b"x")
        groups, skipped = importer.plan(self.inbox)
        by_name = {g["name"]: g for g in groups}
        self.assertEqual(set(by_name), {"Artist - Song", "Other - Tune", "Disc - Cdg", "Chart Dude - Chorus Song"})
        self.assertEqual(by_name["Artist - Song"]["kind"], "song")
        self.assertTrue(by_name["Artist - Song"]["has_lrc"])
        self.assertEqual({f.suffix for f in by_name["Artist - Song"]["files"]}, {".mp3", ".lrc"})
        self.assertTrue(by_name["Other - Tune"]["has_lrc"])             # 'X (lyrics).lrc' pairs with 'X.mp3'
        self.assertEqual(by_name["Disc - Cdg"]["kind"], "cdg")
        self.assertTrue(by_name["Disc - Cdg"]["has_lrc"])               # CDG draws its own lyrics
        self.assertEqual(by_name["Chart Dude - Chorus Song"]["kind"], "chorus")
        self.assertTrue(by_name["Chart Dude - Chorus Song"]["dir"])
        self.assertTrue(by_name["Chart Dude - Chorus Song"]["has_lrc"])
        self.assertEqual(skipped, [self.inbox / "junk.mp3"])            # no 'Artist - Title'
        self.assertEqual(len(by_name["Artist - Song"]["files"]), 2)     # the lone .lrc is dropped

    def test_import_moves_fetches_lyrics_but_never_for_cdg(self):
        self.make("Solo - Tune.mp3", "Disc - Cdg.mp3", "Disc - Cdg.cdg", "Done - Song.mp3", "Done - Song.lrc",
                  "Dual - Format.mp3", "Dual - Format.mp4")
        looked = []

        def fake_find(artist, title, dur):
            looked.append((artist, title, dur))
            return "[ar:X]\n[00:05.00] Hi\n", "X - Y"

        groups, _ = importer.plan(self.inbox)
        said = []
        with patched(lrclib, find=fake_find, length=lambda p: 100.0):
            done = importer.import_groups(groups, self.dest, say=said.append)
        self.assertEqual(sorted(done), ["Disc - Cdg", "Done - Song", "Dual - Format", "Solo - Tune"])
        self.assertEqual(looked, [("Dual", "Format", 100.0), ("Solo", "Tune", 100.0)])   # once per song, not per format
        self.assertEqual(sorted(f.suffix for f in self.dest.iterdir() if f.stem == "Dual - Format"), [".lrc", ".mp3", ".mp4"])
        self.assertTrue((self.dest / "Solo - Tune.mp3").exists())
        self.assertTrue((self.dest / "Disc - Cdg.cdg").exists())
        self.assertTrue((self.dest / "Done - Song.lrc").exists())
        self.assertEqual((self.dest / "Solo - Tune.lrc").read_text(), "[ar:X]\n[00:05.00] Hi\n")
        self.assertFalse((self.inbox / "Solo - Tune.mp3").exists())     # moved, not copied
        self.assertIn("  Solo - Tune: lyrics saved (X - Y)", said)
        self.assertEqual([m for m in said].count("  Dual - Format: lyrics saved (X - Y)"), 1)

    def test_import_skips_what_is_already_there(self):
        self.make("Artist - Tune.mp3")
        self.dest.mkdir()
        (self.dest / "Artist - Tune.mp3").write_bytes(b"old")
        groups, _ = importer.plan(self.inbox)
        said = []
        self.assertEqual(importer.import_groups(groups, self.dest, say=said.append), [])
        self.assertEqual((self.dest / "Artist - Tune.mp3").read_bytes(), b"old")   # never overwritten
        self.assertTrue((self.inbox / "Artist - Tune.mp3").exists())
        self.assertIn("skip (already in library): Artist - Tune", said)

    def test_import_skips_the_same_song_under_another_name(self):
        con = library.db()
        con.execute("INSERT INTO songs(number,path,root,kind,title,artist,lang,country,nkey,prio)"
                    " VALUES(10000,?,?,'audio',?,?,'','',?,5)",
                    (str(self.tmp / "old.mp3"), str(self.tmp), "Come Finirà", "Fabri Fibra",
                     library.norm("Come Finirà", "Fabri Fibra")))
        con.commit()
        con.close()
        self.make("Fabri Fibra - Come Finirà (Live).mp3")               # same song, another file name
        groups, _ = importer.plan(self.inbox)
        said = []
        self.assertEqual(importer.import_groups(groups, self.dest, say=said.append), [])
        self.assertTrue((self.inbox / "Fabri Fibra - Come Finirà (Live).mp3").exists())
        self.assertIn("skip (already in library): Fabri Fibra - Come Finirà (Live)", said)

    def test_import_copy_keeps_source_and_whole_folders(self):
        chorus = self.inbox / "Chart Dude - Chorus Song"
        chorus.mkdir()
        (chorus / "song.ini").write_text("[song]\nname = Chorus Song\nartist = Chart Dude\n")
        (chorus / "notes.mid").write_bytes(b"x")
        (chorus / "song.ogg").write_bytes(b"x")
        self.make("Copy - Me.mp3")
        groups, _ = importer.plan(self.inbox)
        self.assertEqual(importer.import_groups(groups, self.dest, copy=True, say=lambda m: None),
                         ["Chart Dude - Chorus Song", "Copy - Me"])
        self.assertTrue((self.inbox / "Copy - Me.mp3").exists())
        self.assertTrue((self.inbox / "Chart Dude - Chorus Song" / "song.ogg").exists())
        self.assertTrue((self.dest / "Copy - Me.mp3").exists())
        self.assertTrue((self.dest / "Chart Dude - Chorus Song" / "song.ogg").exists())

    def test_no_lyrics_flag(self):
        self.make("Solo - Tune.mp3")
        groups, _ = importer.plan(self.inbox)
        with patched(lrclib, find=lambda *a: self.fail("lookup should be skipped")):
            self.assertEqual(importer.import_groups(groups, self.dest, fetch_lyrics=False), ["Solo - Tune"])
        self.assertFalse((self.dest / "Solo - Tune.lrc").exists())

    def test_ensure_folder_and_default_dest(self):
        cfg = {"folders": []}
        self.assertTrue(importer.ensure_folder(cfg, self.dest, "tl", "PH"))
        self.assertEqual(cfg["folders"], [{"path": str(self.dest), "start": 10000, "lang": "tl", "country": "PH"}])
        self.assertEqual(json.loads(config.CFG_FILE.read_text())["folders"][0]["path"], str(self.dest))
        self.assertFalse(importer.ensure_folder(cfg, self.dest))                    # same folder
        self.assertFalse(importer.ensure_folder(cfg, self.dest / "sub"))            # covered by a parent
        cfg = {"folders": [{"path": str(self.tmp / "a"), "start": 20000, "lang": "", "country": ""}]}
        self.assertTrue(importer.ensure_folder(cfg, self.dest))
        self.assertEqual(cfg["folders"][-1]["start"], 30000)
        self.assertEqual(importer.default_dest({"folders": [{"path": "~/Music/K"}]}), Path("~/Music/K").expanduser())
        self.assertEqual(importer.default_dest({}), importer.ROOT / "songs")

    def test_notify_running_app(self):
        seen = {}

        class R:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def ok(req, timeout=None):
            seen.update(url=req.full_url, token=req.get_header("X-token"), method=req.get_method(), timeout=timeout)
            return R()

        with patched(urllib.request, urlopen=ok):
            self.assertTrue(importer.notify_running_app({"port": 1234, "token": "tok"}))
        self.assertEqual(seen, {"url": "http://127.0.0.1:1234/api/scan", "token": "tok", "method": "POST", "timeout": 1})
        with patched(urllib.request, urlopen=lambda req, timeout=None: (_ for _ in ()).throw(urllib.error.URLError("refused"))):
            self.assertFalse(importer.notify_running_app({"port": 1234, "token": "tok"}))


class FetchLrc(unittest.TestCase):
    """tools/fetch_lrc.py: configured folders by default, audio + video, skips what has lyrics already."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cfg = (config.CFG_DIR, config.CFG_FILE, config.DATA_DIR, config.DB_FILE)
        config.CFG_DIR = self.tmp / "cfg"
        config.CFG_FILE = config.CFG_DIR / "config.json"
        config.DATA_DIR = self.tmp / "data"
        config.DB_FILE = config.DATA_DIR / "lib.db"
        self._net = (lrclib.find, lrclib.length)
        self.folder = self.tmp / "songs"
        self.folder.mkdir()
        (self.folder / "Artist - Song.mp3").write_bytes(b"x")
        (self.folder / "Artist - Done.mp3").write_bytes(b"x")
        (self.folder / "Artist - Done.lrc").write_text("[00:01.00] hi\n")
        (self.folder / "Disc - Cdg.mp3").write_bytes(b"x")
        (self.folder / "Disc - Cdg.cdg").write_bytes(b"x")
        (self.folder / "Video - Star.mp4").write_bytes(b"x")
        chorus = self.folder / "Chart Dude - Chorus Song"
        chorus.mkdir()
        (chorus / "song.ini").write_text("[song]\nname = Chorus Song\nartist = Chart Dude\n")
        (chorus / "vocals.ogg").write_bytes(b"x")
        config.CFG_DIR.mkdir(parents=True)
        config.CFG_FILE.write_text(json.dumps({"token": "t", "folders": [
            {"path": str(self.folder), "start": 10000, "lang": "", "country": ""}]}))
        con = library.db()
        con.execute("INSERT INTO songs(number,path,root,kind,title,artist,lang,country,nkey,prio)"
                    " VALUES(10000,?,'','audio','Song','Artist','','','artistsong',5)", (str(self.folder / "Artist - Song.mp3"),))
        con.commit()
        con.close()
        self.looked = []
        lrclib.find = lambda artist, title, dur: (self.looked.append((artist, title, dur))
                                                 or ("[ar:X]\n[00:05.00] Hi\n", "X - Y"))
        lrclib.length = lambda p: 100.0
        spec = importlib.util.spec_from_file_location("kk_fetch_lrc", ROOT / "tools" / "fetch_lrc.py")
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def tearDown(self):
        config.CFG_DIR, config.CFG_FILE, config.DATA_DIR, config.DB_FILE = self._cfg
        lrclib.find, lrclib.length = self._net

    def test_defaults_to_configured_folders_and_audio_video(self):
        notified = []
        out = io.StringIO()
        with patched(importer, notify_running_app=lambda cfg: notified.append(cfg) or True), redirect_stdout(out):
            self.tool.main(["tools/fetch_lrc.py"])                     # no folder: use cfg["folders"]
        self.assertEqual(sorted(self.looked), [("Artist", "Song", 100.0), ("Video", "Star", 100.0)])
        self.assertTrue((self.folder / "Artist - Song.lrc").is_file())
        self.assertTrue((self.folder / "Video - Star.lrc").is_file())
        self.assertFalse((self.folder / "Disc - Cdg.lrc").exists())    # CDG draws its own words
        self.assertFalse((self.folder / "Chart Dude - Chorus Song" / "vocals.lrc").exists())
        self.assertEqual((self.folder / "Artist - Done.lrc").read_text(), "[00:01.00] hi\n")   # untouched
        self.assertIn("the open app updates by itself", out.getvalue())
        self.assertEqual(len(notified), 1)
        con = library.db()
        self.assertEqual(con.execute("SELECT lyrics FROM songs WHERE title='Song'").fetchone()[0], "line")
        con.close()


class ImportSongsCli(unittest.TestCase):
    """The CLI is a thin shell over importer; run it in-process so nothing can reach the network."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cfg = (config.CFG_DIR, config.CFG_FILE, config.DATA_DIR, config.DB_FILE)
        config.CFG_DIR = self.tmp / "cfg"
        config.CFG_FILE = config.CFG_DIR / "config.json"
        config.DATA_DIR = self.tmp / "data"
        config.DB_FILE = config.DATA_DIR / "lib.db"
        self._tags, self._net = importer.tags, (lrclib.find, lrclib.length)
        importer.tags = lambda p: (None, None)
        lrclib.find, lrclib.length = lambda *a: (None, "no match"), lambda p: 100.0   # no network
        self.inbox = self.tmp / "box"
        self.inbox.mkdir()
        (self.inbox / "Artist - Song.mp3").write_bytes(b"x")
        (self.inbox / "Notaname.mp3").write_bytes(b"x")
        self.dest = self.tmp / "lib"
        spec = importlib.util.spec_from_file_location("kk_import_songs", ROOT / "tools" / "import_songs.py")
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)

    def tearDown(self):
        config.CFG_DIR, config.CFG_FILE, config.DATA_DIR, config.DB_FILE = self._cfg
        lrclib.find, lrclib.length = self._net
        importer.tags = self._tags

    def run_cli(self, *args):
        out = io.StringIO()
        with patched(sys, argv=[str(ROOT / "tools" / "import_songs.py"), *args]), redirect_stdout(out):
            self.cli.main()
        return out.getvalue()

    def test_help(self):
        env = dict(os.environ, XDG_CONFIG_HOME=str(self.tmp / "c"), XDG_DATA_HOME=str(self.tmp / "d"),
                   XDG_CACHE_HOME=str(self.tmp / "ca"), XDG_STATE_HOME=str(self.tmp / "s"))
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "import_songs.py"), "--help"],
                           capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("usage:", r.stdout.lower())
        self.assertIn("--dry-run", r.stdout)

    def test_dry_run_changes_nothing(self):
        with patched(importer, tags=lambda p: (None, None)):
            out = self.run_cli(str(self.inbox), "--dest", str(self.dest), "--dry-run")
        self.assertIn("Artist - Song   [.mp3]", out)
        self.assertIn("?? Notaname.mp3", out)
        self.assertIn("Nothing changed.", out)
        self.assertTrue((self.inbox / "Artist - Song.mp3").exists())
        self.assertFalse(self.dest.exists())

    def test_import_registers_scans_and_notifies(self):
        notified = []
        with patched(importer, tags=lambda p: (None, None),
                     notify_running_app=lambda cfg: notified.append(cfg) or True):
            out = self.run_cli(str(self.inbox), "--dest", str(self.dest), "--no-lyrics", "--yes")
        self.assertTrue((self.dest / "Artist - Song.mp3").exists())
        self.assertFalse((self.inbox / "Artist - Song.mp3").exists())
        self.assertIn(f"registered {self.dest}", out)
        self.assertIn("Now in the song book:", out)
        self.assertIn("10000", out)                                     # first folder starts at 10000
        self.assertIn("the open app updates by itself", out)
        self.assertEqual(len(notified), 1)


if __name__ == "__main__":
    unittest.main()
