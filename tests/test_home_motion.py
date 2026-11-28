"""Motion helpers shared by the RG OS tile and RG XMB launchers (entrance, spring focus ring, embers, XMB pulses)."""
import types
import unittest
from unittest import mock

from tests.helpers import load_menu

menu = load_menu()


class Surf:
    def __init__(self, size=(8, 8), *a, **k):
        self.size = (int(size[0]), int(size[1]))

    def get_width(self):
        return self.size[0]

    def get_height(self):
        return self.size[1]

    def get_clip(self):
        return (0, 0) + self.size

    def set_clip(self, r):
        pass

    def blit(self, *a, **k):
        pass

    def fill(self, *a, **k):
        pass

    def set_alpha(self, a):
        pass

    def copy(self):
        return Surf(self.size)


class Font:
    def render(self, text, aa, col):
        return Surf((8 * len(text), 16))

    def size(self, text):
        return (8 * len(text), 16)

    def get_linesize(self):
        return 18


def fake_pygame():
    pg = types.SimpleNamespace(SRCALPHA=1, BLEND_RGBA_MULT=1, Surface=Surf, Rect=lambda *a: a)
    pg.draw = types.SimpleNamespace(rect=lambda *a, **k: None, circle=lambda *a, **k: None, line=lambda *a, **k: None,
                                    polygon=lambda *a, **k: None)
    pg.transform = types.SimpleNamespace(smoothscale=lambda s, size: Surf(size))
    return pg


class HomeIntroTests(unittest.TestCase):
    def test_replays_after_a_gap_and_on_launcher_switch(self):
        menu.home_intro("rgos", 100.0)
        self.assertAlmostEqual(menu.home_intro("rgos", 100.1), 0.1)
        self.assertAlmostEqual(menu.home_intro("rgos", 100.2), 0.2)
        self.assertAlmostEqual(menu.home_intro("rgos", 101.0), 0.0)
        self.assertAlmostEqual(menu.home_intro("xmb", 101.05), 0.0)
        self.assertAlmostEqual(menu.home_intro("xmb", 101.15), 0.1)


class RingTests(unittest.TestCase):
    def test_spring_settles_on_the_target_and_overshoots_a_little(self):
        menu._RING["p"] = None
        menu._ring_step(0, 0, 1 / 60.0, 0.0)
        far, now = 0.0, 0.0
        for _ in range(240):
            now += 1 / 60.0
            speed, rem = menu._ring_step(100, 40, 1 / 60.0, now)
            far = max(far, menu._RING["p"][0])
        self.assertGreater(far, 100.0)
        self.assertLess(far, 110.0)
        self.assertEqual((speed, rem), (0.0, 0.0))
        self.assertEqual(menu._RING["p"], [100.0, 40.0])

    def test_large_frame_steps_stay_stable(self):
        menu._RING["p"] = None
        menu._ring_step(0, 0, 0.05, 0.0)
        for i in range(60):
            menu._ring_step(300, 200, 0.05, i * 0.05)
        self.assertAlmostEqual(menu._RING["p"][0], 300.0, places=3)


class XmbFxTests(unittest.TestCase):
    def test_tracks_category_and_item_changes(self):
        fx = menu.xmb_fx(1, 0, 10.0, 0.0)
        self.assertGreater(fx["sel_t"], 5)
        fx = menu.xmb_fx(1, 2, 11.0, 1.0)
        self.assertAlmostEqual(fx["sel_t"], 0.0)
        self.assertGreater(fx["cat_t"], 5)
        fx = menu.xmb_fx(2, 0, 11.2, 1.2)
        self.assertAlmostEqual(fx["cat_t"], 0.0)
        self.assertAlmostEqual(fx["sel_t"], 0.0)


class DrawSmokeTests(unittest.TestCase):
    def test_xmb_home_draws_through_entrance_and_pulses(self):
        items = [{"icon": "games", "label": "Item %d" % i, "sub": "sub"} for i in range(6)]
        with mock.patch.object(menu, "pygame", fake_pygame()), mock.patch.object(menu, "xmb_icon", lambda *a: Surf((8, 8))):
            c, f = Surf((menu.W, menu.H)), Font()
            now = 50.0
            for step in range(120):
                now += 1 / 30.0
                el = menu.home_intro("xmb", now)
                fx = menu.xmb_fx(1 + (step > 60), 0 if step < 30 else 2, now, el)
                menu.draw_xmb_home(c, f, f, 1.0, 1 + (step > 60), items, 0.0, min(1.0, step / 20.0), fx)
            menu.draw_xmb_home(c, f, f, 1.0, 1, items, 0.0, 1.0)

    def test_ring_shine_and_embers_draw(self):
        with mock.patch.object(menu, "pygame", fake_pygame()):
            c, now = Surf((menu.W, menu.H)), 5.0
            menu._RING["p"] = None
            for step in range(200):
                now += 1 / 60.0
                speed, rem = menu._ring_step(40 + (step > 20) * 200, 90, 1 / 60.0, now)
                menu._draw_ring(c, now, 180, 120, 1.0, speed, rem)
                menu.home_embers(c, now, 1 / 60.0)


if __name__ == "__main__":
    unittest.main()
