import importlib
import json
import os
import re
import subprocess
import sys
import unittest
from unittest import mock

from tests import helpers
from tests.test_launch import load_launch


def read(*parts):
    with open(os.path.join(helpers.ROOT, *parts)) as f:
        return f.read()


class SteamDeckWiringTests(unittest.TestCase):
    def test_menu_has_the_deck_canvas_and_allows_gamecube(self):
        menu = helpers.load_menu()
        self.assertEqual(menu.CANVAS["steamdeck"], (720, 480))
        with mock.patch.dict(os.environ, {"RGOS_DEVICE": "steamdeck"}):
            self.assertTrue(menu._gc_allowed())
        for dev in ("rg34xxsp", "rg35xxh", "rg35xxsp", "miniloong"):
            with mock.patch.dict(os.environ, {"RGOS_DEVICE": dev}):
                self.assertFalse(menu._gc_allowed(), dev)

    def test_installer_and_update_know_the_device(self):
        self.assertIn('"steamdeck"', read("rgos", "rgos-update"))
        self.assertIn('"steamdeck": "Steam Deck"', read("rgos", "installer.py"))

    def test_build_sh_hands_the_deck_to_its_own_builder(self):
        b = read("build.sh")
        self.assertIn("steamdeck", re.search(r"^ALL_DEVICES=\(([^)]*)\)", b, re.M).group(1).split())
        self.assertIn('exec bash "$HERE/build-steamdeck.sh"', b)

    def test_scripts_parse(self):
        for f in ("build.sh", "build-steamdeck.sh"):
            subprocess.run(["bash", "-n", os.path.join(helpers.ROOT, f)], check=True)
        for f in ("rgos-session", "rgos-deck-roms", "rgos-deck-audio"):
            subprocess.run(["sh", "-n", os.path.join(helpers.RGOS, f)], check=True)

    def test_services_and_configs_exist(self):
        for f in ("rgos.service", "rgos-deck-firstboot.service", "rgos-deck-audio.service"):
            self.assertIn("[Service]", read("systemd", f))
        self.assertIn("/opt/rgos/rgos-session", read("systemd", "rgos.service"))
        conf = json.loads(read("config", "input-steamdeck.json"))
        self.assertTrue(conf["analog"])
        self.assertEqual(conf["sticks"], 2)
        self.assertIn('video_fullscreen_x = "1280"', read("config", "retroarch-steamdeck.cfg"))

    def test_the_build_ships_every_core_the_menu_can_use(self):
        import cores
        sys.path.insert(0, helpers.RGOS)
        script = read("build-steamdeck.sh")
        listed = set(re.search(r"CORES=\(([^)]*)\)", script).group(1).split())
        wanted = {c for names in cores.SYSTEM_CORE_COMPATIBILITY.values() for c in names}
        wanted.discard("flycast_standalone")
        wanted.discard("mesen_s")          # fetched separately: the buildbot calls it mesen-s
        wanted.discard("dolphin")          # added when GC_REPO is not none
        self.assertEqual(sorted(wanted - listed), [])
        self.assertIn("fetch_core mesen-s mesen_s", script)
        self.assertIn("CORES+=(dolphin)", script)


class X86CoreInstallerTests(unittest.TestCase):
    def load(self, arch):
        sys.path.insert(0, helpers.RGOS)
        with mock.patch.dict(os.environ, {"RGOS_ARCH": arch}):
            import coreinstall
            return importlib.reload(coreinstall)

    def tearDown(self):
        self.load("aarch64")

    def test_x86_uses_the_x86_64_buildbot_and_offers_dolphin_and_flycast(self):
        ci = self.load("x86_64")
        self.assertTrue(ci.DEFAULT_URL.endswith("/linux/x86_64/latest"))
        self.assertNotIn("dolphin", ci.EXCLUDE)
        self.assertNotIn("flycast", ci.DESKTOP_GL_ONLY)

    def test_handhelds_keep_the_old_rules(self):
        ci = self.load("aarch64")
        self.assertTrue(ci.DEFAULT_URL.endswith("/linux/aarch64/latest"))
        self.assertIn("dolphin", ci.EXCLUDE)
        self.assertIn("flycast", ci.DESKTOP_GL_ONLY)


class RotationTests(unittest.TestCase):
    def test_portrait_panel_rotates_retroarch(self):
        launch = load_launch()
        for rot, want in (("90", '"3"'), ("270", '"1"')):
            with mock.patch.dict(os.environ, {"RGOS_FB_ROTATE": rot}):
                self.assertIn("video_rotation = %s" % want, launch.run_config("snes", "/r", "default"))
        for rot in ("", "0", "180"):
            with mock.patch.dict(os.environ, {"RGOS_FB_ROTATE": rot}):
                self.assertNotIn("video_rotation", launch.run_config("snes", "/r", "default"))


if __name__ == "__main__":
    unittest.main()
