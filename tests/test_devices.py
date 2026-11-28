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


def consoles():
    """Every console id /etc/rgos-device can hold: the chipsets that serve one console, plus the H700 consoles."""
    m = re.search(r"^H700_CONSOLES=\(([^)]*)\)", read("build.sh"), re.M)
    return [d for d in build_devices() if not d.startswith("h700-")] + m.group(1).split()


class DeviceWiringTests(unittest.TestCase):
    def test_build_targets_are_chipsets_and_the_h700_covers_the_three_consoles(self):
        self.assertEqual(sorted(build_devices()), ["h700-ddr3", "h700-ddr4", "miniloong", "rg-rotate"])
        self.assertEqual(sorted(consoles()), ["miniloong", "rg-rotate", "rg34xxsp", "rg35xxh", "rg35xxsp"])

    def test_every_console_has_a_menu_canvas(self):
        menu = helpers.load_menu()
        for dev in consoles():
            self.assertIn(dev, menu.CANVAS, dev)

    def test_rg35xxsp_uses_the_640x480_layout_of_the_rg35xxh(self):
        menu = helpers.load_menu()
        self.assertEqual(menu.CANVAS["rg35xxsp"], menu.CANVAS["rg35xxh"])

    def test_every_device_is_in_the_workflow_readme_and_update_docs(self):
        wf, readme, upd = read(".github", "workflows", "build-rgos.yml"), read("docs", "DEVICES.md"), read("rgos", "rgos-update")
        for dev in build_devices():
            self.assertIn("- %s" % dev, wf, dev)
            self.assertIn("`%s`" % dev, readme, dev)
            self.assertIn('"%s"' % dev, upd, dev)
        for dev in consoles():
            self.assertIn("`%s`" % dev, readme, dev)

    def test_build_installs_analog_off_for_the_sp_and_never_falls_back_to_the_stick_config(self):
        b = read("build.sh")
        self.assertIn('if [[ "$CONSOLE" == "rg35xxsp" ]]; then ANALOG=false; else ANALOG=true; fi', b)
        self.assertIn('[[ -f "$RA_CFG" || "$CONSOLE" == "rg35xxsp" ]] || RA_CFG="$HERE/config/retroarch-rg34xxsp.cfg"', b)


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

    def test_no_right_stick_or_stick_click_is_bound(self):
        for k in ("input_player1_l3_btn", "input_player1_r3_btn"):
            self.assertEqual(self.cfg.get(k), "nul", k)
        for axis in ("r_x_plus", "r_x_minus", "r_y_plus", "r_y_minus", "l2", "r2", "r3"):
            self.assertEqual(self.cfg.get("input_player1_%s_axis" % axis), "nul", axis)
        self.assertEqual(self.cfg.get("input_analog_dpad_mode"), "0")

    def test_only_the_left_stick_axes_are_bound_for_dpad_to_joystick(self):
        self.assertEqual([self.cfg.get("input_player1_l_%s_axis" % a) for a in ("x_plus", "x_minus", "y_plus", "y_minus")],
                         ["+0", "-0", "+1", "-1"])

    def test_the_right_stick_config_of_the_other_h700_consoles_is_not_inherited(self):
        self.assertIn("+2", parse_cfg("retroarch-rg34xxsp.cfg").values())
        self.assertNotIn("+2", self.cfg.values())

    def test_hotkeys_only_use_buttons_the_sp_has(self):
        missing = {"6", "7", "11", "12"}
        for k, v in self.cfg.items():
            if k.startswith("input_") and (k.endswith("_btn")) and not k.startswith("input_player1_"):
                self.assertNotIn(v, missing, k)
        combo = {k: v for k, v in self.cfg.items() if k.startswith("input_") and k.endswith("_btn") and not k.startswith("input_player1_")
                 and k != "input_enable_hotkey_btn"}
        self.assertEqual(len(set(combo.values())), len(combo), combo)

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


class ChipsetBuildTests(unittest.TestCase):
    """One H700 image for every console: the console is read from the device tree, the user copies the .dtb to dtb.img."""

    def test_the_h700_image_keeps_device_trees_and_ships_no_dtb_img(self):
        b = read("build.sh")
        self.assertIn('rm -f "$WORK/mnt/dtb.img"', b)
        self.assertNotIn('rm -rf "$WORK/mnt/device_trees"', b)
        self.assertNotIn('cp -f "$DTB_SRC" "$WORK/mnt/dtb.img"', b)
        self.assertIn("device_trees/README.txt", b)

    def test_usage_names_the_chipsets_and_the_dtb_step(self):
        b = read("build.sh")
        self.assertIn("H700_DDR4", b)
        self.assertIn("H700_DDR3", b)
        self.assertIn("rename it to dtb.img", b)

    def test_old_per_console_build_names_are_refused_with_a_hint(self):
        import subprocess
        for old in ("rg34xxsp", "rg35xxh", "rg35xxsp"):
            r = subprocess.run(["bash", os.path.join(helpers.ROOT, "build.sh"), old], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, old)
            self.assertIn("H700_DDR4", r.stderr, old)

    def test_chipset_names_are_accepted_in_any_case(self):
        import subprocess
        b = read("build.sh")
        self.assertIn("h700-ddr3|h700ddr3)", b)
        self.assertIn("h700-ddr4|h700ddr4)", b)
        self.assertIn("t618", b)
        self.assertIn("rk3566", b)

    def test_every_console_gets_its_own_input_retroarch_and_splash_files(self):
        b = read("build.sh")
        self.assertIn('for CONSOLE in "${H700_CONSOLES[@]}"; do', b)
        self.assertIn('"$ROOTFS/etc/rgos/input-$CONSOLE.json"', b)
        self.assertIn('"$ROOTFS/etc/rgos/retroarch-$CONSOLE.cfg"', b)
        self.assertIn('splash-$CONSOLE.', b)

    def test_device_file_is_a_run_link_on_the_h700_and_the_chipset_is_baked(self):
        b = read("build.sh")
        self.assertIn('ln -sfn /run/rgos-device "$ROOTFS/etc/rgos-device"', b)
        self.assertIn('echo "$DEVICE" > "$ROOTFS/etc/rgos-chipset"', b)
        self.assertIn('/opt/rgos/rgos-detect-device', b)
        self.assertIn('"$(cat "$ROOTFS/etc/rgos-chipset")"', b)


class DetectDeviceTests(unittest.TestCase):
    SCRIPT = os.path.join(helpers.ROOT, "rgos", "rgos-detect-device")

    def run_detect(self, compatible, model="", force=None):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "compatible"), "wb") as f:
                f.write(b"\0".join(c.encode() for c in compatible) + b"\0")
            with open(os.path.join(d, "model"), "wb") as f:
                f.write(model.encode() + b"\0")
            force_file = os.path.join(d, "force")
            if force is not None:
                with open(force_file, "w") as f:
                    f.write(force)
            env = dict(os.environ, RGOS_DT_DIR=d, RGOS_FORCE_FILE=force_file)
            r = subprocess.run(["sh", self.SCRIPT], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.strip()

    def test_the_three_h700_consoles_are_told_apart(self):
        self.assertEqual(self.run_detect(["anbernic,rg34xx-sp", "allwinner,sun50i-h700"]), "rg34xxsp")
        self.assertEqual(self.run_detect(["anbernic,rg35xx-h", "allwinner,sun50i-h700"]), "rg35xxh")
        self.assertEqual(self.run_detect(["anbernic,rg35xx-sp", "allwinner,sun50i-h700"]), "rg35xxsp")

    def test_the_model_string_is_a_fallback(self):
        self.assertEqual(self.run_detect(["allwinner,sun50i-h700"], model="Anbernic RG35XX SP"), "rg35xxsp")

    def test_an_unknown_tree_gets_the_default_console(self):
        self.assertEqual(self.run_detect(["anbernic,rg40xx-h", "allwinner,sun50i-h700"]), "rg35xxh")

    def test_a_force_file_wins_and_a_bad_one_is_ignored(self):
        self.assertEqual(self.run_detect(["anbernic,rg35xx-h"], force="rg34xxsp\n"), "rg34xxsp")
        self.assertEqual(self.run_detect(["anbernic,rg35xx-sp"], force="toaster"), "rg35xxsp")

    def test_script_is_valid_shell_with_lf_line_endings(self):
        import subprocess
        self.assertEqual(subprocess.run(["sh", "-n", self.SCRIPT]).returncode, 0)
        with open(self.SCRIPT, "rb") as f:
            self.assertNotIn(b"\r", f.read())


class EveryChipsetUsesDtbImgTests(unittest.TestCase):
    def test_extlinux_is_pointed_at_dtb_img_for_every_chipset_and_no_dtb_is_shipped(self):
        b = read("build.sh")
        self.assertIn('FDT /dtb.img', b)
        self.assertIn('rm -f "$WORK/mnt/dtb.img"', b)
        self.assertNotIn("MINILOONG_DTB_REL", b)
        self.assertNotIn("UPDATE_DTB", b)
        self.assertIn("dtb-README.txt", b)

    def test_usage_names_the_t618_and_rk3566_chipsets(self):
        b = read("build.sh")
        self.assertIn("T618        Anbernic RG Rotate", b)
        self.assertIn("RK3566      MiniLoong Pocket 1", b)
