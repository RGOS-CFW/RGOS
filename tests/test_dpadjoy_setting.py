import os
import unittest
from unittest import mock

from tests import helpers

menu = helpers.load_menu()
DEFAULT_PATH = menu.DPAD_JOY


class SettingsRowTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(helpers.sandbox(), "dpad-joystick")
        p = mock.patch.object(menu, "DPAD_JOY", self.path)
        p.start()
        self.addCleanup(p.stop)

    def test_row_exists_between_swap_ab_and_wifi_and_has_an_icon(self):
        rows = menu.SETTINGS_ROWS
        self.assertEqual(rows[rows.index("swapab") + 1], "dpadjoy")
        self.assertIn("dpadjoy", menu.ICONS)

    def test_toggle_creates_and_removes_the_file_the_hub_watches(self):
        self.assertFalse(menu.dpad_joy_on())
        self.assertTrue(menu.set_dpad_joy(True))
        self.assertTrue(os.path.exists(self.path))
        self.assertTrue(menu.dpad_joy_on())
        self.assertTrue(menu.set_dpad_joy(False))
        self.assertFalse(os.path.exists(self.path))
        self.assertTrue(menu.set_dpad_joy(False))

    def test_unwritable_location_reports_failure(self):
        blocker = os.path.join(os.path.dirname(self.path), "a-file")
        open(blocker, "w").close()
        with mock.patch.object(menu, "DPAD_JOY", os.path.join(blocker, "dpad-joystick")):
            self.assertFalse(menu.set_dpad_joy(True))

    def test_hub_and_menu_use_the_same_file(self):
        hub = helpers.load_hub()
        self.assertEqual(DEFAULT_PATH, "/var/lib/rgos/dpad-joystick")
        self.assertEqual(DEFAULT_PATH, hub.DPADJOY)

    def test_icon_draws_inside_its_box(self):
        canvas = mock.MagicMock()
        menu.icon_dpadjoy(canvas, 48, 48, (255, 255, 255), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
