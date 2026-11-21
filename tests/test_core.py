"""Run: python3 -m unittest discover -s tests -v   (no ffmpeg/mpv needed)."""
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kuraoke_kami import config, library, lyrics  # noqa: E402
from kuraoke_kami.player import graph  # noqa: E402
import fixtures  # noqa: E402

WORDS = [(0, "Hel"), (480, "lo "), (960, "to "), (1440, "the "), (1920, "/Kar"), (2400, "a"), (2640, "o"), (2880, "ke ")]


def text(line): return "".join(x for _, _, x in line)


class Lyrics(unittest.TestCase):
    def check_midi(self, kar):
        div, tr = lyrics.read_smf(fixtures.midi(WORDS, kar=kar))
        lines = lyrics.midi_lyrics(div, tr)
        self.assertEqual([text(l) for l in lines], ["Hello to the ", "Karaoke "])
        self.assertAlmostEqual(lines[0][1][0], 0.5)       # 480 ticks @120bpm
        self.assertAlmostEqual(lines[0][0][1], 0.5)       # a word ends where the next starts

    def test_midi_lyric_events(self): self.check_midi(False)
    def test_kar_text_events(self): self.check_midi(True)

    def test_midi_stems(self):
        div, tr = lyrics.read_smf(fixtures.midi(WORDS))
        g = lyrics.midi_groups(tr)
        self.assertEqual(g, ["base", "melody", "base", "chorus"])
        parts = lyrics.split_midi(div, tr, g)
        self.assertEqual(set(parts), {"base", "melody", "chorus"})
        for name, data in parts.items():
            _, t2 = lyrics.read_smf(data)
            have = [any(lyrics.is_note(e) for e in x) for x in t2]
            self.assertEqual(have, [k in {"base": (2,), "melody": (1,), "chorus": (3,)}[name] for k in range(4)])
        self.assertEqual(lyrics.midi_groups(lyrics.read_smf(fixtures.midi(WORDS, melody_name="Track 2", chorus=False))[1]), ["base"] * 3)

    def test_chorus_vocals(self):
        voc = [fixtures.meta(0, 3, b"PART VOCALS"), (0, 0x90, 0, bytes([105, 9])), (900, 0x80, 0, bytes([105, 0]))]
        voc += [fixtures.meta(t, 5, x.encode()) for t, x in [(0, "Sing-"), (240, "ing "), (480, "a "), (720, "+"), (1000, "Next"), (1300, "[x]")]]
        voc += [(1000, 0x90, 0, bytes([105, 9]))]
        lines = lyrics.chorus_mid_lyrics(480, [[fixtures.meta(0, 0x2F, b"")], voc])
        self.assertEqual([text(l) for l in lines], ["Sing" + "ing " + "a ", "Next "])

    def test_chart(self):
        c = '[Song]\n{\n  Resolution = 192\n}\n[SyncTrack]\n{\n  0 = B 120000\n}\n[Events]\n{\n  0 = E "phrase_start"\n  0 = E "lyric Hi-"\n  192 = E "lyric there"\n  400 = E "phrase_start"\n  400 = E "lyric Bye"\n}\n'
        lines = lyrics.chart_lyrics(c)
        self.assertEqual([text(l) for l in lines], ["Hithere ", "Bye "])
        self.assertAlmostEqual(lines[0][1][0], 0.5)

    def test_lrc(self):
        plain = lyrics.parse_lrc("[00:01.50]Hello world\n[00:05.00]Bye\n")
        self.assertEqual([text(l) for l in plain], ["Hello world ", "Bye "])
        enh = lyrics.parse_lrc("[00:01.00]<00:01.00>Hello <00:02.00>mp3\n[00:05.00]<00:05.00>Again\n")
        self.assertEqual([text(l) for l in enh], ["Hello mp3", "Again"])
        self.assertAlmostEqual(enh[0][1][0], 2.0)


class Library(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        config.DATA_DIR, config.DB_FILE = self.tmp / "data", self.tmp / "data" / "lib.db"
        self.a, self.b = self.tmp / "a", self.tmp / "b"
        for d in (self.a, self.b): d.mkdir()
        for f in ("Abba - Waterloo.mp3", "Abba - Waterloo.mp4", "Abba - Waterloo.mid", "Zed - Song.mp3", "Zed - Song.cdg", "Solo.mp3", "orphan.cdg", "notes.txt"):
            (self.a / f).write_bytes(b"x")
        (self.b / "Rico - Ang Kanta.mid").write_bytes(b"x")
        c = self.a / "pack" / "Band - Chart"; c.mkdir(parents=True)
        (c / "song.ini").write_text("[song]\nname = Chart Name\nartist = Chart Band\n"); (c / "song.ogg").write_bytes(b"x")
        self.cfg = {"folders": [{"path": str(self.a), "start": 1000, "lang": "en", "country": "US"},
                                {"path": str(self.b), "start": 50000, "lang": "tl", "country": "PH"}]}

    def test_scan_and_numbers(self):
        self.assertEqual(library.scan(self.cfg), 7)  # 3 waterloo + zed(cdg) + solo + chorus + rico; orphan.cdg/notes.txt/zed.mp3 are skipped
        rows, _ = library.query()
        kinds = {r["path"].rsplit("/", 1)[-1]: r["kind"] for r in rows}
        self.assertEqual(kinds["Zed - Song.cdg"], "cdg"); self.assertNotIn("Zed - Song.mp3", kinds); self.assertNotIn("orphan.cdg", kinds)
        self.assertEqual(kinds["Band - Chart"], "chorus")
        nums = {r["path"]: r["number"] for r in rows}
        self.assertTrue(all(1000 <= n < 1100 for p, n in nums.items() if "Rico" not in p))
        self.assertEqual(library.get(number=50000)["title"], "Ang Kanta")
        (self.a / "New - Late.mp3").write_bytes(b"x")                     # rescan keeps numbers, new song gets the next one
        library.scan(self.cfg)
        again = {r["path"]: r["number"] for r in library.query()[0]}
        self.assertEqual({k: v for k, v in again.items() if k in nums}, nums)
        self.assertEqual(again[str(self.a / "New - Late.mp3")], max(v for k, v in nums.items() if "Rico" not in k) + 1)
        (self.a / "Solo.mp3").unlink()                                    # vanished files leave the book
        library.scan(self.cfg)
        self.assertNotIn("Solo", {r["title"] for r in library.query()[0]})

    def test_search_filter_dedupe(self):
        library.scan(self.cfg)
        self.assertEqual({r["title"] for r in library.query("water")[0]}, {"Waterloo"})
        self.assertEqual(library.query("50000")[0][0]["title"], "Ang Kanta")
        self.assertEqual(len(library.query("waterloo")[0]), 3)
        d = library.query("waterloo", dedupe=True)[0]
        self.assertEqual([r["kind"] for r in d], ["video"])               # best format wins
        self.assertEqual({r["lang"] for r in library.query(langs=["tl"])[0]}, {"tl"})
        self.assertEqual({r["country"] for r in library.query(countries=["US"])[0]}, {"US"})
        self.assertEqual(library.get(number=50000)["title"], "Ang Kanta")

    def test_rebuild_renumbers(self):
        library.scan(self.cfg)
        self.cfg["folders"][0]["start"] = 7000
        library.scan(self.cfg, rebuild=True)
        self.assertTrue(all(7000 <= r["number"] < 7100 for r in library.query(langs=["en"])[0]))

    def test_lyrics_columns(self):
        (self.a / "Abba - Waterloo.lrc").write_text("[00:01.00]Water\n")
        self.assertEqual(library.scan(self.cfg), 7)
        rows = {r["path"].rsplit("/", 1)[-1]: r for r in library.query(limit=100)[0]}
        self.assertEqual(rows["Abba - Waterloo.mp3"]["lyrics"], "line")
        self.assertEqual(rows["Abba - Waterloo.mp4"]["lyrics"], "line")      # same stem: one .lrc for both
        self.assertEqual(rows["Abba - Waterloo.mid"]["lyrics"], "embedded")
        self.assertEqual(rows["Zed - Song.cdg"]["lyrics"], "cdg")
        self.assertEqual(rows["Solo.mp3"]["lyrics"], "none")
        self.assertEqual(rows["Band - Chart"]["lyrics"], "none")             # chorus folder without notes.*
        self.assertEqual(rows["Rico - Ang Kanta.mid"]["lyrics"], "embedded")
        mp3 = rows["Abba - Waterloo.mp3"]
        self.assertEqual(mp3["size"], 1)
        self.assertEqual(mp3["mtime"], os.stat(mp3["path"]).st_mtime)

    def test_missing_filter_and_facets(self):
        (self.a / "Abba - Waterloo.lrc").write_text("[00:01.00]Water\n")
        (self.a / "Solo.lrc").write_text("[kk:suspect]\n[00:01.00]Hi\n")
        library.scan(self.cfg)
        rows, more = library.query(missing=True, limit=100)
        self.assertFalse(more)
        self.assertEqual({r["path"].rsplit("/", 1)[-1] for r in rows}, {"Solo.mp3", "Band - Chart"})
        self.assertEqual({r["lyrics"] for r in rows}, {"suspect", "none"})
        f = library.facets()
        self.assertEqual((f["total"], f["missing"]), (7, 2))
        self.assertEqual(len(library.query(limit=100)[0]), 7)                # nothing hidden unless asked
        self.assertEqual(len(library.query(missing=False, limit=100)[0]), 7)

    def test_refresh_after_lrc_write(self):
        library.scan(self.cfg)
        self.assertEqual(library.query("solo")[0][0]["lyrics"], "none")
        (self.a / "Solo.lrc").write_text("[00:01.00]Hi\n")
        self.assertEqual(library.refresh(self.a / "Solo.mp3"), "line")
        self.assertEqual(library.query("solo")[0][0]["lyrics"], "line")
        self.assertIsNone(library.refresh(self.a / "not in book.mp3"))

    def test_rename_keeps_number(self):
        library.scan(self.cfg)
        before = {r["path"]: r for r in library.query(limit=100)[0]}
        src, dst = self.a / "Solo.mp3", self.a / "Solo Renamed.mp3"
        src.rename(dst)                                                     # same size + mtime: same song
        moved = []
        self.assertEqual(library.scan(self.cfg, renamed=lambda o, n: moved.append((o, n))), 7)
        self.assertEqual(moved, [(str(src), str(dst))])
        after = {r["path"]: r for r in library.query(limit=100)[0]}
        self.assertNotIn(str(src), after)
        self.assertEqual(after[str(dst)]["number"], before[str(src)]["number"])
        self.assertEqual(after[str(dst)]["id"], before[str(src)]["id"])

    def test_rename_keeps_number_by_name(self):
        library.scan(self.cfg)
        before = {r["path"]: r["number"] for r in library.query(limit=100)[0]}
        src, dst = self.a / "Solo.mp3", self.a / "Solo (2).mp3"
        src.rename(dst)
        os.utime(dst, (time.time() + 60, time.time() + 60))                 # touched: size/mtime no longer match
        library.scan(self.cfg)
        after = {r["path"]: r["number"] for r in library.query(limit=100)[0]}
        self.assertEqual(after[str(dst)], before[str(src)])


class Names(unittest.TestCase):
    def test_clean_stem(self):
        c = library.clean_stem
        self.assertEqual(c("Yung Lean - Forever Yung (Official Video)"), "Yung Lean - Forever Yung")
        self.assertEqual(c("Coma_Cose - CUORICINI (Official Video - Sanremo 2025)"), "Coma Cose - Cuoricini")  # '_' -> space
        self.assertEqual(c("Artist_-_Song"), "Artist - Song")
        self.assertEqual(c("Artist - Song [dQw4w9WgXcQ]"), "Artist - Song")
        self.assertEqual(c("Fabri Fibra - Che Fine (Red Bull 64 Bars)"), "Fabri Fibra - Che Fine (Red Bull 64 Bars)")
        self.assertEqual(c("Artist - Topic"), "Artist")
        self.assertEqual(c("Marracash - Stupido Official Video"), "Marracash - Stupido")
        self.assertEqual(c("Artist - Song Official Music Video"), "Artist - Song")
        self.assertEqual(c("Artist - Song Video Ufficiale"), "Artist - Song")
        self.assertEqual(c("Artist - Official Video Game"), "Artist - Official Video Game")   # only trailing junk goes
        self.assertEqual(c("M83 'Midnight City' Official video [dX3k_QDnzHE]"), "M83 - Midnight City")
        self.assertEqual(c('Artist "Song Name"'), "Artist - Song Name")
        self.assertEqual(c("Artist – Song"), "Artist - Song")
        self.assertEqual(c("Artist | Song"), "Artist - Song")
        self.assertEqual(c("Don't Stop"), "Don't Stop")                                      # no artist: stays unknown

    def test_split_name(self):
        s = library.split_name
        self.assertEqual(s("A$AP Rocky - Everyday ft. Rod Stewart, Miguel"), ("Everyday", "A$AP Rocky ft. Rod Stewart, Miguel"))
        self.assertEqual(s("Artist - Song (feat. Guest)"), ("Song", "Artist feat. Guest"))
        self.assertEqual(s("Artist - Song [featuring Guest]"), ("Song", "Artist featuring Guest"))
        self.assertEqual(s("Artist - Everyday FT. Rod"), ("Everyday", "Artist ft. Rod"))
        self.assertEqual(s("Coma_Cose - CUORICINI"), ("CUORICINI", "Coma Cose"))
        self.assertEqual(s("SC1234-05 - Artist - Title"), ("Title", "Artist"))        # disc code prefix
        self.assertEqual(s("Solo"), ("Solo", ""))
        self.assertEqual(s("Artist - Gift. Song"), ("Gift. Song", "Artist"))          # "Gift." is not a feat marker
        self.assertEqual(s("Band - Left ft. Right"), ("Left", "Band ft. Right"))


class LrcTags(unittest.TestCase):
    """The [offset:], [kk:suspect] and [kk:untimed] tags that live inside .lrc files."""

    def test_offset_roundtrip(self):
        t = "[ar:A$AP Rocky]\n[ti:Everyday]\n[00:01.00]First line\n[00:05.00]Second line\n"
        self.assertEqual(lyrics.lrc_get_offset(t), 0.0)
        s = lyrics.lrc_set_offset(t, 29.95)                                 # + = lyrics later, tag stores -ms
        self.assertIn("[offset:-29950]", s)
        self.assertAlmostEqual(lyrics.lrc_get_offset(s), 29.95)
        self.assertEqual(s.replace("[offset:-29950]\n", ""), t)             # every other byte untouched
        self.assertEqual(lyrics.lrc_set_offset(s, 29.95), s)                # idempotent
        self.assertEqual(lyrics.lrc_set_offset(s, 0), t)                    # 0 drops the tag again
        self.assertEqual(lyrics.lrc_get_offset("[offset:+500]\n[00:01.00]a\n"), -0.5)

    def test_offset_replaces_and_drops_suspect(self):
        t = "[offset:500]\n[kk:suspect]\n[00:01.00]Hi\n"
        s = lyrics.lrc_set_offset(t, -1.25)
        self.assertEqual(s.count("[offset:"), 1)
        self.assertIn("[offset:1250]", s)
        self.assertNotIn("kk:suspect", s)
        self.assertFalse(lyrics.lrc_is_suspect(s))
        self.assertEqual(lyrics.lrc_get_offset(s), -1.25)
        self.assertEqual(s, "[offset:1250]\n[00:01.00]Hi\n")

    def test_suspect(self):
        self.assertTrue(lyrics.lrc_is_suspect("[ar:X]\n[kk:suspect]\n[00:01.00]Hi\n"))
        self.assertFalse(lyrics.lrc_is_suspect("[kk:untimed]\n[00:01.00]Hi\n"))
        self.assertFalse(lyrics.lrc_is_suspect("[00:01.00]Hi\n"))

    def test_kind(self):
        self.assertEqual(lyrics.lrc_kind("[00:01.00]a\n[00:02.50]b\n"), "line")
        self.assertEqual(lyrics.lrc_kind("[00:01.00]<00:01.00>a <00:02.00>b\n"), "word")
        self.assertEqual(lyrics.lrc_kind("[ar:X]\n[ti:Y]\n[offset:10]\n"), "none")
        self.assertEqual(lyrics.lrc_kind(""), "none")

    def test_parse_lrc_ignores_tags(self):
        lines = lyrics.parse_lrc("[ar:Artist]\n[ti:Title]\n[offset:500]\n[kk:suspect]\n[00:01.00]Hi there\n")
        self.assertEqual([text(l) for l in lines], ["Hi there "])
        self.assertAlmostEqual(lines[0][0][0], 1.0)                         # the offset tag is not applied here


class LyricsFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.song = self.tmp / "Band - Song.mp3"
        self.song.write_bytes(b"x")

    def test_lrc_for_and_target(self):
        self.assertIsNone(library.lrc_for(self.song))
        self.assertEqual(library.lrc_target(self.song), self.tmp / "Band - Song.lrc")
        other = self.tmp / "BAND - SONG.LRC"
        other.write_text("[00:01.00]Hi\n")
        self.assertEqual(library.lrc_for(self.song), other)                 # case-insensitive stem

    def test_status_audio(self):
        lrc = self.tmp / "Band - Song.lrc"
        self.assertEqual(library.lyrics_status(self.song, "audio"), "none")
        lrc.write_text("[00:01.00]Hi\n")
        self.assertEqual(library.lyrics_status(self.song, "audio"), "line")
        lrc.write_text("[00:01.00]<00:01.00>Hi\n")
        self.assertEqual(library.lyrics_status(self.song, "audio"), "word")
        lrc.write_text("[kk:suspect]\n[00:01.00]Hi\n")
        self.assertEqual(library.lyrics_status(self.song, "audio"), "suspect")
        self.assertEqual(library.lyrics_status(self.song, "midi"), "embedded")
        self.assertEqual(library.lyrics_status(self.song, "cdg"), "cdg")

    def test_status_chorus(self):
        d = self.tmp / "pack" / "Band - Chart"
        d.mkdir(parents=True)
        (d / "song.ini").write_text("[song]\nname = Chart\nartist = Band\n")
        self.assertIsNone(library.lrc_for(d))                               # lyrics are inside the folder
        self.assertEqual(library.lyrics_status(d, "chorus"), "none")
        (d / "notes.chart").write_text("[Song]\n{\n}\n")
        self.assertEqual(library.lyrics_status(d, "chorus"), "embedded")


class Migration(unittest.TestCase):
    def test_old_book_opens_and_keeps_numbers(self):
        tmp = Path(tempfile.mkdtemp())
        config.DATA_DIR, config.DB_FILE = tmp / "data", tmp / "data" / "lib.db"
        config.DATA_DIR.mkdir()
        songs = tmp / "songs"
        songs.mkdir()
        song = songs / "Band - Song.mp3"
        song.write_bytes(b"x")
        con = sqlite3.connect(config.DB_FILE)                               # the pre-lyrics schema
        con.executescript("""CREATE TABLE songs(id INTEGER PRIMARY KEY, number INTEGER UNIQUE, path TEXT UNIQUE,
            root TEXT, kind TEXT, title TEXT, artist TEXT, lang TEXT, country TEXT, nkey TEXT, prio INT);
            CREATE INDEX songs_nkey ON songs(nkey); CREATE INDEX songs_root ON songs(root, number);""")
        con.execute("INSERT INTO songs(number,path,root,kind,title,artist,lang,country,nkey,prio) VALUES(77,?,?,?,?,?,?,?,?,?)",
                    (str(song), str(songs), "audio", "Song", "Band", "en", "", "bandsong", 5))
        con.commit()
        con.close()
        con = library.db()
        self.assertTrue({"lyrics", "size", "mtime"} <= {r[1] for r in con.execute("PRAGMA table_info(songs)")})
        con.close()
        self.assertEqual(library.scan({"folders": [{"path": str(songs), "start": 10}]}), 1)
        row = library.get(number=77)
        self.assertEqual((row["lyrics"], row["size"]), ("none", 1))
        self.assertEqual(len(library.query(limit=10)[0]), 1)


class Log(unittest.TestCase):
    def test_tail_keeps_errors_with_tracebacks(self):
        from kuraoke_kami import log
        config.LOG_FILE = Path(tempfile.mkdtemp()) / "k.log"
        config.LOG_FILE.write_text("2026-11-01 19:00:00,1 INFO started\n2026-11-01 19:00:01,1 ERROR boom\nTraceback (most recent call last):\n  File x\nValueError: no\n2026-11-01 19:00:02,1 INFO fine\n")
        self.assertEqual(log.tail(10, only_errors=True), ["2026-11-01 19:00:01,1 ERROR boom", "Traceback (most recent call last):", "  File x", "ValueError: no"])
        self.assertEqual(len(log.tail(2)), 2)


class Player(unittest.TestCase):
    def test_graph(self):
        self.assertEqual(graph({"base": 1}, False, True, 0), "[aid1]volume=1[s0];[s0]amix=inputs=1:normalize=0,anull[ao]")
        g = graph({"base": 1, "melody": 2, "chorus": 3}, False, True, 2)
        self.assertIn("[aid2]volume=0[s1]", g); self.assertIn("[aid3]volume=1[s2]", g); self.assertIn("rubberband=pitch=1.12246", g)


if __name__ == "__main__":
    unittest.main()
