import unittest
from unittest import mock

from tests import helpers

menu = helpers.load_menu()


class FakeSurface:
    made = 0

    def __init__(self, size=(1, 1), *a, **k):
        self.size = (int(size[0]), int(size[1]))
        self.alpha = 255
        FakeSurface.made += 1

    def get_size(self): return self.size
    def get_width(self): return self.size[0]
    def get_height(self): return self.size[1]
    def set_alpha(self, a): self.alpha = a
    def fill(self, *a, **k): pass
    def blit(self, *a, **k): pass
    def copy(self): return FakeSurface(self.size)


class FakeFont:
    def render(self, text, aa, col, *bg): return FakeSurface((8 * len(text), 16))
    def size(self, text): return (8 * len(text), 16)
    def set_bold(self, b): pass
    def get_height(self): return 16


def fake_pygame():
    pg = mock.MagicMock()
    pg.SRCALPHA = 65536
    pg.Surface = FakeSurface
    pg.transform.smoothscale = mock.Mock(side_effect=lambda s, size: FakeSurface(size))
    pg.transform.scale = mock.Mock(side_effect=lambda s, size: FakeSurface(size))
    pg.font.Font = lambda *a, **k: FakeFont()
    return pg


class LevelTests(unittest.TestCase):
    def test_resting_sizes_hit_a_level_exactly(self):
        for S in (240, 335, 348, 360):
            for scale, li in ((1.0, 0), (0.62, 4), (0.45, 7)):
                tw = S * scale
                got = menu.flow_level_index(tw, S)
                self.assertEqual(got, li, (S, scale))
                self.assertEqual(menu.flow_level_width(S, got), max(16, int(round(tw))))

    def test_level_is_never_smaller_than_the_target_and_gaps_stay_small(self):
        S = 335
        for tw in range(int(S * 0.45), S + 1):
            li = menu.flow_level_index(tw, S)
            w = menu.flow_level_width(S, li)
            self.assertGreaterEqual(w, tw - 1)
            self.assertLessEqual(w / float(tw), 1.16)

    def test_lru_drops_the_oldest_not_everything(self):
        d = {}
        for i in range(5):
            menu._lru_put(d, i, i + 1, 3)
        self.assertEqual(list(d), [2, 3, 4])
        menu._lru_get(d, 2)
        menu._lru_put(d, 9, 1, 3)
        self.assertEqual(list(d), [4, 2, 9])


class CarouselTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(menu, "pygame", fake_pygame())
        self.pg = p.start()
        self.addCleanup(p.stop)
        for name in ("cards", "glow", "shadow", "fonts"):
            menu._FLOW[name].clear()
        menu._FLOW["warm"] = None
        menu._FLOW["S"] = 300
        menu.FONT_PATH[0] = None
        self.cards = [{"title": "Game %d" % i, "sub": "x", "hue": i * 20, "tag": "GBA", "abbr": "G%d" % i, "icon": None, "fav": False}
                      for i in range(12)]

    def draw(self, fx, fade=1.0):
        c = FakeSurface((menu.W, menu.H))
        f = FakeFont()
        menu.draw_flow_level(c, f, f, self.cards, fx, fade, "", [("A", "Open")], ("", ""), "12:00", None, False)

    def test_warm_stops_at_its_budget_and_finishes_later(self):
        menu.flow_warm(self.cards, 0, 0.0)
        built = sum(1 for lv in menu._FLOW["cards"].values() for x in lv if x is not None)
        self.assertGreaterEqual(built, 1)
        for _ in range(500):
            menu.flow_warm(self.cards, 0, 0.0)
            if menu._FLOW["warm"]:
                break
        self.assertTrue(menu._FLOW["warm"])
        n = len(menu._FLOW["cards"])
        self.assertLessEqual(n, menu.FLOW_CACHE_CARDS)
        for dist in (0, 1, 2, 10, 11):
            g = self.cards[dist]
            lv = menu._FLOW["cards"][(g["hue"], g["tag"], g["abbr"], 300, None)]
            self.assertTrue(all(x is not None for x in lv), dist)

    def test_glide_after_warming_never_smoothscales(self):
        for _ in range(500):
            menu.flow_warm(self.cards, 0, 1.0)
            if menu._FLOW["warm"]:
                break
        self.draw(0.0)
        self.pg.transform.smoothscale.reset_mock()
        for k in range(1, 20):
            self.draw(k / 20.0)
        big = [c for c in self.pg.transform.smoothscale.call_args_list if min(c[0][1]) >= 100]
        self.assertEqual(big, [])

    def test_wraps_around_the_ends(self):
        menu.flow_warm(self.cards, 11, 1.0)
        menu.flow_warm(self.cards, -1, 1.0)
        self.draw(11.4)
        self.draw(-0.6)

    def test_two_covers_and_empty_lists_work(self):
        for n in (0, 1, 2):
            self.cards = self.cards[:n]
            menu.flow_warm(self.cards, 0, 1.0)
            self.draw(0.0)


class CoverTests(unittest.TestCase):
    """Cover art must never be decoded and scaled inside a frame."""

    def setUp(self):
        p = mock.patch.object(menu, "pygame", fake_pygame())
        self.pg = p.start()
        self.addCleanup(p.stop)
        for name in ("cards", "glow", "shadow", "fonts", "jobs"):
            menu._FLOW[name].clear()
        menu._FLOW["warm"] = None
        menu._FLOW["S"] = 300
        menu.FONT_PATH[0] = None
        self.cards = [{"title": "Game %d" % i, "sub": "x", "hue": i * 20, "tag": "GBA", "abbr": "G%d" % i, "icon": None,
                       "fav": False, "art": "/art/%d.png" % i} for i in range(8)]
        self.steps = []

    def fake_steps(self, path, S, n=3, result="surface"):
        self.steps.append(path)
        for _ in range(n):
            yield
        return FakeSurface((S, S)) if result == "surface" else None

    def key(self, i):
        g = self.cards[i]
        return menu._flow_key(g["hue"], g["tag"], g["abbr"], 300, None, g["art"])

    def test_draw_shows_the_gradient_and_never_builds_a_cover(self):
        with mock.patch.object(menu, "_flow_art_steps", side_effect=AssertionError("decoded in a frame")):
            c = FakeSurface((menu.W, menu.H))
            menu.draw_flow_level(c, FakeFont(), FakeFont(), self.cards, 0.0, 1.0, "", [("A", "Open")], ("", ""), "12:00", None, False)
        self.assertNotIn(self.key(0), menu._FLOW["cards"])

    def test_warm_builds_a_cover_a_step_at_a_time(self):
        with mock.patch.object(menu, "_flow_art_steps", side_effect=self.fake_steps):
            menu.flow_warm(self.cards, 0, 0.0)
            self.assertNotIn(self.key(0), menu._FLOW["cards"])  # one step per call, not the whole cover
            self.assertIn(self.key(0), menu._FLOW["jobs"])
            for _ in range(10):
                menu.flow_warm(self.cards, 0, 0.0)
            self.assertIn(self.key(0), menu._FLOW["cards"])
            self.assertNotIn(self.key(0), menu._FLOW["jobs"])
        self.assertEqual(self.steps.count("/art/0.png"), 1)  # built once, not restarted every call

    def test_a_cover_that_cannot_be_read_falls_back_to_the_gradient(self):
        with mock.patch.object(menu, "_flow_art_steps", side_effect=lambda p, S: self.fake_steps(p, S, 1, None)):
            for _ in range(6):
                menu.flow_warm(self.cards, 0, 0.0)
        lv = menu._FLOW["cards"][self.key(0)]
        self.assertIsNotNone(lv[0])

    def test_half_built_covers_are_dropped_when_you_scroll_away(self):
        with mock.patch.object(menu, "_flow_art_steps", side_effect=lambda p, S: self.fake_steps(p, S, 50)):
            menu.flow_warm(self.cards, 0, 0.0)
            self.assertIn(self.key(0), menu._FLOW["jobs"])
            self.cards = self.cards + [dict(c, art="/art/new%d.png" % i, abbr="N%d" % i) for i, c in enumerate(self.cards)] * 3
            menu.flow_warm(self.cards, 12, 0.0)
        self.assertNotIn(self.key(0), menu._FLOW["jobs"])


class MovingTests(unittest.TestCase):
    """While a glide runs, flow_warm must not start anything heavy."""

    def setUp(self):
        p = mock.patch.object(menu, "pygame", fake_pygame())
        self.pg = p.start()
        self.addCleanup(p.stop)
        for name in ("cards", "glow", "shadow", "fonts", "jobs"):
            menu._FLOW[name].clear()
        menu._FLOW["warm"] = None
        menu._FLOW["S"] = 300
        menu.FONT_PATH[0] = None
        self.cards = [{"title": "Game %d" % i, "sub": "x", "hue": i * 20, "tag": "GBA", "abbr": "G%d" % i, "icon": None,
                       "fav": False, "art": "/art/%d.png" % i} for i in range(30)]

    def test_moving_never_decodes_covers_or_scales_levels(self):
        with mock.patch.object(menu, "_flow_art_steps", side_effect=AssertionError("decoded while moving")):
            for _ in range(40):
                menu.flow_warm(self.cards, 0, 0.004, True)
        self.pg.transform.smoothscale.assert_not_called()
        self.assertEqual(menu._FLOW["jobs"], {})
        self.assertIsNone(menu._FLOW["warm"])

    def test_moving_builds_one_cheap_card_per_call_nearest_first(self):
        menu.flow_warm(self.cards, 10, 0.004, True)
        self.assertEqual(len(menu._FLOW["cards"]), 1)
        g = self.cards[10]
        self.assertIn(menu._flow_key(g["hue"], g["tag"], g["abbr"], 300, None), menu._FLOW["cards"])

    def test_a_shoulder_jump_finds_its_cards_ready(self):
        for _ in range(60):
            menu.flow_warm(self.cards, 10, 0.004, True)
        for i in range(10 + menu.FLOW_JUMP - 2, 10 + menu.FLOW_JUMP + 3):
            g = self.cards[i]
            self.assertIn(menu._flow_key(g["hue"], g["tag"], g["abbr"], 300, None), menu._FLOW["cards"], i)

    def test_moving_cache_stays_inside_its_cap(self):
        for c in range(0, 30):
            for _ in range(20):
                menu.flow_warm(self.cards, c, 0.004, True)
        self.assertLessEqual(len(menu._FLOW["cards"]), menu.FLOW_CACHE_CARDS)

    def test_resting_afterwards_still_finishes_the_covers(self):
        for _ in range(30):
            menu.flow_warm(self.cards, 0, 0.004, True)
        with mock.patch.object(menu, "_flow_art_steps", side_effect=lambda p, S: iter(())):
            for _ in range(300):
                menu.flow_warm(self.cards, 0, 0.012, False)
                if menu._FLOW["warm"]:
                    break
        self.assertTrue(menu._FLOW["warm"])


if __name__ == "__main__":
    unittest.main()
