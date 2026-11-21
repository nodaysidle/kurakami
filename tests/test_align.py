"""Speech-recognition timing (kuraoke_kami/align.py): no faster-whisper needed, transcripts are hand-made."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kuraoke_kami import align, lyrics  # noqa: E402


def seg(*words):
    """seg(("Hello", 1.0), ...) -> one transcript segment; words keep a leading space like the recogniser's."""
    ws = [{"w": (" " if i else "") + w, "s": s, "e": s + 0.3} for i, (w, s) in enumerate(words)]
    return {"start": words[0][1], "end": words[-1][1] + 0.3, "text": " ".join(w for w, _ in words), "words": ws}


class TextLines(unittest.TestCase):
    def test_strips_stamps_tags_and_sections(self):
        src = "[ar:X]\n[kk:untimed]\n[offset:250]\n[Verse 1]\n[00:01.00] Iron rattles\n<00:02.00>The <00:02.50>glass\n\n(Chorus)\nPlain line\n(Ah)\n(Only the storm)\n"
        self.assertEqual(align.text_lines(src), ["Iron rattles", "The glass", "Plain line", "(Ah)", "(Only the storm)"])


class Align(unittest.TestCase):
    def test_known_words_take_heard_times(self):
        lines = ["Iron rattles against the frost", "The glass is cold"]
        segs = [seg(("Iron", 10.0), ("rattles", 10.5), ("against", 11.0), ("the", 11.4), ("frost", 11.8)),
                seg(("The", 14.0), ("glass", 14.4), ("is", 14.8), ("cold", 15.2))]
        timed, share, hit = align.align(lines, segs)
        self.assertEqual(share, 1.0)
        self.assertEqual(hit, [True, True])
        self.assertEqual([w for w, _ in timed[1]], ["The", "glass", "is", "cold"])
        self.assertAlmostEqual(timed[1][0][1], 14.0)

    def test_misheard_word_is_interpolated(self):
        timed, share, _ = align.align(["The glass is cold"], [seg(("The", 1.0), ("grass", 2.0), ("is", 3.0), ("cold", 4.0))])
        self.assertAlmostEqual(timed[0][1][1], 2.0)          # 'glass' between 'The' (1.0) and 'is' (3.0)
        self.assertEqual(share, 0.75)

    def test_unheard_lines_share_the_gap_in_order(self):
        lines = ["one two", "la la la", "oh oh", "three four"]
        timed, _, hit = align.align(lines, [seg(("one", 10.0), ("two", 10.5)), seg(("three", 30.0), ("four", 30.5))])
        self.assertEqual(hit, [True, False, False, True])
        starts = [ln[0][1] for ln in timed]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(10.5 < starts[1] < starts[2] < 30.0)

    def test_result_is_word_timed_lrc_the_app_reads(self):
        timed, _, _ = align.align(["Hello world"], [seg(("Hello", 5.0), ("world", 5.5))])
        text = align.to_lrc(["[ar:A]", "[ti:B]"], timed)
        self.assertEqual(lyrics.lrc_kind(text), "word")
        ln = lyrics.parse_lrc(text)[0]
        self.assertEqual("".join(x for _, _, x in ln).split(), ["Hello", "world"])
        self.assertAlmostEqual(ln[0][0], 5.0)


class Transcript(unittest.TestCase):
    def test_transcript_becomes_lines_with_glued_apostrophes(self):
        s = {"start": 0, "end": 3, "text": "", "words": [
            {"w": "Questa", "s": 0.0, "e": 0.3}, {"w": " è", "s": 0.4, "e": 0.5}, {"w": " dell", "s": 0.6, "e": 0.8},
            {"w": "'amico", "s": 0.9, "e": 1.2}]}
        text = align.transcript_lrc(["[ar:X]"], [s])
        ln = lyrics.parse_lrc(text)[0]
        self.assertEqual("".join(x for _, _, x in ln).strip(), "Questa è dell'amico")

    def test_long_segment_is_cut_at_the_longest_pause_before_a_capital(self):
        s = seg(("Questa", 0.0), ("è", 0.4), ("la", 0.6), ("canzone", 0.8), ("dell'amico", 1.2), ("perso", 1.6),
                ("Quello", 3.3), ("col", 3.6), ("destino", 3.9), ("messo", 4.3))
        self.assertEqual([p[0][1] for p in align.transcript_lines([s])], [0.0, 3.3])


if __name__ == "__main__":
    unittest.main()
