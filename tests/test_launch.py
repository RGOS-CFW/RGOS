import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

from tests import helpers


def load_launch():
    loader = importlib.machinery.SourceFileLoader("rgos_launch", os.path.join(helpers.RGOS, "rgos-launch"))
    spec = importlib.util.spec_from_loader("rgos_launch", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class PickCoreTests(unittest.TestCase):
    def setUp(self):
        self.launch = load_launch()
        p = mock.patch.object(self.launch, "core_file", lambda c: "/cores/%s.so" % c if isinstance(c, str) and c else "")
        p.start()
        self.addCleanup(p.stop)

    def pick(self, state):
        return self.launch.pick_core("snes", state, lambda sid: "snes9x", lambda sid, cores=None: ["bsnes"])

    def test_users_choice_wins(self):
        self.assertEqual(self.pick({"emulators": {"snes": "bsnes"}}), "bsnes")

    def test_no_choice_uses_the_system_default(self):
        self.assertEqual(self.pick({}), "snes9x")
        self.assertEqual(self.pick({"emulators": {}}), "snes9x")

    def test_state_that_is_not_the_expected_shape_falls_back_to_the_default(self):
        for bad in ([], None, "x", 5, {"emulators": []}, {"emulators": "a"}, {"emulators": {"snes": ["bsnes"]}},
                    {"emulators": {"snes": 7}}):
            self.assertEqual(self.pick(bad), "snes9x", bad)


class NativePortTests(unittest.TestCase):
    def setUp(self):
        self.launch = load_launch()
        self.tmp = tempfile.mkdtemp(prefix="rgos-native-")
        self.script = os.path.join(self.tmp, "game.sh")
        with open(self.script, "w") as f:
            f.write("#!/bin/sh\necho native\n")
        self.launch.NATIVE_LOG = os.path.join(self.tmp, "native.log")
        self.launch.RUN_DIR = os.path.join(self.tmp, "run")
        self.launch.GAME_FLAG = os.path.join(self.launch.RUN_DIR, "ingame")

    def test_shell_port_runs_directly_without_selecting_a_core(self):
        seen = {}
        def fake_call(cmd, **kw):
            seen.update(cmd=cmd, cwd=kw["cwd"])
            return 0
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}), \
             mock.patch.object(self.launch.subprocess, "call", side_effect=fake_call), \
             mock.patch.object(self.launch, "set_game_flag"), \
             mock.patch.object(self.launch, "set_governor", return_value={}), \
             mock.patch.object(self.launch, "restore_governor"):
            rc = self.launch.launch_native(self.script)
        self.assertEqual(rc, 0)
        self.assertEqual(seen["cmd"], [self.launch.shutil.which("sh"), self.script])
        self.assertEqual(seen["cwd"], self.tmp)

    def test_menu_sdl_dummy_driver_does_not_leak_into_ports(self):
        base = {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy", "RGOS_VIDEO": "fb", "RGOS_NO_HW": "1", "PATH": "/bin"}
        env = self.launch.native_env(base)
        self.assertNotIn("SDL_VIDEODRIVER", env)
        self.assertNotIn("RGOS_VIDEO", env)
        self.assertEqual(env["SDL_AUDIODRIVER"], "alsa")
        self.assertEqual(env["HOME"], "/root")

    def test_an_explicit_real_video_driver_is_kept(self):
        env = self.launch.native_env({"SDL_VIDEODRIVER": "kmsdrm", "RGOS_NO_HW": "1"})
        self.assertEqual(env["SDL_VIDEODRIVER"], "kmsdrm")

    def test_crlf_script_is_converted_before_running(self):
        with open(self.script, "wb") as f:
            f.write(b"#!/bin/sh\r\necho native\r\n")
        seen = {}
        def fake_call(cmd, **kw):
            seen["cmd"] = cmd
            return 0
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}), \
             mock.patch.object(self.launch.subprocess, "call", side_effect=fake_call):
            self.launch.launch_native(self.script)
        with open(seen["cmd"][1], "rb") as f:
            self.assertNotIn(b"\r", f.read())

    def test_self_extracting_installer_is_not_rewritten(self):
        payload = b"#!/bin/bash\r\n# Makeself\r\nexit 0\r\n" + bytes(range(256)) + b"\r\n\x00\x1f\x8b\r\n"
        with open(self.script, "wb") as f:
            f.write(payload)
        self.assertEqual(self.launch.fix_crlf(self.script), self.script)
        with open(self.script, "rb") as f:
            self.assertEqual(f.read(), payload)

    def test_portmaster_is_found_in_the_roms_ports_folder(self):
        ports = os.path.join(self.tmp, "roms", "ports")
        os.makedirs(ports)
        pm = os.path.join(ports, "PortMaster.sh")
        open(pm, "w").close()
        self.launch.ROMS_ROOT = self.tmp
        self.assertEqual(self.launch.portmaster_script(), pm)

    def test_port_paths_are_classified_as_native(self):
        self.assertEqual(self.launch.system_of("/media/roms/roms/ports/example.sh"), "ports")


class DolphinSysTests(unittest.TestCase):
    def setUp(self):
        self.launch = load_launch()
        self.tmp = tempfile.mkdtemp(prefix="rgos-gc-")
        self.src = os.path.join(self.tmp, "src", "Sys")
        os.makedirs(os.path.join(self.src, "GC"))
        for rel in ("codehandler.bin", os.path.join("GC", "dsp_rom.bin")):
            with open(os.path.join(self.src, rel), "w") as f:
                f.write("x")
        rel = os.path.join(self.tmp, "release")
        with open(rel, "w") as f:
            f.write("BUILD_ID=1\n")
        self.launch.RELEASE_FILE = rel
        self.roms = os.path.join(self.tmp, "roms")
        self.dst = os.path.join(self.roms, "bios", "dolphin-emu", "Sys")

    def test_copies_everything_and_writes_the_stamp_last(self):
        ok, why = self.launch.ensure_dolphin_sys(self.roms, self.src)
        self.assertTrue(ok, why)
        self.assertTrue(os.path.isfile(os.path.join(self.dst, "GC", "dsp_rom.bin")))
        self.assertTrue(os.path.isfile(os.path.join(self.dst, self.launch.SYS_MARK)))

    def test_a_half_copied_folder_without_the_stamp_is_completed(self):
        os.makedirs(self.dst)
        ok, _ = self.launch.ensure_dolphin_sys(self.roms, self.src)
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(os.path.join(self.dst, "codehandler.bin")))

    def test_user_files_survive_a_refresh_for_a_new_build(self):
        self.launch.ensure_dolphin_sys(self.roms, self.src)
        ipl = os.path.join(self.dst, "GC", "USA")
        os.makedirs(ipl)
        with open(os.path.join(ipl, "IPL.bin"), "w") as f:
            f.write("bios")
        with open(self.launch.RELEASE_FILE, "w") as f:
            f.write("BUILD_ID=2\n")
        self.launch.ensure_dolphin_sys(self.roms, self.src)
        self.assertTrue(os.path.isfile(os.path.join(ipl, "IPL.bin")))

    def test_a_good_stamp_means_no_copying(self):
        self.launch.ensure_dolphin_sys(self.roms, self.src)
        with mock.patch.object(self.launch, "copy_tree", side_effect=AssertionError("copied again")):
            self.assertTrue(self.launch.ensure_dolphin_sys(self.roms, self.src)[0])

    def test_missing_source_reports_failure_without_a_destination(self):
        ok, why = self.launch.ensure_dolphin_sys(self.roms, os.path.join(self.tmp, "nope"))
        self.assertFalse(ok)
        self.assertIn("no Dolphin Sys", why)


class GameCubeLaunchTests(unittest.TestCase):
    def setUp(self):
        self.launch = load_launch()

    def test_gc_tries_glcore_then_gl_and_other_systems_are_left_alone(self):
        self.assertEqual(self.launch.video_attempts("gc", "/nonexistent"), ["glcore", "gl"])
        self.assertEqual(self.launch.video_attempts("gba", "/nonexistent"), [None])

    def test_boot_file_forces_one_video_driver(self):
        d = tempfile.mkdtemp(prefix="rgos-boot-")
        with open(os.path.join(d, "retroarch-gc-video.txt"), "w") as f:
            f.write("vulkan\n")
        self.assertEqual(self.launch.video_attempts("gc", d), ["vulkan"])

    def test_run_config_pins_the_video_driver_only_when_asked(self):
        self.assertIn('video_driver = "glcore"', self.launch.run_config("gc", "/r", "default", video_driver="glcore"))
        self.assertNotIn("video_driver", self.launch.run_config("gba", "/r", "default"))

    def test_signal_deaths_are_named(self):
        self.assertEqual(self.launch.rc_text(-11), "killed by SIGSEGV")
        self.assertEqual(self.launch.rc_text(1), "code 1")

    def test_missing_libs_lists_only_the_not_found_ones(self):
        out = "\tlinux-vdso.so.1 (0x1)\n\tliblzo2.so.2 => not found\n\tlibc.so.6 => /lib/libc.so.6 (0x2)\n"
        fake = mock.Mock(stdout=out)
        with mock.patch.object(self.launch.shutil, "which", return_value="/usr/bin/ldd"), \
             mock.patch.object(self.launch.subprocess, "run", return_value=fake):
            self.assertEqual(self.launch.missing_libs("/x/dolphin_libretro.so"), ["liblzo2.so.2"])

    def test_a_dying_first_attempt_is_retried_with_the_next_driver(self):
        L = self.launch
        d = tempfile.mkdtemp(prefix="rgos-run-")
        seen = []
        codes = iter([-11, 0])

        def fake_call(cmd, **kw):
            seen.append(open(os.path.join(d, "retroarch-run.cfg")).read())
            return next(codes)

        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}), \
             mock.patch.object(L, "RUN_DIR", d), mock.patch.object(L, "ROMS_ROOT", d), mock.patch.object(L, "BOOT_DIR", d), \
             mock.patch.object(L, "LOG", os.path.join(d, "ra.log")), mock.patch.object(L, "TTY", os.path.join(d, "tty")), \
             mock.patch.object(L, "SYS_INPUT", d), mock.patch.object(L.subprocess, "call", side_effect=fake_call):
            rc = L.launch_retroarch("gc", "dolphin", "/cores/dolphin_libretro.so", "/roms/gc/g.iso")
        self.assertEqual(rc, 0)
        self.assertEqual(len(seen), 2)
        self.assertIn('video_driver = "glcore"', seen[0])
        self.assertIn('video_driver = "gl"', seen[1])
        report = open(os.path.join(d, "rgos-retroarch.txt")).read()
        self.assertIn("earlier attempt 1", report)
        self.assertIn("SIGSEGV", report)


if __name__ == "__main__":
    unittest.main()
