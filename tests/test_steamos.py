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
        menu._STEAM.update({"bg": (None, None, None), "prev": None, "dim": (None, None)})
        menu.STEAM_UI.update({"open": False, "slide": 0.0, "sel": 0, "wifi": None})
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
        menu._steam_backdrop(c, b)
        self.assertIsNotNone(menu._STEAM["prev"])
        self.assertIsNot(menu._STEAM["prev"][0], menu._STEAM["bg"][2])


if __name__ == "__main__":
    unittest.main()
