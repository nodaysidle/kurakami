"""Run: python3 -m unittest discover -s tests -v   (no ffmpeg/mpv needed)."""
import sys
import tempfile
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


class Names(unittest.TestCase):
    def test_clean_stem(self):
        c = library.clean_stem
        self.assertEqual(c("Yung Lean - Forever Yung (Official Video)"), "Yung Lean - Forever Yung")
        self.assertEqual(c("Coma_Cose - CUORICINI (Official Video - Sanremo 2025)"), "Coma_Cose - Cuoricini")
        self.assertEqual(c("Artist - Song [dQw4w9WgXcQ]"), "Artist - Song")
        self.assertEqual(c("Fabri Fibra - Che Fine (Red Bull 64 Bars)"), "Fabri Fibra - Che Fine (Red Bull 64 Bars)")
        self.assertEqual(c("Artist - Topic"), "Artist")
        self.assertEqual(c("Marracash - Stupido Official Video"), "Marracash - Stupido")
        self.assertEqual(c("Artist - Song Official Music Video"), "Artist - Song")
        self.assertEqual(c("Artist - Song Video Ufficiale"), "Artist - Song")
        self.assertEqual(c("Artist - Official Video Game"), "Artist - Official Video Game")   # only trailing junk goes


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
