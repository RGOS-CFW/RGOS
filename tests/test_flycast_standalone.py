import os
import stat
import tempfile
import unittest
from unittest import mock

from tests.helpers import load_menu
from tests.test_dreamcast import load
from tests.test_launch import load_launch

menu = load_menu()
cores = load("cores")
coreinstall = load("coreinstall")


def fake_exe(directory, name="flycast", mode=0o755):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\n")
    os.chmod(path, mode)
    return path


class CoreTableTests(unittest.TestCase):
    def test_dreamcast_offers_both_flycasts_and_the_libretro_one_stays_the_default(self):
        self.assertEqual(cores.default_core("dreamcast"), "flycast")
        self.assertEqual(cores.SYSTEM_CORE_COMPATIBILITY["dreamcast"], ("flycast", "flycast_standalone"))
        self.assertEqual(cores.compatible_cores("dreamcast", ["flycast", "flycast_standalone"]), ["flycast", "flycast_standalone"])
        self.assertEqual(cores.compatible_cores("dreamcast", ["flycast_standalone"]), ["flycast_standalone"])

    def test_standalone_is_found_by_its_executable_only(self):
        d = tempfile.mkdtemp()
        self.assertEqual(cores.standalone_path("flycast_standalone", [d]), "")
        fake_exe(d, mode=0o644)  # not executable
        self.assertEqual(cores.standalone_path("flycast_standalone", [d]), "")
        path = fake_exe(d)
        self.assertEqual(cores.standalone_path("flycast_standalone", [d]), path)
        self.assertEqual(cores.standalone_path("flycast", [d]), "")  # libretro names are not standalone names
        self.assertEqual(cores.standalone_path("mgba", [d]), "")

    def test_installed_cores_lists_the_standalone_emulator_when_present(self):
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"RGOS_STANDALONE_DIRS": d}):
            self.assertNotIn("flycast_standalone", cores.installed_cores())
            fake_exe(d)
            self.assertIn("flycast_standalone", cores.installed_cores())

    def test_core_installer_never_offers_it_for_download(self):
        systems = [(s[0], s[1], s[4]) for s in menu.ALL_SYSTEMS if s[2] == "retroarch"]
        rows = coreinstall.candidates(systems, cores.SYSTEM_CORE_COMPATIBILITY, [], menu.CORE_NAMES)
        names = [r["core"] for r in rows]
        self.assertIn("flycast", names)
        self.assertNotIn("flycast_standalone", names)

    def test_name_is_safe_and_labelled(self):
        self.assertRegex("flycast_standalone", coreinstall.NAME_RE)
        self.assertEqual(menu.CORE_NAMES["flycast_standalone"], "Flycast (standalone)")


class MenuLabelTests(unittest.TestCase):
    def test_runner_text_says_retroarch_only_for_libretro_cores(self):
        self.assertEqual(menu.runner_label("dreamcast", {}), "RetroArch + Flycast")
        self.assertEqual(menu.runner_label("dreamcast", {"emulators": {"dreamcast": "flycast"}}), "RetroArch + Flycast")
        self.assertEqual(menu.runner_label("dreamcast", {"emulators": {"dreamcast": "flycast_standalone"}}), "Flycast (standalone)")
        self.assertEqual(menu.game_runner_text({"sid": "dreamcast", "core": "retroarch"}, {"emulators": {"dreamcast": "flycast_standalone"}}),
                         "Flycast (standalone)")
        self.assertEqual(menu.runner_label("gba", {}), "RetroArch + mGBA")


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.launch = load_launch()
        self.tmp = tempfile.mkdtemp(prefix="rgos-sa-")
        self.bin_dir = os.path.join(self.tmp, "bin")
        self.launch.STANDALONE_DIRS = [self.bin_dir]
        self.launch.ROMS_ROOT = os.path.join(self.tmp, "roms-card")
        self.launch.NATIVE_LOG = os.path.join(self.tmp, "native.log")
        self.launch.RUN_DIR = os.path.join(self.tmp, "run")
        self.launch.GAME_FLAG = os.path.join(self.launch.RUN_DIR, "ingame")
        self.game = os.path.join(self.tmp, "Crazy Taxi.chd")
        with open(self.game, "wb") as f:
            f.write(b"x")

    def test_core_file_resolves_the_executable_not_a_so(self):
        self.assertEqual(self.launch.core_file("flycast_standalone"), "")
        exe = fake_exe(self.bin_dir)
        self.assertEqual(self.launch.core_file("flycast_standalone"), exe)
        self.assertEqual(self.launch.core_file("flycast", dirs=[self.bin_dir]), "")  # libretro lookup still wants *_libretro.so

    def test_users_choice_of_standalone_is_used_and_a_missing_one_falls_back(self):
        state = {"emulators": {"dreamcast": "flycast_standalone"}}
        default = lambda sid: "flycast"
        compat = lambda sid, cores=None: []
        with mock.patch.object(self.launch, "CORE_DIRS", [os.path.join(self.tmp, "libretro")]):
            fake_exe(os.path.join(self.tmp, "libretro"), "flycast_libretro.so")
            self.assertEqual(self.launch.pick_core("dreamcast", state, default, compat), "flycast")  # no executable yet
            fake_exe(self.bin_dir)
            self.assertEqual(self.launch.pick_core("dreamcast", state, default, compat), "flycast_standalone")

    def test_standalone_env_keeps_settings_on_the_roms_card_and_links_the_bios(self):
        bios = os.path.join(self.launch.ROMS_ROOT, "bios", "dc")
        os.makedirs(bios)
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}):
            env = self.launch.standalone_env("dreamcast", cwd=self.tmp)
        self.assertEqual(env["XDG_CONFIG_HOME"], os.path.join(self.launch.ROMS_ROOT, "config"))
        self.assertEqual(env["XDG_DATA_HOME"], os.path.join(self.launch.ROMS_ROOT, "config", "data"))
        link = os.path.join(env["XDG_DATA_HOME"], "flycast", "data")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), bios)
        self.assertNotIn("SDL_VIDEODRIVER", env)

    def _env(self):
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}):
            return self.launch.standalone_env("dreamcast", cwd=self.tmp)

    def test_bios_added_after_flycast_made_its_empty_data_folder_is_still_linked(self):
        data = os.path.join(self.launch.ROMS_ROOT, "config", "data", "flycast", "data")
        os.makedirs(data)  # what Flycast leaves behind after a run without a BIOS
        bios = os.path.join(self.launch.ROMS_ROOT, "bios", "dc")
        os.makedirs(bios)
        self._env()
        self.assertTrue(os.path.islink(data))
        self.assertEqual(os.readlink(data), bios)

    def test_a_data_folder_with_files_is_left_alone(self):
        data = os.path.join(self.launch.ROMS_ROOT, "config", "data", "flycast", "data")
        os.makedirs(data)
        open(os.path.join(data, "dc_boot.bin"), "w").close()
        os.makedirs(os.path.join(self.launch.ROMS_ROOT, "bios", "dc"))
        self._env()
        self.assertFalse(os.path.islink(data))
        self.assertTrue(os.path.exists(os.path.join(data, "dc_boot.bin")))

    def test_a_link_to_a_stale_bios_folder_is_repointed(self):
        data_dir = os.path.join(self.launch.ROMS_ROOT, "config", "data", "flycast")
        os.makedirs(data_dir)
        os.symlink(os.path.join(self.tmp, "gone"), os.path.join(data_dir, "data"))
        bios = os.path.join(self.launch.ROMS_ROOT, "bios", "dc")
        os.makedirs(bios)
        self._env()
        self.assertEqual(os.readlink(os.path.join(data_dir, "data")), bios)

    def test_launch_runs_the_executable_on_the_game_without_retroarch(self):
        exe = fake_exe(self.bin_dir)
        seen = {}

        def fake_call(cmd, **kw):
            seen.update(cmd=cmd, cwd=kw["cwd"])
            return 0, False
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}), \
                mock.patch.object(self.launch, "call_native", side_effect=fake_call), \
                mock.patch.object(self.launch, "set_game_flag") as flag, \
                mock.patch.object(self.launch, "set_governor", return_value={}), \
                mock.patch.object(self.launch, "restore_governor"), \
                mock.patch.object(self.launch, "save_native_report"), \
                mock.patch.object(self.launch, "launch_retroarch") as ra:
            rc = self.launch.launch_standalone("dreamcast", "flycast_standalone", exe, self.game)
        self.assertEqual(rc, 0)
        self.assertEqual(seen["cmd"], [exe, self.game])
        self.assertEqual(seen["cwd"], self.tmp)
        ra.assert_not_called()
        flag.assert_any_call(True, kind="native", title="Crazy Taxi")
        flag.assert_called_with(False)

    def test_early_failure_is_shown(self):
        exe = fake_exe(self.bin_dir)
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}), \
                mock.patch.object(self.launch, "call_native", return_value=(1, False)), \
                mock.patch.object(self.launch, "set_game_flag"), \
                mock.patch.object(self.launch, "set_governor", return_value={}), \
                mock.patch.object(self.launch, "restore_governor"), \
                mock.patch.object(self.launch, "save_native_report"), \
                mock.patch.object(self.launch, "show_error") as err:
            self.launch.launch_standalone("dreamcast", "flycast_standalone", exe, self.game)
        err.assert_called_once()
        self.assertIn("flycast_standalone", err.call_args[0][0])


class BuildScriptTests(unittest.TestCase):
    def test_build_restores_libraries_the_dev_purge_removed_from_standalone_flycast(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "build.sh"), encoding="utf-8") as fh:
            text = fh.read()
        purge = text.index("apt-get purge -y --auto-remove gcc")
        check = text.index("ldd /usr/local/bin/flycast 2>&1 | grep")
        self.assertGreater(check, purge)  # the repair must run after the purge, not before it
        self.assertIn("libzip5", text[check:])


if __name__ == "__main__":
    unittest.main()
