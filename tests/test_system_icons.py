import types
import unittest
from unittest import mock

from tests import helpers

menu = helpers.load_menu()


class Recorder:
    """Stands in for pygame.draw and keeps the extent of everything drawn."""

    def __init__(self):
        self.xs, self.ys, self.calls = [], [], 0
        self.draw = types.SimpleNamespace(rect=self.rect, circle=self.circle, line=self.line, lines=self.lines, polygon=self.polygon)

    def _pt(self, x, y):
        self.xs.append(x)
        self.ys.append(y)

    def rect(self, c, col, r, *a, **k):
        self.calls += 1
        self._pt(r[0], r[1])
        self._pt(r[0] + r[2], r[1] + r[3])

    def circle(self, c, col, ctr, rad, *a, **k):
        self.calls += 1
        self._pt(ctr[0] - rad, ctr[1] - rad)
        self._pt(ctr[0] + rad, ctr[1] + rad)

    def line(self, c, col, a, b, *args, **k):
        self.calls += 1
        self._pt(*a)
        self._pt(*b)

    def lines(self, c, col, closed, pts, *a, **k):
        self.calls += 1
        for p in pts:
            self._pt(*p)

    def polygon(self, c, col, pts, *a, **k):
        self.calls += 1
        for p in pts:
            self._pt(*p)


class SystemIconTests(unittest.TestCase):
    def test_every_system_has_its_own_icon(self):
        for sy in menu.SYSTEMS:
            self.assertEqual(menu.system_icon(sy[0]), "sys_" + sy[0], sy[0])
            self.assertIn("sys_" + sy[0], menu.ICONS)

    def test_a_system_without_an_icon_falls_back_to_the_pad(self):
        self.assertEqual(menu.system_icon("somethingnew"), "games")
        self.assertEqual(menu.system_icon(""), "games")

    def test_icons_draw_something_inside_the_96px_box(self):
        for sid, fn in menu.SYSTEM_ICONS.items():
            rec = Recorder()
            with mock.patch.object(menu, "pygame", types.SimpleNamespace(draw=rec.draw)):
                fn(object(), 48, 48, (255, 255, 255, 255), (0, 0, 0, 0))
            self.assertGreater(rec.calls, 3, sid)
            self.assertGreaterEqual(min(rec.xs), 2, sid)
            self.assertGreaterEqual(min(rec.ys), 2, sid)
            self.assertLessEqual(max(rec.xs), 94, sid)
            self.assertLessEqual(max(rec.ys), 94, sid)

    def test_menu_icons_are_still_there(self):
        for k in ("games", "settings", "power", "tools", "files"):
            self.assertIn(k, menu.ICONS)


if __name__ == "__main__":
    unittest.main()
