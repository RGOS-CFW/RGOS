import json
import os
import tempfile
import unittest
from unittest import mock

from tests.helpers import load_menu

menu = load_menu()


def game(i, sid="gba"):
    return {"title": "Game %d" % i, "path": "/r/%s/g%d.gba" % (sid, i), "tag": "GBA", "core": "retroarch", "sid": sid, "card": 1}


class RomSizeTests(unittest.TestCase):
    def test_scan_does_not_stat_and_size_is_read_once_on_demand(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "roms", "ports"))
        rom = os.path.join(root, "roms", "ports", "A.sh")
        with open(rom, "wb") as f:
            f.write(b"x" * 1234)
        with mock.patch.object(menu, "ROMS_ROOT", root), mock.patch.object(menu, "rom_roots", lambda: [(1, root)]):
            games = menu.scan_roms()
        self.assertEqual(len(games), 1)
        self.assertNotIn("size", games[0])
        self.assertEqual(menu.rom_size(games[0]), 1234)
        os.remove(rom)
        self.assertEqual(menu.rom_size(games[0]), 1234)

    def test_missing_file_is_zero(self):
        self.assertEqual(menu.rom_size({"path": "/nope/x.gba"}), 0)


class ScanCacheTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "sub", "scan-cache.json")

    def test_round_trip_drops_lazy_size(self):
        games = [game(1), dict(game(2), size=99)]
        menu.save_scan_cache(games, self.path)
        got = menu.load_scan_cache(self.path)
        self.assertEqual([g["path"] for g in got], [g["path"] for g in games])
        self.assertNotIn("size", got[1])

    def test_missing_damaged_and_foreign_root_give_none(self):
        self.assertIsNone(menu.load_scan_cache(self.path))
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertIsNone(menu.load_scan_cache(self.path))
        with open(self.path, "w") as f:
            json.dump({"v": 1, "root": "/somewhere/else", "games": [game(1)]}, f)
        self.assertIsNone(menu.load_scan_cache(self.path))
        with open(self.path, "w") as f:
            json.dump({"v": 1, "root": menu.ROMS_ROOT, "games": [{"title": 5}]}, f)
        self.assertIsNone(menu.load_scan_cache(self.path))

    def test_same_games(self):
        a = [game(1), game(2)]
        self.assertTrue(menu.same_games(a, [dict(g, size=5) for g in a]))
        self.assertFalse(menu.same_games(a, a[:1]))
        self.assertFalse(menu.same_games(a, [game(1), game(3)]))

    def test_rescan_thread_refreshes_the_cache(self):
        import time
        rs = menu.Rescan()
        with mock.patch.object(menu, "scan_roms", return_value=[game(7)]), \
                mock.patch.object(menu, "SCAN_CACHE", self.path):
            rs.start()
            end = time.monotonic() + 2
            while rs.take() is None and time.monotonic() < end:
                time.sleep(0.005)
        self.assertEqual(menu.load_scan_cache(self.path)[0]["title"], "Game 7")


if __name__ == "__main__":
    unittest.main()
