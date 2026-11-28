import os
import tempfile
import unittest
from unittest import mock

from tests.helpers import load_menu

menu = load_menu()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "rgos", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cores = load("cores")
biosctl = load("biosctl")
coreinstall = load("coreinstall")


class DreamcastTests(unittest.TestCase):
    def row(self):
        return next(sy for sy in menu.ALL_SYSTEMS if sy[0] == "dreamcast")

    def test_system_row(self):
        sid, tag, kind, exts, name = self.row()
        self.assertEqual((tag, kind, name), ("DC", "retroarch", "Sega Dreamcast"))
        for ext in (".gdi", ".cdi", ".chd", ".cue", ".m3u"):
            self.assertIn(ext, exts)

    def test_core_tables(self):
        self.assertEqual(cores.default_core("dreamcast"), "flycast")
        self.assertEqual(cores.compatible_cores("dreamcast", ["flycast", "mgba"]), ["flycast"])
        self.assertEqual(cores.compatible_cores("dreamcast", ["mgba"]), [])
        self.assertEqual(menu.CORE_NAMES["flycast"], "Flycast")

    def test_hidden_until_flycast_is_installed_and_offered_by_the_installer(self):
        systems = [(s[0], s[1], s[4]) for s in menu.ALL_SYSTEMS if s[2] == "retroarch"]
        self.assertIn("dreamcast", coreinstall.uncovered(systems, cores.SYSTEM_CORE_COMPATIBILITY, ["mgba"]))
        self.assertNotIn("dreamcast", coreinstall.uncovered(systems, cores.SYSTEM_CORE_COMPATIBILITY, ["flycast"]))
        rows = {r["core"]: r for r in coreinstall.candidates(systems, cores.SYSTEM_CORE_COMPATIBILITY, [], menu.CORE_NAMES)}
        self.assertEqual(rows["flycast"]["systems"], ["DC"])
        self.assertFalse(rows["flycast"]["installed"])

    def test_has_its_own_icon(self):
        self.assertEqual(menu.system_icon("dreamcast"), "sys_dreamcast")

    def test_second_card_and_bios(self):
        sd = load("sdcard")
        self.assertIn("dreamcast", sd.SYSTEM_DIRS)
        files = [b[0] for b in biosctl.BIOS["dreamcast"]]
        self.assertEqual(files, ["dc/dc_boot.bin", "dc/dc_flash.bin"])
        self.assertTrue(all(b[3] == () for b in biosctl.BIOS["dreamcast"]))

    def test_scan_lists_discs_but_not_track_files(self):
        root = tempfile.mkdtemp()
        game = os.path.join(root, "roms", "dreamcast", "Sonic Adventure")
        os.makedirs(game)
        for n in ("disc.gdi", "track01.bin", "track02.raw", "track03.bin"):
            open(os.path.join(game, n), "wb").write(b"x")
        open(os.path.join(root, "roms", "dreamcast", "Crazy Taxi.chd"), "wb").write(b"x")
        with mock.patch.object(menu, "rom_roots", lambda: [(1, root)]), \
                mock.patch.object(menu, "SYSTEMS", list(menu.ALL_SYSTEMS)):
            games = menu.scan_roms()
        self.assertEqual(sorted(g["path"].rsplit("/", 1)[1] for g in games), ["Crazy Taxi.chd", "disc.gdi"])
        self.assertTrue(all(g["sid"] == "dreamcast" and g["tag"] == "DC" for g in games))


if __name__ == "__main__":
    unittest.main()
