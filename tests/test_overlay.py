import importlib.machinery
import importlib.util
import os
import unittest

from tests import helpers


def load_overlay():
    loader = importlib.machinery.SourceFileLoader("rgos_overlay", os.path.join(helpers.RGOS, "rgos-overlay"))
    spec = importlib.util.spec_from_loader("rgos_overlay", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class FakeScreen:
    """A 1-row 'framebuffer' region: a list of bytes rows the test (the 'program') can repaint."""
    def __init__(self, fill=b"a"):
        self.rows, self.pos, self.writes = [fill * 4, fill * 4], (0, 0), 0

    def position(self):
        return self.pos

    def read(self):
        return list(self.rows)

    def write(self, rows):
        self.rows, self.writes = list(rows), self.writes + 1

    def compose(self, saved, pct):
        return [b"B%02d" % pct + b"x"] * len(saved)


class Clock:
    def __init__(self):
        self.t = 10.0

    def __call__(self):
        return self.t


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.ov = load_overlay()

    def test_parse_volume(self):
        self.assertEqual(self.ov.parse_volume("70 1700000000000\n"), (70, "1700000000000"))
        self.assertEqual(self.ov.parse_volume("250 5"), (100, "5"))
        self.assertIsNone(self.ov.parse_volume("junk"))
        self.assertIsNone(self.ov.parse_volume(""))

    def test_parse_theme_falls_back(self):
        t = self.ov.parse_theme("1,2,3 4,5,6 7,8,9 10,11,12")
        self.assertEqual((t["BG"], t["PANEL"], t["ACCENT"], t["TEXT"]), ((1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12)))
        self.assertEqual(self.ov.parse_theme("nope"), self.ov.DEFAULT_THEME)
        self.assertEqual(self.ov.parse_theme("1,2 4,5,6 7,8,9 10,11,12"), self.ov.DEFAULT_THEME)

    def test_rect_rotation_keeps_the_bar_on_screen_and_same_area(self):
        lw, lh = 720, 480
        rect = self.ov.bar_geometry(lw, lh)
        for rot in (0, 90, 180, 270):
            fw, fh = self.ov.logical_size(lw, lh, rot)          # framebuffer size for this rotation
            x, y, w, h = self.ov.to_fb_rect(rect, lw, lh, rot)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, fw)
            self.assertLessEqual(y + h, fh)
            self.assertEqual(w * h, rect[2] * rect[3])

    def test_rotation_maps_a_corner_like_a_clockwise_turn(self):
        # upright bottom-left pixel (0, lh-1) of a 720x480 screen lands at (0, 0) after turning clockwise 90
        self.assertEqual(self.ov.to_fb_rect((0, 479, 1, 1), 720, 480, 90)[:2], (0, 0))
        self.assertEqual(self.ov.to_fb_rect((0, 0, 1, 1), 720, 480, 180)[:2], (719, 479))
        self.assertEqual(self.ov.to_fb_rect((0, 0, 1, 1), 720, 480, 270)[:2], (0, 719))


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_overlay()
        self.scr, self.clk = FakeScreen(), Clock()
        self.ov = self.mod.Overlay(self.scr, self.clk)

    def test_show_draws_then_hide_restores_the_original_pixels(self):
        orig = list(self.scr.rows)
        self.ov.show(40)
        self.assertNotEqual(self.scr.rows, orig)
        self.assertTrue(self.ov.tick())
        self.clk.t += self.mod.HOLD + 0.1
        self.assertFalse(self.ov.tick())
        self.assertEqual(self.scr.rows, orig)

    def test_a_new_value_redraws_and_still_restores_the_first_background(self):
        orig = list(self.scr.rows)
        self.ov.show(40)
        self.clk.t += 1.0
        self.ov.show(55)
        self.assertTrue(self.scr.rows[0].startswith(b"B55"))
        self.clk.t += 1.0
        self.assertTrue(self.ov.tick())                      # the hold restarted with the second press
        self.clk.t += 1.0
        self.assertFalse(self.ov.tick())
        self.assertEqual(self.scr.rows, orig)

    def test_program_repaint_under_the_bar_is_covered_again_and_kept_on_hide(self):
        self.ov.show(40)
        self.scr.rows = [b"zzzz", b"zzzz"]                   # the game drew a new frame over the bar
        self.assertTrue(self.ov.tick())
        self.assertTrue(self.scr.rows[0].startswith(b"B40"))  # bar put back on top of the new frame
        self.scr.rows = [b"yyyy", b"yyyy"]                   # another frame
        self.clk.t += self.mod.HOLD + 0.1
        self.assertFalse(self.ov.tick())
        self.assertEqual(self.scr.rows, [b"yyyy", b"yyyy"])   # not overwritten with stale pixels

    def test_page_flip_does_not_restore_stale_pixels(self):
        self.ov.show(40)
        self.scr.pos = (0, 480)
        self.scr.rows = [b"nnnn", b"nnnn"]
        self.clk.t += 0.2
        self.ov.tick()
        self.clk.t += self.mod.HOLD + 0.1
        self.ov.tick()
        self.assertNotIn(b"aaaa", self.scr.rows)

    def test_idle_tick_touches_nothing(self):
        self.assertFalse(self.ov.tick())
        self.assertEqual(self.scr.writes, 0)


if __name__ == "__main__":
    unittest.main()


class RetroArchOverlayTests(unittest.TestCase):
    def test_volume_text(self):
        ov = load_overlay()
        self.assertEqual(ov.volume_text(0), "Volume   0%  [" + "-" * 20 + "]")
        self.assertEqual(ov.volume_text(100), "Volume 100%  [" + "#" * 20 + "]")
        self.assertEqual(ov.volume_text(500).count("#"), 20)

    def test_retroarch_running_reads_flag(self):
        import json, tempfile
        ov = load_overlay()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ingame")
            self.assertFalse(ov.retroarch_running(p))
            for kind, want in (("retroarch", True), ("native", False)):
                with open(p, "w") as f:
                    json.dump({"kind": kind}, f)
                self.assertEqual(ov.retroarch_running(p), want)
            open(p, "w").close()
            self.assertFalse(ov.retroarch_running(p))

    def test_ra_message_sends_show_msg(self):
        import socket
        ov = load_overlay()
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        srv.settimeout(2)
        try:
            self.assertTrue(ov.ra_message("Volume  50%", addr=srv.getsockname()))
            self.assertEqual(srv.recvfrom(256)[0], b"SHOW_MSG Volume  50%")
        finally:
            srv.close()
