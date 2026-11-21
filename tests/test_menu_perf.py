import unittest
from unittest import mock

from tests import helpers

menu = helpers.load_menu()


class FakeFont:
    def __init__(self):
        self.calls = 0

    def size(self, text):
        self.calls += 1
        return (8 * len(text), 16)


class WrapNTests(unittest.TestCase):
    def setUp(self):
        menu._WRAPN.clear()

    def test_wraps_and_truncates_like_before(self):
        f = FakeFont()
        text = "one two three four five six seven eight nine ten"
        out = menu.wrap_n(f, text, 8 * 14, 2)
        self.assertEqual(len(out), 2)
        self.assertTrue(out[-1].endswith("..."))

    def test_repeat_calls_do_no_measuring_and_cannot_be_corrupted(self):
        f = FakeFont()
        text = "alpha beta gamma delta epsilon zeta eta theta"
        first = menu.wrap_n(f, text, 8 * 12, 6)
        measured = f.calls
        first.append("mutated by a caller")
        again = menu.wrap_n(f, text, 8 * 12, 6)
        self.assertEqual(f.calls, measured)
        self.assertNotIn("mutated by a caller", again)

    def test_key_includes_width_and_line_limit(self):
        f = FakeFont()
        text = "alpha beta gamma delta epsilon zeta eta theta"
        self.assertNotEqual(menu.wrap_n(f, text, 8 * 12, 6), menu.wrap_n(f, text, 8 * 30, 6))
        self.assertEqual(len(menu.wrap_n(f, text, 8 * 12, 1)), 1)


class DetailCoverTests(unittest.TestCase):
    def setUp(self):
        menu._DETAIL_ART.clear()
        self.pg = mock.MagicMock()
        img = mock.MagicMock()
        img.get_size.return_value = (600, 900)
        img.convert_alpha.return_value = img
        self.pg.image.load.return_value = img
        self.pg.transform.smoothscale.return_value = "scaled-cover"
        p = mock.patch.object(menu, "pygame", self.pg)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(menu._DETAIL_ART.clear)

    def test_nothing_is_read_while_the_cursor_is_moving(self):
        self.assertIsNone(menu._detail_cover("/art/a.png", 152, 130, load=False))
        self.pg.image.load.assert_not_called()

    def test_loads_once_settled_then_serves_from_cache(self):
        self.assertEqual(menu._detail_cover("/art/a.png", 152, 130, load=True), "scaled-cover")
        self.assertEqual(self.pg.image.load.call_count, 1)
        # cached covers appear instantly even mid-scroll, and are not decoded again
        self.assertEqual(menu._detail_cover("/art/a.png", 152, 130, load=False), "scaled-cover")
        self.assertEqual(menu._detail_cover("/art/a.png", 152, 130), "scaled-cover")
        self.assertEqual(self.pg.image.load.call_count, 1)

    def test_a_skipped_load_is_not_remembered_as_a_failure(self):
        menu._detail_cover("/art/b.png", 152, 130, load=False)
        self.assertEqual(menu._detail_cover("/art/b.png", 152, 130, load=True), "scaled-cover")

    def test_settle_delay_is_short_but_nonzero(self):
        self.assertGreater(menu.DETAIL_SETTLE_S, 0.0)
        self.assertLess(menu.DETAIL_SETTLE_S, 0.3)


class FrameProfilerTests(unittest.TestCase):
    def make(self, enabled=True):
        self.t = [0.0]
        self.out = []
        return menu.FrameProfiler(enabled, self.out.append, interval=5.0, clock=lambda: self.t[0])

    def test_disabled_is_silent(self):
        p = self.make(False)
        self.t[0] = 100.0
        p.frame(0.5, 0.5, 0.5, 0.5, "x")
        self.assertEqual(self.out, [])

    def test_reports_average_slow_count_and_worst_split(self):
        p = self.make()
        for _ in range(9):
            p.frame(0.001, 0.004, 0.002, 0.003, "flow/games")  # 10 ms
        p.frame(0.002, 0.080, 0.010, 0.008, "flow/games")  # 100 ms
        self.assertEqual(self.out, [])  # nothing until the interval has passed
        self.t[0] = 5.1
        p.frame(0.001, 0.004, 0.002, 0.003, "flow/games")
        self.assertEqual(len(self.out), 1)
        line = self.out[0]
        self.assertIn("11 frames", line)
        self.assertIn("1 over 40 ms", line)
        self.assertIn("worst 100 ms", line)
        self.assertIn("draw 80", line)
        self.assertIn("[flow/games]", line)

    def test_window_resets_after_a_report(self):
        p = self.make()
        self.t[0] = 6.0
        p.frame(0.001, 0.001, 0.001, 0.001, "a")
        self.assertEqual(len(self.out), 1)
        p.frame(0.001, 0.001, 0.001, 0.001, "a")
        self.assertEqual(len(self.out), 1)


if __name__ == "__main__":
    unittest.main()
