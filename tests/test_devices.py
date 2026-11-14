"""Every device build.sh can build is wired in everywhere: menu canvas, CI workflow, README, update-tar manifest docs."""
import os
import re
import unittest

from tests import helpers


def read(*parts):
    with open(os.path.join(helpers.ROOT, *parts), newline="") as f:
        return f.read()


def build_devices():
    m = re.search(r"^ALL_DEVICES=\(([^)]*)\)", read("build.sh"), re.M)
    return m.group(1).split()


class DeviceWiringTests(unittest.TestCase):
    def test_build_lists_the_rg35xxsp(self):
        self.assertIn("rg35xxsp", build_devices())

    def test_every_device_has_a_menu_canvas(self):
        menu = helpers.load_menu()
        for dev in build_devices():
            self.assertIn(dev, menu.CANVAS, dev)

    def test_rg35xxsp_uses_the_640x480_layout_of_the_rg35xxh(self):
        menu = helpers.load_menu()
        self.assertEqual(menu.CANVAS["rg35xxsp"], menu.CANVAS["rg35xxh"])

    def test_every_device_is_in_the_workflow_readme_and_update_docs(self):
        wf, readme, upd = read(".github", "workflows", "build-rgos.yml"), read("README.md"), read("rgos", "rgos-update")
        for dev in build_devices():
            self.assertIn("- %s" % dev, wf, dev)
            self.assertIn("`%s`" % dev, readme, dev)
            self.assertIn('"%s"' % dev, upd, dev)

    def test_build_installs_analog_off_for_the_sp_and_never_falls_back_to_the_stick_config(self):
        b = read("build.sh")
        self.assertIn('if [[ "$DEVICE" == "rg35xxsp" ]]; then ANALOG=false; else ANALOG=true; fi', b)
        # the fallback to the RG34XXSP's (stick) config must exclude the SP
        self.assertIn('[[ -f "$RA_CFG" || "$DEVICE" == "rg35xxsp" ]] || RA_CFG="$HERE/config/retroarch-rg34xxsp.cfg"', b)


def parse_cfg(name):
    out = {}
    for line in read("config", name).splitlines():
        m = re.match(r'\s*([a-z0-9_]+)\s*=\s*"([^"]*)"', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


class Rg35xxspRetroArchConfigTests(unittest.TestCase):
    def setUp(self):
        self.cfg = parse_cfg("retroarch-rg35xxsp.cfg")

    def test_it_has_its_own_file(self):
        self.assertTrue(os.path.isfile(os.path.join(helpers.ROOT, "config", "retroarch-rg35xxsp.cfg")))

    def test_no_stick_axis_or_stick_click_is_bound(self):
        for k, v in self.cfg.items():
            if k.endswith("_axis") or k in ("input_player1_l3_btn", "input_player1_r3_btn"):
                self.assertEqual(v, "nul", k)
        for axis in ("l_x_plus", "l_x_minus", "l_y_plus", "l_y_minus", "r_x_plus", "r_x_minus", "r_y_plus", "r_y_minus"):
            self.assertEqual(self.cfg.get("input_player1_%s_axis" % axis), "nul", axis)
        self.assertEqual(self.cfg.get("input_analog_dpad_mode"), "0")

    def test_the_stick_config_of_the_other_h700_consoles_is_not_inherited(self):
        self.assertIn("+0", parse_cfg("retroarch-rg34xxsp.cfg").values())       # they do have sticks; the SP file must not look like them
        self.assertNotIn("+0", self.cfg.values())

    def test_hotkeys_only_use_buttons_the_sp_has(self):
        missing = {"6", "7", "11", "12"}                                         # L2 R2 L3 R3
        for k, v in self.cfg.items():
            if k.startswith("input_") and (k.endswith("_btn")) and not k.startswith("input_player1_"):
                self.assertNotIn(v, missing, k)
        combo = {k: v for k, v in self.cfg.items() if k.startswith("input_") and k.endswith("_btn") and not k.startswith("input_player1_")
                 and k != "input_enable_hotkey_btn"}
        self.assertEqual(len(set(combo.values())), len(combo), combo)             # no two hotkeys on the same button

    def test_native_640x480_video(self):
        self.assertEqual((self.cfg["video_fullscreen_x"], self.cfg["video_fullscreen_y"]), ("640", "480"))


class DeviceCfgPickupTests(unittest.TestCase):
    def test_rgos_launch_appends_the_sp_config_for_the_sp(self):
        import importlib.machinery, importlib.util
        from unittest import mock
        loader = importlib.machinery.SourceFileLoader("rgos_launch_dev", os.path.join(helpers.RGOS, "rgos-launch"))
        spec = importlib.util.spec_from_loader("rgos_launch_dev", loader)
        launch = importlib.util.module_from_spec(spec)
        loader.exec_module(launch)
        d = helpers.sandbox()
        for n in ("retroarch.cfg", "retroarch-rg35xxsp.cfg", "retroarch-rg34xxsp.cfg"):
            open(os.path.join(d, n), "w").close()
        devfile = os.path.join(d, "rgos-device")
        with open(devfile, "w") as f:
            f.write("rg35xxsp\n")
        with mock.patch.dict(os.environ, {"RGOS_DEVICE_FILE": devfile}), mock.patch.object(launch, "RA_CFG", os.path.join(d, "retroarch.cfg")):
            self.assertEqual(launch.device_cfg(), os.path.join(d, "retroarch-rg35xxsp.cfg"))


if __name__ == "__main__":
    unittest.main()
