import json
import os
import shutil
import sys
import tempfile
import unittest

from tests import helpers

sys.path.insert(0, helpers.RGOS)
import portpad  
from tests.test_launch import load_launch


def parse(line):
    parts = line.split(",")
    return parts[0], parts[1], dict(p.split(":", 1) for p in parts[2:])


class MappingTests(unittest.TestCase):
    def test_guid_encodes_the_virtual_pad_identity(self):
        self.assertEqual(portpad.sdl_guid(), "190000004b480000df14000000010000")
        self.assertEqual(len(portpad.sdl_guid()), 32)

    def test_buttons_match_the_retroarch_autoconfig_indices(self):
        _, name, m = parse(portpad.mapping_line())
        self.assertEqual(name, "RG OS Gamepad")
        self.assertEqual((m["a"], m["b"], m["y"], m["x"]), ("b0", "b1", "b2", "b3"))
        self.assertEqual((m["leftshoulder"], m["rightshoulder"], m["lefttrigger"], m["righttrigger"]), ("b4", "b5", "b6", "b7"))
        self.assertEqual((m["back"], m["start"], m["guide"], m["leftstick"], m["rightstick"]), ("b8", "b9", "b10", "b11", "b12"))
        self.assertEqual((m["dpup"], m["dpdown"], m["dpleft"], m["dpright"]), ("b13", "b14", "b15", "b16"))
        self.assertEqual(m["platform"], "Linux")

    def test_sticks_only_when_analog_is_enabled(self):
        self.assertNotIn("leftx", parse(portpad.mapping_line(False))[2])
        m = parse(portpad.mapping_line(True))[2]
        self.assertEqual((m["leftx"], m["lefty"], m["rightx"], m["righty"]), ("a0", "a1", "a2", "a3"))

    def test_autoconfig_cfg_and_mapping_agree(self):
        cfg = {}
        with open(os.path.join(helpers.ROOT, "config", "autoconfig", "RG_OS_Gamepad.cfg")) as f:
            for line in f:
                if "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip().strip('"')
        m = parse(portpad.mapping_line())[2]
        self.assertEqual(cfg["input_b_btn"], m["a"][1:])
        self.assertEqual(cfg["input_a_btn"], m["b"][1:])
        self.assertEqual(cfg["input_select_btn"], m["back"][1:])
        self.assertEqual(cfg["input_start_btn"], m["start"][1:])
        self.assertEqual(cfg["input_up_btn"], m["dpup"][1:])
        self.assertEqual(cfg["input_right_btn"], m["dpright"][1:])


class EnvTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rgos-portpad-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.run_dir = os.path.join(self.dir, "run")
        self.roms = os.path.join(self.dir, "roms")
        os.makedirs(os.path.join(self.roms, "ports"))
        self.conf = os.path.join(self.dir, "input.json")

    def env(self, base=None, port_dir=None):
        return portpad.env_for(base or {}, self.run_dir, self.roms, port_dir, self.conf)

    def test_sets_config_and_writes_the_db_file(self):
        env = self.env()
        self.assertIn(portpad.sdl_guid(), env["SDL_GAMECONTROLLERCONFIG"])
        with open(env["SDL_GAMECONTROLLERCONFIG_FILE"]) as f:
            self.assertIn(portpad.sdl_guid(), f.read())

    def test_analog_flag_is_read_from_input_json(self):
        self.assertNotIn("leftx", self.env()["SDL_GAMECONTROLLERCONFIG"])
        with open(self.conf, "w") as f:
            json.dump({"analog": True}, f)
        self.assertIn("leftx:a0", self.env()["SDL_GAMECONTROLLERCONFIG"])

    def test_bad_input_json_means_no_sticks(self):
        with open(self.conf, "w") as f:
            f.write("{nope")
        self.assertFalse(portpad.analog_enabled(self.conf))

    def test_user_lines_are_appended_and_crlf_comments_are_skipped(self):
        with open(os.path.join(self.roms, "ports", portpad.USER_DB_NAME), "wb") as f:
            f.write(b"# mine\r\n\r\nabc,Custom,a:b1,b:b0\r\nnot a mapping\r\n")
        cfg = self.env()["SDL_GAMECONTROLLERCONFIG"].splitlines()
        self.assertEqual(cfg[-1], "abc,Custom,a:b1,b:b0")
        self.assertNotIn("# mine", cfg)
        self.assertNotIn("not a mapping", cfg)

    def test_per_port_file_wins_over_the_global_one(self):
        port = os.path.join(self.dir, "myport")
        os.makedirs(port)
        for d, v in ((os.path.join(self.roms, "ports"), "g"), (port, "p")):
            with open(os.path.join(d, portpad.USER_DB_NAME), "w") as f:
                f.write("guid,%s,a:b0\n" % v)
        cfg = self.env(port_dir=port)["SDL_GAMECONTROLLERCONFIG"].splitlines()
        self.assertEqual(cfg[-2:], ["guid,g,a:b0", "guid,p,a:b0"])

    def test_an_existing_user_export_is_kept_and_comes_last(self):
        cfg = self.env({"SDL_GAMECONTROLLERCONFIG": "mine,Pad,a:b9"})["SDL_GAMECONTROLLERCONFIG"].splitlines()
        self.assertEqual(cfg[-1], "mine,Pad,a:b9")

    def test_unwritable_run_dir_still_gives_the_env_variable(self):
        blocker = os.path.join(self.dir, "file")
        open(blocker, "w").close()
        env = portpad.env_for({}, os.path.join(blocker, "sub"), self.roms, None, self.conf)
        self.assertIn("SDL_GAMECONTROLLERCONFIG", env)
        self.assertNotIn("SDL_GAMECONTROLLERCONFIG_FILE", env)


class LauncherTests(unittest.TestCase):
    def test_native_env_exports_the_mapping(self):
        launch = load_launch()
        env = launch.native_env({"RGOS_NO_HW": "1", "RGOS_RUN": tempfile.mkdtemp(prefix="rgos-run-")})
        self.assertIn(portpad.sdl_guid(), env["SDL_GAMECONTROLLERCONFIG"])


if __name__ == "__main__":
    unittest.main()
