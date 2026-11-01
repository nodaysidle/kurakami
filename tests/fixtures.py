"""Builds a tiny demo song folder (every supported format) for tests and for trying the app. Needs ffmpeg."""
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kuraoke_kami.lyrics import write_smf  # noqa: E402


def meta(t, mt, d): return (t, 0xFF, mt, d)


def midi(words, melody_name="Melody", chorus=True, kar=False):
    """words: [(tick, text)] at 480 tpq, 120 bpm -> one lyric/tempo track + melody + (chorus) + drums tracks."""
    lyr = 0x01 if kar else 0x05
    t0 = [meta(0, 0x51, (500000).to_bytes(3, "big")), meta(0, 0x03, b"Words")]
    if kar: t0 += [meta(0, 0x01, b"@LENGL"), meta(0, 0x01, b"@TDemo")]
    t0 += [meta(t, lyr, x.encode()) for t, x in words] + [meta(words[-1][0] + 480, 0x2F, b"")]
    def notes(ch, name, pitches):
        ev = [meta(0, 0x03, name.encode()), (0, 0xC0 | ch, 0, bytes([0]))]
        for k, p in enumerate(pitches):
            ev += [(k * 480, 0x90 | ch, 0, bytes([p, 90])), (k * 480 + 400, 0x80 | ch, 0, bytes([p, 0]))]
        return ev + [meta(len(pitches) * 480, 0x2F, b"")]
    tracks = [t0, notes(0, melody_name, [72, 74, 76, 77, 79, 77, 76, 74]), notes(9, "Drums", [36, 38] * 4)]
    if chorus: tracks.append(notes(1, "Backing Vocals", [64, 65, 67, 69, 67, 65, 64, 62]))
    return write_smf(480, tracks)


def ffmpeg(*a): subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def sine(out, f, d=12, *extra): ffmpeg("-f", "lavfi", "-i", f"sine=f={f}:d={d}", *extra, str(out))


def cdg(path, seconds=12):
    """Palette packet + a coloured tile every 0.5 s: enough to prove the decoder."""
    def pkt(ins, data): return bytes([9, ins]) + b"\0\0" + data.ljust(16, b"\0") + b"\0" * 4
    pal = b"".join(struct.pack(">H", ((i & 15) << 8) | ((15 - i) << 4)) for i in range(8))
    out = pkt(30, pal) + pkt(31, pal) + pkt(1, bytes([0]))
    for k in range(seconds * 2):
        out += pkt(6, bytes([0, (k % 7) + 1, k % 18, k % 50]) + b"\x3f" * 12)
        out += b"\0" * 24 * 148  # idle packets pad to 0.5 s (150 packets/0.5 s)
    path.write_bytes(out)


def build(root):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    words = [(0, "Hel"), (480, "lo "), (960, "to "), (1440, "the "), (1920, "/Kar"), (2400, "a"), (2640, "o"), (2880, "ke ")]
    (root / "Demo Band - Midi Song.mid").write_bytes(midi(words))
    (root / "Demo Band - Kar Song.kar").write_bytes(midi(words, kar=True))
    sine(root / "Singer - Mp3 Song.mp3", 330)
    (root / "Singer - Mp3 Song.lrc").write_text("[00:01.00]<00:01.00>Hello <00:02.00>mp3 <00:03.00>world\n[00:05.00]Second line here\n")
    ffmpeg("-f", "lavfi", "-i", "testsrc=s=320x240:d=12:r=25", "-f", "lavfi", "-i", "sine=f=300:d=12", "-f", "lavfi", "-i", "sine=f=600:d=12",
           "-map", "0", "-map", "1", "-map", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(root / "Video Star - Mp4 Song.mp4"))
    sine(root / "Disc Girl - Cdg Song.mp3", 440); cdg(root / "Disc Girl - Cdg Song.cdg")
    ch = root / "chorus" / "Chart Dude - Chorus Song"; ch.mkdir(parents=True, exist_ok=True)
    (ch / "song.ini").write_text("[song]\nname = Chorus Song\nartist = Chart Dude\n")
    sine(ch / "guitar.ogg", 200); sine(ch / "vocals.ogg", 500); sine(ch / "vocals_1.ogg", 700)
    voc = [meta(0, 0x03, b"PART VOCALS"), (0, 0x90, 0, bytes([105, 100])), (900, 0x80, 0, bytes([105, 0]))]
    voc += [meta(t, 0x05, x.encode()) for t, x in [(0, "Sing-"), (240, "ing "), (480, "a "), (720, "song")]]
    voc += [(1000, 0x90, 0, bytes([105, 100])), meta(1000, 0x05, b"Next "), meta(1300, 0x05, b"line"), (1800, 0x80, 0, bytes([105, 0])), meta(1900, 0x2F, b"")]
    (ch / "notes.mid").write_bytes(write_smf(480, [[meta(0, 0x51, (500000).to_bytes(3, "big")), meta(0, 0x2F, b"")], voc]))
    return root


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "demo-songs"))
