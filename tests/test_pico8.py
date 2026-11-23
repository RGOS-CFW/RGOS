import os
import tempfile
import unittest
from unittest import mock

from tests.helpers import load_menu
from tests.test_dreamcast import load
from tests.test_launch import load_launch

menu = load_menu()
cores = load("cores")
coreinstall = load("coreinstall")
artwork = load("artwork")


class Pico8Tests(unittest.TestCase):
    def row(self):
        return next(sy for sy in menu.ALL_SYSTEMS if sy[0] == "pico8")

    def test_system_row(self):
        sid, tag, kind, exts, name = self.row()
        self.assertEqual((tag, kind, name), ("P8", "retroarch", "PICO-8"))
        self.assertEqual(exts, (".p8", ".p8.png"))

    def test_core_tables(self):
        self.assertEqual(cores.default_core("pico8"), "fake08")
        self.assertEqual(cores.compatible_cores("pico8", ["retro8", "fake08", "mgba"]), ["fake08", "retro8"])
        self.assertEqual(cores.compatible_cores("pico8", ["mgba"]), [])
        self.assertEqual(menu.CORE_NAMES["fake08"], "fake-08")
        self.assertEqual(menu.CORE_NAMES["retro8"], "retro8")

    def test_hidden_until_a_core_is_installed_and_offered_by_the_installer(self):
        systems = [(s[0], s[1], s[4]) for s in menu.ALL_SYSTEMS if s[2] == "retroarch"]
        self.assertIn("pico8", coreinstall.uncovered(systems, cores.SYSTEM_CORE_COMPATIBILITY, ["mgba"]))
        self.assertNotIn("pico8", coreinstall.uncovered(systems, cores.SYSTEM_CORE_COMPATIBILITY, ["retro8"]))
        rows = {r["core"]: r for r in coreinstall.candidates(systems, cores.SYSTEM_CORE_COMPATIBILITY, [], menu.CORE_NAMES)}
        self.assertEqual(rows["fake08"]["systems"], ["P8"])
        self.assertEqual(rows["retro8"]["systems"], ["P8"])

    def test_icon_and_sd_card_folder(self):
        self.assertEqual(menu.system_icon("pico8"), "sys_pico8")
        self.assertIn("pico8", load("sdcard").SYSTEM_DIRS)

    def test_titles_drop_both_extensions_of_a_png_cart(self):
        self.assertEqual(menu.pretty("celeste.p8"), "celeste")
        self.assertEqual(menu.pretty("celeste.p8.png"), "celeste")
        self.assertEqual(menu.pretty("Some_Game (v2).p8.png"), "Some Game")
        self.assertEqual(menu.pretty("photo.png"), "photo")
        self.assertEqual(artwork.stem_of("/r/pico8/celeste.p8.png"), "celeste")
        self.assertEqual(artwork.stem_of("/r/pico8/celeste.p8"), "celeste")
        self.assertEqual(load_launch().game_title("/r/pico8/celeste.p8.png"), "celeste")

    def test_scan_lists_p8_and_p8_png_but_not_plain_png(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "roms", "pico8"))
        for n in ("a.p8", "b.p8.png", "C.P8.PNG", "cover.png", "notes.txt", ".hidden.p8"):
            open(os.path.join(root, "roms", "pico8", n), "wb").write(b"x")
        with mock.patch.object(menu, "rom_roots", lambda: [(1, root)]), \
                mock.patch.object(menu, "SYSTEMS", list(menu.ALL_SYSTEMS)):
            games = menu.scan_roms()
        self.assertEqual(sorted(g["path"].rsplit("/", 1)[1] for g in games), ["C.P8.PNG", "a.p8", "b.p8.png"])
        self.assertEqual({g["sid"] for g in games}, {"pico8"})


if __name__ == "__main__":
    unittest.main()
