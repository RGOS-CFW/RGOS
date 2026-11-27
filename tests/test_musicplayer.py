import os
import struct
import tempfile
import unittest

from tests import helpers

menu = helpers.load_menu()
import sys
sys.path.insert(0, helpers.RGOS)
import musicplayer as mp


def synchsafe(n):
    return bytes([(n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127])


def id3v23(frames):
    body = b""
    for fid, data in frames:
        body += fid.encode() + struct.pack(">I", len(data)) + b"\x00\x00" + data
    return b"ID3\x03\x00\x00" + synchsafe(len(body)) + body


def text_frame(text):
    return b"\x00" + text.encode("latin-1")


# MPEG-1 layer 3, 128 kbit/s, 44.1 kHz, stereo, no padding, no CRC: 417 bytes per frame
HDR = b"\xff\xfb\x90\x00"
FRAME = HDR + bytes(417 - 4)
PNG = b"\x89PNG\r\n\x1a\n" + b"fakepicturebytes"


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


class ScanTests(unittest.TestCase):
    def test_finds_audio_in_sub_folders_in_natural_order_and_skips_hidden(self):
        d = tempfile.mkdtemp()
        for n in ("10 ten.mp3", "2 two.mp3", "1 one.ogg", "notes.txt", ".hidden.mp3", "A/b.flac", ".trash/x.mp3"):
            write(os.path.join(d, n), b"x")
        got = [os.path.relpath(p, d) for p in mp.scan(d)]
        self.assertEqual(got, ["1 one.ogg", "2 two.mp3", "10 ten.mp3", os.path.join("A", "b.flac")])

    def test_missing_folder_is_an_empty_list(self):
        self.assertEqual(mp.scan("/no/such/folder"), [])

    def test_music_folder_is_under_the_roms_partition(self):
        self.assertEqual(mp.music_dir("/media/roms"), "/media/roms/music")

    def test_fmt_time(self):
        self.assertEqual([mp.fmt_time(x) for x in (None, -1, 0, 59.9, 65, 3599, 3600, 3725)],
                         ["--:--", "--:--", "0:00", "0:59", "1:05", "59:59", "1:00:00", "1:02:05"])


class TagTests(unittest.TestCase):
    def test_id3v2_text_frames_and_cbr_length(self):
        tag = id3v23([("TIT2", text_frame("Atlantis")), ("TPE1", text_frame("Bolt Action")), ("TALB", text_frame("Waves"))])
        p = write(os.path.join(tempfile.mkdtemp(), "a.mp3"), tag + FRAME * 100)
        m = mp.read_meta(p)
        self.assertEqual((m["title"], m["artist"], m["album"]), ("Atlantis", "Bolt Action", "Waves"))
        self.assertAlmostEqual(m["duration"], 100 * 417 * 8 / 128000.0, places=2)
        self.assertIsNone(m["art"])

    def test_xing_header_gives_the_exact_length(self):
        xing = HDR + bytes(32) + b"Xing" + struct.pack(">I", 1) + struct.pack(">I", 1000)
        xing += bytes(417 - len(xing))
        p = write(os.path.join(tempfile.mkdtemp(), "v.mp3"), xing + FRAME * 5)
        self.assertAlmostEqual(mp.read_meta(p)["duration"], 1000 * 1152 / 44100.0, places=3)

    def test_cover_picture_only_when_asked_for(self):
        tag = id3v23([("TIT2", text_frame("T")), ("APIC", b"\x00image/png\x00\x03\x00" + PNG)])
        p = write(os.path.join(tempfile.mkdtemp(), "c.mp3"), tag + FRAME * 3)
        self.assertIsNone(mp.read_meta(p)["art"])
        self.assertEqual(mp.read_meta(p, art=True)["art"], PNG)

    def test_id3v1_is_the_fallback(self):
        v1 = b"TAG" + b"Old Song".ljust(30, b"\0") + b"Old Band".ljust(30, b"\0") + b"Old LP".ljust(30, b"\0") + bytes(35)   # year + comment + genre: 128 bytes in all
        p = write(os.path.join(tempfile.mkdtemp(), "o.mp3"), FRAME * 10 + v1)
        m = mp.read_meta(p)
        self.assertEqual((m["title"], m["artist"], m["album"]), ("Old Song", "Old Band", "Old LP"))
        self.assertAlmostEqual(m["duration"], 10 * 417 * 8 / 128000.0, places=2)   # the 128 tag bytes are not audio

    def test_damaged_files_give_empty_tags_instead_of_raising(self):
        d = tempfile.mkdtemp()
        for name, data in (("e.mp3", b""), ("g.mp3", b"\xff" * 500), ("t.flac", b"fLaC\x00"), ("o.ogg", b"OggS"), ("w.wav", b"RIFF")):
            m = mp.read_meta(write(os.path.join(d, name), data))
            self.assertEqual((m["title"], m["artist"], m["album"]), ("", "", ""), name)

    def test_wav_length(self):
        fmt = struct.pack("<HHIIHH", 1, 2, 44100, 176400, 4, 16)
        data = bytes(176400 * 3)
        wav = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data
        self.assertAlmostEqual(mp.read_meta(write(os.path.join(tempfile.mkdtemp(), "s.wav"), wav))["duration"], 3.0)

    def test_library_fills_in_tags_in_the_background(self):
        d = tempfile.mkdtemp()
        write(os.path.join(d, "b.mp3"), id3v23([("TIT2", text_frame("Beta"))]) + FRAME * 4)
        write(os.path.join(d, "a.mp3"), FRAME * 4)
        lib = mp.Library(d)
        lib.rescan()
        self.assertEqual([t.name for t in lib.tracks], ["a", "b"])       # listed at once, tags follow
        for _ in range(200):
            if all(t.tagged for t in lib.tracks):
                break
            import time
            time.sleep(0.01)
        self.assertEqual([t.label for t in lib.tracks], ["a", "Beta"])   # no title tag -> the file name
        again = lib.rescan()
        self.assertIs(again[0], lib.tracks[0])                           # a re-scan keeps the Track objects


class FakeMusic:
    def __init__(self, bad=()):
        self.bad, self.busy, self.paused, self.loaded, self.started, self.pos_calls = set(bad), False, False, None, [], []

    def load(self, path):
        if path in self.bad:
            raise RuntimeError("cannot decode")
        self.loaded = path

    def set_volume(self, v):
        pass

    def play(self, loops=0, start=0.0):
        self.busy, self.paused = True, False
        self.started.append((self.loaded, start))

    def pause(self):
        self.paused = True

    def unpause(self):
        self.paused = False

    def stop(self):
        self.busy = False

    def get_busy(self):
        return self.busy and not self.paused

    def set_pos(self, p):
        self.pos_calls.append(p)


class FakeMixer:
    def __init__(self, rate=22050, bad=()):
        self.music, self.info = FakeMusic(bad), (rate, -16, 2) if rate else None

    def get_init(self):
        return self.info

    def init(self, rate, fmt, ch, buf):
        self.info = (rate, fmt, ch)

    def quit(self):
        self.info = None


class PlayerTests(unittest.TestCase):
    def make(self, n=3, bad=(), durations=240.0, rate=22050):
        self.t = [0.0]
        tracks = []
        for i in range(n):
            tr = mp.Track("/m/%d.mp3" % i)
            tr.duration, tr.tagged = durations, True
            tracks.append(tr)
        self.mixer = FakeMixer(rate, {"/m/%d.mp3" % i for i in bad})
        self.logs = []
        self.p = mp.Player(self.mixer, clock=lambda: self.t[0], log=self.logs.append, rng=__import__("random").Random(1))
        self.p.set_tracks(tracks)
        self.tracks = tracks
        return self.p

    def end_song(self):
        self.mixer.music.busy = False
        self.p.tick()

    def test_play_reopens_the_launchers_22khz_mixer_at_cd_rate(self):
        p = self.make()
        p.play(self.tracks[0])
        self.assertEqual(self.mixer.info[0], mp.MIXER_RATE)
        self.assertEqual((p.state, p.cur), ("playing", self.tracks[0]))

    def test_position_follows_the_clock_and_freezes_while_paused(self):
        p = self.make()
        p.play(self.tracks[0])
        self.t[0] += 5
        self.assertAlmostEqual(p.position(), 5.0)
        p.toggle()
        self.t[0] += 60
        self.assertEqual((p.state, round(p.position(), 1)), ("paused", 5.0))
        p.toggle()
        self.t[0] += 2
        self.assertAlmostEqual(p.position(), 7.0)

    def test_seek_shows_at_once_and_reaches_the_decoder_after_the_presses_stop(self):
        p = self.make()
        p.play(self.tracks[0])
        self.t[0] += 20
        for _ in range(3):
            p.seek(10)
        self.assertAlmostEqual(p.position(), 50.0)
        p.tick()
        self.assertEqual(self.mixer.music.pos_calls, [])          # still settling: no decoder call per press
        self.t[0] += mp.SEEK_SETTLE + 0.01
        p.tick()
        self.assertEqual(self.mixer.music.pos_calls, [50.0])
        self.assertAlmostEqual(p.position(), 50.0, delta=0.05)

    def test_seek_past_the_end_moves_to_the_next_song(self):
        p = self.make()
        p.repeat = "all"
        p.play(self.tracks[0])
        p.seek(10000)
        self.t[0] += 1
        p.tick()
        self.assertIs(p.cur, self.tracks[1])

    def test_previous_restarts_after_a_few_seconds_otherwise_goes_back(self):
        p = self.make()
        p.play(self.tracks[1])
        self.t[0] += 10
        p.prev()
        self.assertIs(p.cur, self.tracks[1])
        self.assertAlmostEqual(p.position(), 0.0)
        p.prev()
        self.assertIs(p.cur, self.tracks[0])

    def test_next_wraps_round_and_a_finished_song_advances(self):
        p = self.make()
        p.play(self.tracks[2])
        p.next()
        self.assertIs(p.cur, self.tracks[0])
        self.end_song()
        self.assertIs(p.cur, self.tracks[1])

    def test_repeat_off_stops_after_the_last_song(self):
        p = self.make()
        p.repeat = "off"
        p.play(self.tracks[2])
        self.end_song()
        self.assertEqual(p.state, "stopped")

    def test_repeat_one_replays_the_same_song(self):
        p = self.make()
        p.repeat = "one"
        p.play(self.tracks[1])
        self.end_song()
        self.assertEqual((p.state, p.cur), ("playing", self.tracks[1]))
        self.assertEqual(len(self.mixer.music.started), 2)

    def test_repeat_cycles_off_all_one(self):
        p = self.make()
        self.assertEqual([p.cycle_repeat() for _ in range(3)], ["one", "off", "all"])

    def test_shuffle_starts_with_the_chosen_song_and_plays_each_once_per_round(self):
        p = self.make(n=6)
        p.toggle_shuffle()
        p.play(self.tracks[3])
        seen = [p.cur]
        for _ in range(5):
            p.next()
            seen.append(p.cur)
        self.assertIs(seen[0], self.tracks[3])
        self.assertEqual(sorted(t.path for t in seen), sorted(t.path for t in self.tracks))

    def test_a_song_the_mixer_cannot_decode_is_skipped(self):
        p = self.make(bad=(1,))
        p.play(self.tracks[0])
        p.next()
        self.assertIs(p.cur, self.tracks[2])
        self.assertTrue(self.tracks[1].bad)
        self.assertTrue(any("cannot play" in m for m in self.logs))

    def test_playing_an_undecodable_song_reports_it_and_stays_stopped(self):
        p = self.make(bad=(0,))
        self.assertFalse(p.play(self.tracks[0]))
        self.assertEqual(p.state, "stopped")
        self.assertIn("Can't play", p.message())

    def test_when_nothing_can_be_decoded_it_stops_instead_of_looping(self):
        p = self.make(bad=(0, 1, 2))
        p.next()
        self.assertEqual(p.state, "stopped")
        self.assertIn("None of the songs", p.message())

    def test_launcher_music_stays_out_while_the_screen_is_open_or_a_song_plays(self):
        p = self.make()
        self.assertFalse(p.engaged)
        p.hold = True
        self.assertTrue(p.engaged)
        p.hold = False
        p.play(self.tracks[0])
        self.assertTrue(p.engaged)
        p.toggle()
        self.assertTrue(p.engaged)           # paused still owns the mixer
        p.stop()
        self.assertFalse(p.engaged)

    def test_opening_the_screen_silences_the_launcher_track_once(self):
        p = self.make()
        self.mixer.music.busy = True
        p.enter()
        self.assertFalse(self.mixer.music.busy)
        p.play(self.tracks[0])
        p.enter()                            # already playing the user's song: leave it alone
        self.assertTrue(self.mixer.music.busy)

    def test_toggle_from_stopped_starts_the_first_song(self):
        p = self.make()
        p.toggle()
        self.assertEqual((p.state, p.cur), ("playing", self.tracks[0]))

    def test_a_rescan_with_the_same_songs_does_not_reshuffle(self):
        p = self.make(n=6)
        p.toggle_shuffle()
        p.play(self.tracks[0])
        order = list(p._order)
        p.set_tracks(list(self.tracks))
        self.assertEqual(p._order, order)


class MenuWiringTests(unittest.TestCase):
    def test_tools_lists_music_as_a_built_in_view(self):
        self.assertIn(("music", "Music", "Play the songs in the ROMS music folder", "@view:music"), menu.TOOLS)

    def test_music_has_an_icon_and_a_transition_depth(self):
        self.assertIn("music", menu.ICONS)
        self.assertIn("music", menu.VT_DEPTH)

    def test_the_player_reads_the_music_folder_on_the_roms_partition(self):
        with open(os.path.join(helpers.RGOS, "menu.py")) as f:
            src = f.read()
        self.assertIn("musicplayer.Library(musicplayer.music_dir(ROMS_ROOT))", src)


class Surf:
    def __init__(self, w=100, h=16):
        self.w, self.h = w, h

    def get_width(self):
        return self.w

    def get_height(self):
        return self.h


class Font:
    def render(self, text, aa, col):
        return Surf(len(text) * 8)


class Canvas:
    def __init__(self):
        self.blits, self.clip = [], None

    def get_clip(self):
        return menu.pygame.Rect(0, 0, 720, 480)

    def set_clip(self, r):
        self.clip = r

    def blit(self, surf, pos):
        self.blits.append(pos)


class DrawHelperTests(unittest.TestCase):
    def test_glyphs_only_use_integer_coordinates(self):
        calls = []
        orig = menu.pygame.draw
        menu.pygame.draw = type("D", (), {"__getattr__": lambda s, n: (lambda *a, **k: calls.append(a))})()
        try:
            for kind in ("play", "pause", "stop", "next", "prev"):
                menu.mp_glyph(object(), kind, 100.0, 50.0, 11, (1, 2, 3))
        finally:
            menu.pygame.draw = orig
        nums = []
        for a in calls:
            for part in a[2:]:
                for q in (part if isinstance(part, (tuple, list)) else [part]):
                    nums.extend(q if isinstance(q, (tuple, list)) else [q])
        self.assertTrue(nums and all(isinstance(n, int) for n in nums if not isinstance(n, bool)), nums)

    def test_marquee_only_scrolls_text_that_does_not_fit(self):
        c = Canvas()
        self.assertFalse(menu.marquee(c, Font(), "short", (1, 1, 1), 10, 10, 300, 5.0))
        self.assertTrue(menu.marquee(c, Font(), "a very long song title that cannot fit", (1, 1, 1), 10, 10, 100, 5.0))

    def test_marquee_rests_at_the_start_then_scrolls_left(self):
        font, text = Font(), "a very long song title that cannot fit"
        c1, c2 = Canvas(), Canvas()
        menu.marquee(c1, font, text, (9, 9, 9), 10, 10, 100, 0.5)
        menu.marquee(c2, font, text, (9, 9, 9), 10, 10, 100, 4.0)
        self.assertEqual(c1.blits[0][0], 10)
        self.assertLess(c2.blits[0][0], 10)


if __name__ == "__main__":
    unittest.main()
