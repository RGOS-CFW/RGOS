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


class N64Tests(unittest.TestCase):
    def row(self):
        return next(sy for sy in menu.ALL_SYSTEMS if sy[0] == "n64")

    def test_system_row(self):
        sid, tag, kind, exts, name = self.row()
        self.assertEqual((tag, kind, name), ("N64", "retroarch", "Nintendo 64"))
        for ext in (".z64", ".n64", ".v64"):
            self.assertIn(ext, exts)

    def test_core_tables(self):
        self.assertEqual(cores.default_core("n64"), "mupen64plus_next")
        self.assertEqual(cores.compatible_cores("n64", ["mupen64plus_next", "mgba"]), ["mupen64plus_next"])
        self.assertEqual(cores.compatible_cores("n64", ["parallel_n64", "mupen64plus_next"]), ["mupen64plus_next", "parallel_n64"])
        self.assertEqual(cores.compatible_cores("n64", ["mgba"]), [])
        self.assertEqual(menu.CORE_NAMES["mupen64plus_next"], "Mupen64Plus-Next")

    def test_hidden_until_a_core_is_installed_and_offered_by_the_installer(self):
        systems = [(s[0], s[1], s[4]) for s in menu.ALL_SYSTEMS if s[2] == "retroarch"]
        self.assertIn("n64", coreinstall.uncovered(systems, cores.SYSTEM_CORE_COMPATIBILITY, ["mgba"]))
        self.assertNotIn("n64", coreinstall.uncovered(systems, cores.SYSTEM_CORE_COMPATIBILITY, ["parallel_n64"]))
        rows = {r["core"]: r for r in coreinstall.candidates(systems, cores.SYSTEM_CORE_COMPATIBILITY, [], menu.CORE_NAMES)}
        self.assertEqual(rows["mupen64plus_next"]["systems"], ["N64"])

    def test_icon_and_sd_card_folder(self):
        self.assertEqual(menu.system_icon("n64"), "sys_n64")
        self.assertIn("n64", load("sdcard").SYSTEM_DIRS)

    def test_launch_uses_the_gles_driver_and_a_boot_file_override(self):
        launch = load_launch()
        self.assertEqual(launch.video_attempts("n64", "/nonexistent"), ["gl"])
        d = tempfile.mkdtemp(prefix="rgos-boot-")
        with open(os.path.join(d, "retroarch-n64-video.txt"), "w") as f:
            f.write("vulkan\n")
        self.assertEqual(launch.video_attempts("n64", d), ["vulkan"])
        self.assertIn("n64", launch.HEAVY_SYSTEMS)

    def test_n64_core_options_use_supported_render_resolutions_and_safe_retry(self):
        launch = load_launch()
        d = tempfile.mkdtemp(prefix="rgos-n64-options-")
        path = launch.core_options("n64", d, d)
        with open(path) as f:
            defaults = f.read()
        self.assertIn('mupen64plus-43screensize = "320x240"', defaults)
        self.assertIn('mupen64plus-169screensize = "640x360"', defaults)
        self.assertNotIn('mupen64plus-169screensize = "320x180"', defaults)
        safe_path = launch.core_options("n64", d, d, safe=True)
        with open(safe_path) as f:
            safe = f.read()
        self.assertIn('mupen64plus-cpucore = "cached_interpreter"', safe)
        self.assertIn('mupen64plus-EnableFBEmulation = "False"', safe)

    def test_scan_lists_roms_in_any_byte_order(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "roms", "n64"))
        for n in ("a.z64", "b.n64", "c.v64", "notes.txt"):
            open(os.path.join(root, "roms", "n64", n), "wb").write(b"x")
        with mock.patch.object(menu, "rom_roots", lambda: [(1, root)]), \
                mock.patch.object(menu, "SYSTEMS", list(menu.ALL_SYSTEMS)):
            games = menu.scan_roms()
        self.assertEqual(sorted(g["path"].rsplit("/", 1)[1] for g in games), ["a.z64", "b.n64", "c.v64"])
        self.assertTrue(all(g["sid"] == "n64" and g["tag"] == "N64" for g in games))


if __name__ == "__main__":
    unittest.main()
