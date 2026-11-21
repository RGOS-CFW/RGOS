import importlib.util
import os
import unittest

from tests import helpers

_spec = importlib.util.spec_from_file_location("rgos_uiboost", os.path.join(helpers.RGOS, "uiboost.py"))
uiboost = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uiboost)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read(path):
    with open(path) as f:
        return f.read()


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class BoostTests(unittest.TestCase):
    def setUp(self):
        self.root = helpers.sandbox()
        self.cpu = os.path.join(self.root, "devices/system/cpu/cpu0/cpufreq")
        self.gpu = os.path.join(self.root, "class/devfreq/gpu")
        write(self.cpu + "/scaling_governor", "schedutil")
        write(self.cpu + "/scaling_available_governors", "schedutil performance powersave")
        write(self.gpu + "/governor", "simple_ondemand")
        write(self.gpu + "/available_governors", "simple_ondemand performance")
        self.clock = Clock()
        self.b = uiboost.UiBoost(enabled=True, root=self.root, hold=4.0, clock=self.clock)

    def test_poke_switches_to_performance_and_tick_restores_after_the_hold(self):
        self.b.poke()
        self.assertEqual(read(self.cpu + "/scaling_governor"), "performance")
        self.assertEqual(read(self.gpu + "/governor"), "performance")
        self.clock.t += 3.0
        self.b.tick()
        self.assertEqual(read(self.cpu + "/scaling_governor"), "performance")
        self.clock.t += 1.5
        self.b.tick()
        self.assertEqual(read(self.cpu + "/scaling_governor"), "schedutil")
        self.assertEqual(read(self.gpu + "/governor"), "simple_ondemand")
        self.assertFalse(self.b.active)

    def test_activity_extends_the_hold_and_never_records_performance_as_the_original(self):
        self.b.poke()
        self.clock.t += 3.5
        self.b.poke()
        self.clock.t += 3.5
        self.b.tick()
        self.assertTrue(self.b.active)
        self.b.restore()
        self.assertEqual(read(self.cpu + "/scaling_governor"), "schedutil")
        self.b.poke()
        self.b.poke()
        self.b.restore()
        self.assertEqual(read(self.cpu + "/scaling_governor"), "schedutil")

    def test_disabled_and_missing_governors_do_nothing(self):
        off = uiboost.UiBoost(enabled=False, root=self.root, clock=self.clock)
        off.poke()
        self.assertEqual(read(self.cpu + "/scaling_governor"), "schedutil")
        write(self.cpu + "/scaling_available_governors", "schedutil powersave")
        write(self.gpu + "/available_governors", "simple_ondemand")
        none = uiboost.UiBoost(enabled=True, root=self.root, clock=self.clock)
        none.poke()
        self.assertFalse(none.active)
        self.assertEqual(read(self.gpu + "/governor"), "simple_ondemand")

    def test_no_sysfs_is_fine(self):
        b = uiboost.UiBoost(enabled=True, root=helpers.sandbox(), clock=self.clock)
        b.poke()
        b.tick()
        b.restore()
        self.assertFalse(b.active)


if __name__ == "__main__":
    unittest.main()
