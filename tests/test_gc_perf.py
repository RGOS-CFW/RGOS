import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    loader = importlib.machinery.SourceFileLoader("rgos_launch_gc", os.path.join(ROOT, "rgos", "rgos-launch"))
    spec = importlib.util.spec_from_loader("rgos_launch_gc", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


L = load()


class GcPerf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dev = os.path.join(self.tmp, "dev")
        os.environ["RGOS_DEVICE_FILE"] = self.dev

    def tearDown(self):
        os.environ.pop("RGOS_DEVICE_FILE", None)

    def set_device(self, name):
        with open(self.dev, "w") as f:
            f.write(name + "\n")

    def test_gpu_governor_is_left_alone_on_h700_only(self):
        gpu = "/sys/class/devfreq/1800000.gpu/governor"
        cpu = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        self.set_device("rg35xxh")
        self.assertTrue(L.gpu_reclock_unsafe(gpu))
        self.assertFalse(L.gpu_reclock_unsafe(cpu))
        self.set_device("rg-rotate")
        self.assertFalse(L.gpu_reclock_unsafe(gpu))

    def test_benign_retroarch_errors_do_not_count_as_a_failed_start(self):
        log = ('[ERROR] Failed to write to playlist file: "/etc/rgos/content_history.lpl".\n'
               '[ERROR] [Autoconf]: No free and unreserved player slots found for adding new device "x"!\n')
        self.assertFalse(L.real_error(log))
        self.assertTrue(L.real_error(log + "[ERROR] [Core]: Failed to load content.\n"))

    def test_h700_options_turn_off_bbox_and_use_fast_depth(self):
        self.set_device("rg35xxsp")
        roms = os.path.join(self.tmp, "roms")
        os.makedirs(roms)
        path = L.gc_core_options(roms, os.path.join(self.tmp, "run"))
        text = open(path).read()
        self.assertIn('dolphin_bbox_enabled = "disabled"', text)
        self.assertIn('dolphin_fast_depth_calc = "enabled"', text)
        self.assertIn('dolphin_shader_compilation_mode = "a-sync"', text)


if __name__ == "__main__":
    unittest.main()
