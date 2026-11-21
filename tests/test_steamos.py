import unittest
from unittest import mock

from tests import helpers
from tests.test_flow_smooth import FakeFont, FakeSurface, fake_pygame

menu = helpers.load_menu()


class HelperTests(unittest.TestCase):
    def test_clock_is_12_hour(self):
        self.assertEqual(menu.steam_clock("00:05"), "12:05 AM")
        self.assertEqual(menu.steam_clock("09:41"), "9:41 AM")
        self.assertEqual(menu.steam_clock("12:00"), "12:00 PM")
        self.assertEqual(menu.steam_clock("23:59"), "11:59 PM")
        self.assertEqual(menu.steam_clock("nonsense"), "nonsense")

    def test_heading(self):
        self.assertEqual(menu.steam_heading(""), "Home")
        self.assertEqual(menu.steam_heading("Recents"), "Recent Games")
        self.assertEqual(menu.steam_heading("Game Boy Advance"), "Game Boy Advance")

    def test_hints_become_deck_prompts(self):
        base = [("<>", "Browse"), ("A", "Play"), ("Y", "Favorite"), ("B", "Back")]
        self.assertEqual(menu.steam_hints(base, True, False)[1], ("A", "Play"))
        self.assertEqual(menu.steam_hints(base, False, False)[1], ("A", "Select"))
        self.assertEqual(menu.steam_hints(base, True, False)[-1], ("X", "Rescan"))
        home = [("<>", "Browse"), ("A", "Open"), ("MENU", "First")]
        self.assertNotIn("MENU", [k for k, _l in menu.steam_hints(home, False, False)])
        self.assertEqual(menu.steam_hints(base, True, True), [("A", "Select"), ("B", "Back")])

    def test_menu_has_the_expected_targets_and_start_row(self):
        self.assertEqual([k for k, _l in menu.STEAM_MENU], ["home", "games", "recents", "favorites", "tools", "settings", "power"])
        self.assertEqual(menu.steam_menu_index("home"), 0)
        self.assertEqual(menu.steam_menu_index("games"), 1)
        self.assertEqual(menu.steam_menu_index("recents"), 2)
        self.assertEqual(menu.steam_menu_index("favorites"), 3)

    def test_launcher_is_flow_like(self):
        self.assertIn("steamos", menu.FLOW_LIKE)


class DrawTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(menu, "pygame", fake_pygame())
        self.pg = p.start()
        self.addCleanup(p.stop)
        for name in ("cards", "glow", "shadow", "fonts"):
            menu._FLOW[name].clear()
        menu._FLOW["warm"] = None
        menu.FONT_PATH[0] = None
        menu._STEAM.update({"grad": (None, None), "shade": (None, None, None), "shown": None, "prev": None,
                            "dim": (None, None), "on": False})
        for name in ("heroes", "covers", "btn"):
            menu._STEAM[name].clear()
        menu.STEAM_UI.update({"open": False, "slide": 0.0, "sel": 0, "wifi": None, "rest": True})
        self.cards = [{"game": {}, "title": "Game %d" % i, "sub": "GBA", "hue": i * 20, "tag": "GBA", "abbr": "G%d" % i,
                       "icon": None, "fav": i == 1} for i in range(5)]

    def draw(self, cards=None, fx=0.0, hints=None, bat=(80, "Discharging"), crumb=""):
        c = FakeSurface((menu.W, menu.H))
        f = FakeFont()
        menu.draw_steam_level(c, f, f, self.cards if cards is None else cards, fx, 1.0, crumb,
                              hints or [("<>", "Browse"), ("A", "Play"), ("Y", "Favorite"), ("B", "Back")],
                              ("Nothing", "here"), "13:05", bat, False)

    def test_draws_with_and_without_cards(self):
        self.draw()
        self.draw(cards=[])
        self.draw(bat=None, crumb="Recents")

    def test_wifi_state_draws(self):
        for wifi in (None, True, False):
            menu.STEAM_UI["wifi"] = wifi
            self.draw()

    def test_side_menu_draws_open_closed_and_midway(self):
        for slide in (0.0, 0.4, 1.0):
            menu.STEAM_UI.update({"open": slide > 0, "slide": slide, "sel": 3})
            self.draw()

    def test_backdrop_crossfade_starts_when_focus_changes(self):
        a, b = FakeSurface((50, 50)), FakeSurface((50, 50))
        c = FakeSurface((menu.W, menu.H))
        menu._steam_backdrop(c, a)
        self.assertIsNone(menu._STEAM["prev"])
        first = menu._STEAM["shown"]
        menu._steam_backdrop(c, b)
        self.assertIsNotNone(menu._STEAM["prev"])
        self.assertIs(menu._STEAM["prev"][0], first)
        self.assertIsNot(menu._STEAM["prev"][0], menu._STEAM["shown"])

    def test_backdrop_holds_while_the_cursor_is_travelling(self):
        a, b = FakeSurface((50, 50)), FakeSurface((50, 50))
        c = FakeSurface((menu.W, menu.H))
        menu._steam_backdrop(c, a)
        shown = menu._STEAM["shown"]
        for _ in range(5):  # a held d-pad: no new hero is built, no crossfade starts
            menu._steam_backdrop(c, b, rest=False)
        self.assertIs(menu._STEAM["shown"], shown)
        self.assertIsNone(menu._STEAM["prev"])
        self.assertIsNone(menu._steam_hero_peek(b))
        menu._steam_backdrop(c, b, rest=True)
        self.assertIsNot(menu._STEAM["shown"], shown)
        self.assertIs(menu._STEAM["prev"][0], shown)

    def test_hero_is_built_once_per_capsule_and_reused(self):
        a = FakeSurface((50, 50))
        c = FakeSurface((menu.W, menu.H))
        h1 = menu._steam_hero(a, c)
        made = FakeSurface.made
        self.assertIs(menu._steam_hero(a, c), h1)
        self.assertIs(menu._steam_hero_peek(a), h1)
        self.assertEqual(FakeSurface.made, made)

    def test_hero_cache_is_bounded(self):
        c = FakeSurface((menu.W, menu.H))
        keep = [FakeSurface((50, 50)) for _ in range(menu.HERO_CACHE + 4)]
        for b in keep:
            menu._steam_hero(b, c)
        self.assertLessEqual(len(menu._STEAM["heroes"]), menu.HERO_CACHE)
        self.assertIsNotNone(menu._steam_hero_peek(keep[-1]))
        self.assertIsNone(menu._steam_hero_peek(keep[0]))

    def test_steady_frames_scale_and_build_nothing(self):
        self.draw(fx=0.0)
        scaled = self.pg.transform.smoothscale.call_count + self.pg.transform.scale.call_count
        self.draw(fx=0.0)
        self.draw(fx=0.0)
        self.assertEqual(self.pg.transform.smoothscale.call_count + self.pg.transform.scale.call_count, scaled)

    def test_a_glide_never_uses_the_per_frame_nearest_scale(self):
        for step in range(0, 11):
            self.draw(fx=step / 10.0)
        self.pg.transform.scale.assert_not_called()

    def test_cover_width_snaps_and_is_cached(self):
        S = 150
        lv = [FakeSurface((S, S))] + [None] * (len(menu.FLOW_LEVELS) - 1)
        key = ("k",)
        surf, wq = menu._steam_cover(key, lv, S, S)
        self.assertEqual((wq, surf.get_width()), (S, S))
        small = int(round(S * 0.8))
        surf, wq = menu._steam_cover(key, lv, S, small + 1)
        self.assertEqual((wq, surf.get_width()), (small, small))
        s2, wq2 = menu._steam_cover(key, lv, S, small - 1)
        self.assertIs(s2, surf)  # the same cached surface, nothing scaled again
        mid, wqm = menu._steam_cover(key, lv, S, 133)
        self.assertEqual(wqm % 4, 0)
        self.assertLessEqual(abs(wqm - 133), 3)

    def test_warm_prebuilds_heroes_and_skips_the_glow(self):
        self.draw(fx=0.0)  # marks the SteamOS launcher as the one drawn and sets the capsule size
        S = menu._FLOW["S"]
        for _ in range(300):
            menu.flow_warm(self.cards, 0, 1.0)
            if menu._FLOW["warm"]:
                break
        self.assertTrue(menu._FLOW["warm"])
        self.assertEqual(menu._FLOW["glow"], {})
        # the focused capsule and its neighbours already have a finished hero
        lvs = [menu._flow_draw_base(g["hue"], g["tag"], g["abbr"], S, g.get("icon"), g.get("art"))[1] for g in self.cards[:2]]
        for lv in lvs:
            self.assertIsNotNone(menu._steam_hero_peek(lv[0]))

    def test_prompt_width_matches_what_is_drawn(self):
        f = FakeFont()
        for arrows in (False, True):
            drawn = menu._steam_prompt(FakeSurface((menu.W, menu.H)), f, 100, 20, "<>", "Browse", arrows) - 100
            self.assertEqual(menu._steam_prompt_width(f, "<>", "Browse", arrows), drawn)
        self.assertEqual(menu._steam_prompt_width(f, "A", "Play"),
                         menu._steam_prompt(FakeSurface((menu.W, menu.H)), f, 0, 20, "A", "Play", False))

    def test_play_button_is_drawn_once_per_state(self):
        c = FakeSurface((menu.W, menu.H))
        f = FakeFont()
        menu._steam_play_button(c, 28, 300, 150, 44, "Play", f, True)
        self.assertEqual(len(menu._STEAM["btn"]), 1)
        menu._steam_play_button(c, 28, 300, 150, 44, "Play", f, True)
        self.assertEqual(len(menu._STEAM["btn"]), 1)
        menu._steam_play_button(c, 28, 300, 150, 44, "Play", f, False)
        self.assertEqual(len(menu._STEAM["btn"]), 2)


if __name__ == "__main__":
    unittest.main()
