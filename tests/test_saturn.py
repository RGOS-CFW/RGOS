import unittest

from tests.helpers import load_menu
from tests.test_dreamcast import load

menu = load_menu()
cores = load("cores")
coreinstall = load("coreinstall")
biosctl = load("biosctl")
sdcard = load("sdcard")


class SaturnTests(unittest.TestCase):
    def row(self):
        return next(sy for sy in menu.ALL_SYSTEMS if sy[0] == "saturn")

    def test_system_row(self):
        sid, tag, kind, exts, name = self.row()
        self.assertEqual((tag, kind, name), ("SAT", "retroarch", "Sega Saturn"))
        for ext in (".cue", ".chd", ".iso", ".m3u"):
            self.assertIn(ext, exts)
        self.assertNotIn(".bin", exts)

    def test_core_tables(self):
        self.assertEqual(cores.default_core("saturn"), "yabasanshiro")
        self.assertEqual(cores.compatible_cores("saturn", ["mednafen_saturn", "yabasanshiro", "mgba"]),
                         ["yabasanshiro", "mednafen_saturn"])
        self.assertEqual(cores.compatible_cores("saturn", ["mgba"]), [])
        for core in cores.SYSTEM_CORE_COMPATIBILITY["saturn"]:
            self.assertIn(core, menu.CORE_NAMES)

    def test_hidden_until_a_core_is_installed_and_offered_by_the_installer(self):
        systems = [(s[0], s[1], s[4]) for s in menu.ALL_SYSTEMS if s[2] == "retroarch"]
        self.assertIn("saturn", coreinstall.uncovered(systems, cores.SYSTEM_CORE_COMPATIBILITY, ["mgba"]))
        self.assertNotIn("saturn", coreinstall.uncovered(systems, cores.SYSTEM_CORE_COMPATIBILITY, ["yabause"]))
        rows = {r["core"]: r for r in coreinstall.candidates(systems, cores.SYSTEM_CORE_COMPATIBILITY, [], menu.CORE_NAMES)}
        self.assertEqual(rows["yabasanshiro"]["systems"], ["SAT"])

    def test_icon_and_sd_card_folder(self):
        self.assertEqual(menu.system_icon("saturn"), "sys_saturn")
        self.assertIn("saturn", sdcard.SYSTEM_DIRS)

    def test_bios_needed_only_by_beetle_saturn(self):
        self.assertTrue(biosctl.needs_bios("saturn"))
        status = {r["file"]: r["status"] for r in biosctl.check_system("saturn", "mednafen_saturn", ["/nonexistent"])}
        self.assertEqual(status["sega_101.bin"], biosctl.MISSING)
        status = {r["file"]: r["status"] for r in biosctl.check_system("saturn", "yabasanshiro", ["/nonexistent"])}
        self.assertEqual(set(status.values()), {biosctl.OPTIONAL})


if __name__ == "__main__":
    unittest.main()
