import os
import tempfile
import unittest

from tests.helpers import load_menu
from tests.test_launch import load_launch
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


    def test_core_specific_options_and_bios_detection(self):
        launch = load_launch()
        with tempfile.TemporaryDirectory() as root:
            bios = os.path.join(root, "bios")
            run = os.path.join(root, "run")
            os.makedirs(bios)

            # Beetle's regional BIOS files must not disable YabaSanshiro's HLE BIOS.
            open(os.path.join(bios, "sega_101.bin"), "wb").close()
            self.assertFalse(launch.saturn_has_bios(root))
            path = launch.core_options("saturn", root, run, core="yabasanshiro")
            with open(path) as f:
                yaba = f.read()
            self.assertIn('yabasanshiro_force_hle_bios = "enabled"', yaba)
            self.assertIn('yabasanshiro_sh2coretype = "dynarec"', yaba)
            self.assertIn('yabasanshiro_resolution_mode = "original"', yaba)
            self.assertNotIn("polygon_generation_mode", yaba)

            # Beetle must never receive unrelated YabaSanshiro options or a hardware-renderer safe retry.
            path = launch.core_options("saturn", root, run, safe=True, core="mednafen_saturn")
            with open(path) as f:
                beetle = f.read()
            self.assertEqual(beetle, "")
            self.assertEqual(launch.video_attempts("saturn", core="mednafen_saturn"), [None])

            # Yabause has its own option namespace and sensible two-thread default.
            path = launch.core_options("saturn", root, run, core="yabause")
            with open(path) as f:
                yabause = f.read()
            self.assertIn('yabause_frameskip = "enabled"', yabause)
            self.assertIn('yabause_numthreads = "2"', yabause)
            self.assertIn('yabause_force_hle_bios = "enabled"', yabause)

    def test_saturn_user_overrides_are_filtered_by_selected_core(self):
        launch = load_launch()
        with tempfile.TemporaryDirectory() as root:
            config = os.path.join(root, "config")
            os.makedirs(config)
            with open(os.path.join(config, "saturn-options.cfg"), "w") as f:
                f.write('yabasanshiro_resolution_mode = "2x"\n')
                f.write('yabause_numthreads = "4"\n')
                f.write('beetle_saturn_cdimagecache = "enabled"\n')
                f.write('mupen64plus-cpucore = "bad"\n')
            run = os.path.join(root, "run")
            path = launch.core_options("saturn", root, run, core="yabasanshiro")
            with open(path) as f:
                self.assertIn('yabasanshiro_resolution_mode = "2x"', f.read())
            path = launch.core_options("saturn", root, run, core="yabause")
            with open(path) as f:
                data = f.read()
            self.assertIn('yabause_numthreads = "4"', data)
            self.assertNotIn("yabasanshiro_resolution_mode", data)
            path = launch.core_options("saturn", root, run, core="mednafen_saturn")
            with open(path) as f:
                self.assertIn('beetle_saturn_cdimagecache = "enabled"', f.read())

    def test_bios_needed_only_by_beetle_saturn(self):
        self.assertTrue(biosctl.needs_bios("saturn"))
        status = {r["file"]: r["status"] for r in biosctl.check_system("saturn", "mednafen_saturn", ["/nonexistent"])}
        self.assertEqual(status["sega_101.bin"], biosctl.MISSING)
        status = {r["file"]: r["status"] for r in biosctl.check_system("saturn", "yabasanshiro", ["/nonexistent"])}
        self.assertEqual(set(status.values()), {biosctl.OPTIONAL})


if __name__ == "__main__":
    unittest.main()
