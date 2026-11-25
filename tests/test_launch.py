import importlib.machinery
import importlib.util
import os
import subprocess
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
            return 0, False
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}), \
             mock.patch.object(self.launch, "call_native", side_effect=fake_call), \
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
            return 0, False
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}), \
             mock.patch.object(self.launch, "call_native", side_effect=fake_call):
            self.launch.launch_native(self.script)
        with open(seen["cmd"][1], "rb") as f:
            self.assertNotIn(b"\r", f.read())

    def test_system_is_not_confused_by_a_roms_folder_inside_a_system(self):
        for path, sid in (("/media/roms/roms/arcade/roms/neogeo/kof.zip", "arcade"),
                          ("/media/roms/roms/snes/Hacks/roms/Zelda/x.sfc", "snes"),
                          ("/media/roms/roms/snes/a.sfc", "snes"),
                          ("/media/roms2/roms/psx/game/disc.cue", "psx"),
                          ("/roms/gba/x.gba", "gba"),
                          ("/media/roms/roms/ports/example.sh", "ports"),
                          ("/tmp/game.gba", "")):
            self.assertEqual(self.launch.system_of(path), sid, path)

    def test_tail_returns_the_last_lines_of_a_huge_log(self):
        with open(self.launch.NATIVE_LOG, "w") as f:
            for i in range(60000):
                f.write("line %d\n" % i)
        self.assertEqual(self.launch.tail(self.launch.NATIVE_LOG, 2), "line 59998\nline 59999\n")
        self.assertEqual(self.launch.tail(os.path.join(self.tmp, "missing"), 3), "")

    def test_tail_of_a_short_file_returns_it_whole(self):
        with open(self.launch.NATIVE_LOG, "w") as f:
            f.write("a\nb\nc\n")
        self.assertEqual(self.launch.tail(self.launch.NATIVE_LOG, 10), "a\nb\nc\n")

    def test_oversized_native_log_is_trimmed_to_its_recent_end(self):
        with open(self.launch.NATIVE_LOG, "w") as f:
            for i in range(200000):
                f.write("old output %d\n" % i)
        self.launch.trim_log(self.launch.NATIVE_LOG)
        size = os.path.getsize(self.launch.NATIVE_LOG)
        self.assertLess(size, self.launch.NATIVE_LOG_KEEP + 100)
        with open(self.launch.NATIVE_LOG) as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "[older output trimmed]")
        self.assertEqual(lines[-1], "old output 199999")
        self.assertTrue(lines[1].startswith("old output "))  # cut on a line boundary

    def test_small_native_log_is_left_alone(self):
        with open(self.launch.NATIVE_LOG, "w") as f:
            f.write("keep me\n")
        self.launch.trim_log(self.launch.NATIVE_LOG)
        with open(self.launch.NATIVE_LOG) as f:
            self.assertEqual(f.read(), "keep me\n")

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

    def test_dreamcast_gets_a_gl_driver_then_retries_and_logs_verbosely(self):
        self.assertEqual(self.launch.video_attempts("dreamcast", "/nonexistent"), ["gl"])
        d = tempfile.mkdtemp(prefix="rgos-boot-")
        with open(os.path.join(d, "retroarch-dc-video.txt"), "w") as f:
            f.write("glcore\n")
        self.assertEqual(self.launch.video_attempts("dreamcast", d), ["glcore"])
        self.assertIn("--verbose", self.launch.build_command("/c.so", "/g.chd", "/r", "/run.cfg", verbose=True))

    def test_gles_mismatch_is_detected_so_it_is_not_retried(self):
        self.assertTrue(self.launch.gl_mismatch("[ERROR] Requesting OpenGL context, but RetroArch is compiled against OpenGLES. Cannot use HW context."))
        self.assertFalse(self.launch.gl_mismatch("[ERROR] something else"))
        self.assertFalse(self.launch.gl_mismatch(""))

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
        report = open(os.path.join(d, "logs", "rgos-retroarch.txt")).read()
        self.assertIn("earlier attempt 1", report)
        self.assertIn("SIGSEGV", report)


    def _launch_with_log_error(self, run_seconds):
        """Launch a GameCube game whose log ends in an [ERROR] line and which exits 0 after run_seconds; returns launches."""
        L = self.launch
        d = tempfile.mkdtemp(prefix="rgos-run-")
        with open(os.path.join(d, "ra.log"), "w") as f:
            f.write("[INFO] running\n[ERROR] failed to save SRAM\n")
        clock, seen = [0.0], []

        def fake_call(cmd, **kw):
            seen.append(cmd)
            clock[0] += run_seconds
            return 0

        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}), \
             mock.patch.object(L, "RUN_DIR", d), mock.patch.object(L, "ROMS_ROOT", d), mock.patch.object(L, "BOOT_DIR", d), \
             mock.patch.object(L, "LOG", os.path.join(d, "ra.log")), mock.patch.object(L, "TTY", os.path.join(d, "tty")), \
             mock.patch.object(L, "SYS_INPUT", d), mock.patch.object(L.time, "monotonic", lambda: clock[0]), \
             mock.patch.object(L.subprocess, "call", side_effect=fake_call):
            L.launch_retroarch("gc", "dolphin", "/cores/dolphin_libretro.so", "/roms/gc/g.iso")
        return len(seen)

    def test_quitting_normally_after_a_stray_log_error_is_not_relaunched(self):
        self.assertEqual(self._launch_with_log_error(10.0), 1)

    def test_an_instant_exit_with_a_log_error_still_retries(self):
        self.assertEqual(self._launch_with_log_error(1.0), 2)

    def test_run_config_adds_the_gc_pacing_settings_only_for_gamecube(self):
        gc = self.launch.run_config("gc", "/r", "default", core_options="/run/o.cfg")
        self.assertIn('video_adaptive_vsync = "true"', gc)
        self.assertIn('audio_latency = "96"', gc)
        self.assertIn('core_options_path = "/run/o.cfg"', gc)
        other = self.launch.run_config("psx", "/r", "default")
        self.assertNotIn("adaptive_vsync", other)
        self.assertNotIn("core_options_path", other)

    def test_gc_core_options_defaults_safe_mode_and_user_overrides(self):
        L = self.launch
        d = tempfile.mkdtemp(prefix="rgos-opt-")
        read = lambda p: dict(l.rstrip("\n").split(" = ", 1) for l in open(p))
        fast = read(L.gc_core_options(d, d))
        self.assertEqual(fast["dolphin_fastmem"], '"enabled"')
        self.assertEqual(fast["dolphin_efb_scale"], '"x1 (640 x 528)"')
        self.assertEqual(read(L.gc_core_options(d, d, safe=True))["dolphin_fastmem"], '"disabled"')
        os.makedirs(os.path.join(d, "config"))
        with open(os.path.join(d, "config", "dolphin-options.cfg"), "w") as f:
            f.write('dolphin_efb_scale = "x2 (1280 x 1056)"\nnot_dolphin = "x"\n# comment\ndolphin_fastmem = enabled\n')
        mine = read(L.gc_core_options(d, d, safe=True))
        self.assertEqual(mine["dolphin_efb_scale"], '"x2 (1280 x 1056)"')
        self.assertEqual(mine["dolphin_fastmem"], '"enabled"')
        self.assertNotIn("not_dolphin", mine)

    def test_the_retry_after_a_crash_also_turns_fastmem_off(self):
        L = self.launch
        d = tempfile.mkdtemp(prefix="rgos-run-")
        seen = []
        codes = iter([-11, 0])

        def fake_call(cmd, **kw):
            seen.append(open(os.path.join(d, "dolphin-options.cfg")).read())
            return next(codes)

        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}), \
             mock.patch.object(L, "RUN_DIR", d), mock.patch.object(L, "ROMS_ROOT", d), mock.patch.object(L, "BOOT_DIR", d), \
             mock.patch.object(L, "LOG", os.path.join(d, "ra.log")), mock.patch.object(L, "TTY", os.path.join(d, "tty")), \
             mock.patch.object(L, "SYS_INPUT", d), mock.patch.object(L.subprocess, "call", side_effect=fake_call):
            L.launch_retroarch("gc", "dolphin", "/cores/dolphin_libretro.so", "/roms/gc/g.iso")
        self.assertIn('dolphin_fastmem = "enabled"', seen[0])
        self.assertIn('dolphin_fastmem = "disabled"', seen[1])


if __name__ == "__main__":
    unittest.main()


class PortEnvTests(unittest.TestCase):
    """An oversized SDL_GAMECONTROLLERCONFIG makes every later exec() fail with E2BIG (seen in GTA III)."""

    def setUp(self):
        self.launch = load_launch()
        self.run = tempfile.mkdtemp(prefix="rgos-portenv-")
        self.launch.RUN_DIR = self.run
        self.launch.NATIVE_LOG = os.path.join(self.run, "native.log")

    def test_hook_clamps_an_oversized_controller_config(self):
        env = self.launch.native_env({"RGOS_NO_HW": "1", "PATH": "/usr/bin:/bin"})
        self.assertEqual(env["BASH_ENV"], os.path.join(self.run, "port-env.sh"))
        script = os.path.join(self.run, "port.sh")
        with open(script, "w") as f:
            f.write('export SDL_GAMECONTROLLERCONFIG="$(head -c 200000 /dev/zero | tr \'\\0\' a)"\n'
                    '/usr/bin/env true && echo "len=${#SDL_GAMECONTROLLERCONFIG}"\n')
        out = subprocess.run(["bash", script], env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertLess(int(out.stdout.split("len=")[1]), 60000)
        with open(self.launch.NATIVE_LOG) as f:
            self.assertIn("replaced by the RG OS pad mapping", f.read())

    def test_tar_ignores_the_packers_owner(self):
        env = self.launch.native_env({"RGOS_NO_HW": "1"})
        self.assertEqual(env["TAR_OPTIONS"], "--no-same-owner")


class PortDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.launch = load_launch()
        self.run = tempfile.mkdtemp(prefix="rgos-diag-")
        self.launch.RUN_DIR = self.run
        self.launch.NATIVE_LOG = os.path.join(self.run, "native.log")

    def test_hook_logs_the_gl_setup_once_after_libgl_is_sourced(self):
        env = self.launch.native_env({"RGOS_NO_HW": "1", "PATH": "/usr/bin:/bin"})
        script = os.path.join(self.run, "port.sh")
        with open(script, "w") as f:
            f.write("export LIBGL_ES=2 LIBGL_GL=21\n:\n:\n")
        out = subprocess.run(["bash", script], env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        with open(self.launch.NATIVE_LOG) as f:
            lines = [l for l in f if "GL env:" in l]
        self.assertEqual(len(lines), 1)
        self.assertIn("LIBGL_ES=2", lines[0])

    def test_drm_nodes_names_the_driver_of_each_card(self):
        sysdrm = os.path.join(self.run, "drm")
        for card, drv in (("card0", "panfrost"), ("card1", "sun4i-drm")):
            os.makedirs(os.path.join(sysdrm, card, "device"))
            os.makedirs(os.path.join(self.run, "drivers", drv), exist_ok=True)
            os.symlink(os.path.join(self.run, "drivers", drv), os.path.join(sysdrm, card, "device", "driver"))
        os.makedirs(os.path.join(sysdrm, "card1-HDMI-A-1"))
        text = self.launch.drm_nodes(sysdrm)
        self.assertIn("card0: driver=panfrost connectors=none", text)
        self.assertIn("card1: driver=sun4i-drm connectors=HDMI-A-1", text)
