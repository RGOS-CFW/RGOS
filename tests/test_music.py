import os
import tempfile
import unittest
from unittest import mock

from tests import helpers

menu = helpers.load_menu()


class MusicTickTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rgos-music-")
        for n in ("a.mp3", "b.ogg", "c.wav"):
            with open(os.path.join(self.dir, n), "wb") as f:
                f.write(b"x")
        self.pg = mock.MagicMock()
        self.pg.mixer.get_init.return_value = True
        self.pg.mixer.music.get_busy.return_value = False
        self.logs = []
        for p in (mock.patch.object(menu, "pygame", self.pg),
                  mock.patch.object(menu, "MUSIC_DIRS", (self.dir,)),
                  mock.patch.object(menu, "log", self.logs.append),
                  mock.patch.object(menu, "_music_playlist", []),
                  mock.patch.object(menu, "_music_last", None),
                  mock.patch.object(menu, "_music_scan", [0.0, []]),
                  mock.patch.object(menu, "_music_retry_at", [0.0])):
            p.start()
            self.addCleanup(p.stop)

    def test_unplayable_tracks_are_not_retried_every_frame(self):
        self.pg.mixer.music.load.side_effect = Exception("cannot decode")
        walks = []
        real_walk = os.walk
        with mock.patch("os.walk", lambda *a, **k: (walks.append(1), real_walk(*a, **k))[1]):
            for frame in range(200):
                menu._music_tick(now=1000.0 + frame / 60.0)
        self.assertLessEqual(self.pg.mixer.music.load.call_count, 6)
        self.assertLessEqual(len(walks), 2)
        self.assertLessEqual(len(self.logs), 6)

    def test_it_tries_again_after_the_backoff(self):
        self.pg.mixer.music.load.side_effect = Exception("cannot decode")
        menu._music_tick(now=1000.0)
        tried = self.pg.mixer.music.load.call_count
        self.assertGreater(tried, 0)
        menu._music_tick(now=1000.0 + menu.MUSIC_RETRY_S - 5)
        self.assertEqual(self.pg.mixer.music.load.call_count, tried)
        menu._music_retry_at[0] = 0.0
        self.pg.mixer.music.load.side_effect = None
        menu._music_tick(now=2000.0)
        self.assertTrue(self.pg.mixer.music.play.called)

    def test_playing_a_track_clears_the_backoff(self):
        menu._music_retry_at[0] = 5.0
        menu._music_tick(now=10.0)
        self.assertTrue(self.pg.mixer.music.play.called)
        self.assertEqual(menu._music_retry_at[0], 0.0)

    def test_nothing_happens_while_music_is_playing(self):
        self.pg.mixer.music.get_busy.return_value = True
        for frame in range(50):
            menu._music_tick(now=1000.0 + frame)
        self.assertFalse(self.pg.mixer.music.load.called)

    def test_next_track_starts_when_one_ends(self):
        menu._music_tick(now=1.0)
        self.assertEqual(self.pg.mixer.music.play.call_count, 1)
        menu._music_tick(now=2.0)
        self.assertEqual(self.pg.mixer.music.play.call_count, 2)


if __name__ == "__main__":
    unittest.main()
