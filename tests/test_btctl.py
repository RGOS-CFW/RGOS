import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from tests import helpers

sys.path.insert(0, helpers.RGOS)
try:
    import btctl
finally:
    sys.path.remove(helpers.RGOS)


class ApplyPowerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rgos-bt-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        p = mock.patch.object(btctl, "CONF", os.path.join(self.dir, "bt.json"))
        p.start()
        self.addCleanup(p.stop)

    def power_calls(self, conf):
        if conf is not None:
            with open(btctl.CONF, "w") as f:
                json.dump(conf, f)
        with mock.patch.object(btctl, "run", return_value=(0, "")) as run:
            btctl.apply_power()
        return [c.args[0] for c in run.call_args_list]

    def test_enabled_powers_on(self):
        self.assertEqual(self.power_calls({"enabled": True}), [["bluetoothctl", "power", "on"]])

    def test_disabled_powers_off(self):
        self.assertEqual(self.power_calls({"enabled": False}), [["bluetoothctl", "power", "off"]])

    def test_no_settings_file_defaults_to_on(self):
        self.assertEqual(self.power_calls(None), [["bluetoothctl", "power", "on"]])


class BringUpTests(unittest.TestCase):
    def test_adapter_found_late_is_still_picked_up(self):
        calls = {"n": 0}

        def adapter():
            calls["n"] += 1
            return "hci0" if calls["n"] > 3 else None
        with mock.patch.object(btctl, "adapter", adapter), mock.patch.object(btctl, "load_modules", return_value=[]), \
                mock.patch.object(btctl, "reprobe_serdev", return_value=[]), mock.patch.object(btctl, "run", return_value=(0, "")), \
                mock.patch.object(btctl.time, "sleep"):
            self.assertTrue(btctl.find_adapter())

    def test_gives_up_after_all_attempts_and_dumps_diagnostics(self):
        with mock.patch.object(btctl, "adapter", return_value=None), mock.patch.object(btctl, "load_modules", return_value=[]) as lm, \
                mock.patch.object(btctl, "reprobe_serdev", return_value=[]), mock.patch.object(btctl, "run", return_value=(0, "")), \
                mock.patch.object(btctl, "diag") as diag, mock.patch.object(btctl.time, "sleep"):
            self.assertFalse(btctl.find_adapter(attempts=3))
        self.assertEqual(lm.call_count, 3)
        diag.assert_called_once()

    def test_reprobe_only_touches_unbound_serdev_devices(self):
        d = tempfile.mkdtemp(prefix="rgos-serial-")
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "devices", "serial0"))
        os.makedirs(os.path.join(d, "devices", "serial0-0"))
        os.makedirs(os.path.join(d, "devices", "serial1-0"))
        os.symlink(d, os.path.join(d, "devices", "serial1-0", "driver"))
        open(os.path.join(d, "drivers_probe"), "w").close()
        with mock.patch.object(btctl, "SYSSERIAL", d):
            self.assertEqual(btctl.reprobe_serdev(), ["serial0-0"])
        with open(os.path.join(d, "drivers_probe")) as f:
            self.assertEqual(f.read(), "serial0-0")

    def test_diag_runs_without_a_kernel(self):
        with mock.patch.object(btctl, "run", return_value=(0, "")), mock.patch.object(btctl, "log") as log:
            btctl.diag("test")
        self.assertTrue(any("device-tree Bluetooth nodes" in c.args[0] for c in log.call_args_list))


if __name__ == "__main__":
    unittest.main()
