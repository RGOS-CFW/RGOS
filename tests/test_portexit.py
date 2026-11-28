import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest

from tests import helpers
from tests.test_launch import load_launch

sys.path.insert(0, helpers.RGOS)
import portexit


def ev(code, value):
    return struct.pack("llHHi", 0, 0, portexit.EV_KEY, code, value)


class WatcherCase(unittest.TestCase):
    def start(self, cmd, hold=0.3, grace=0.6):
        self.proc = subprocess.Popen(cmd, start_new_session=True)
        self.addCleanup(self.cleanup)
        r, self.w = os.pipe()
        self.addCleanup(os.close, self.w)
        self.watcher = portexit.ExitWatcher([r], self.proc.pid, lambda: self.proc.poll() is None, hold=hold, grace=grace)
        self.watcher.start()

    def cleanup(self):
        self.watcher.stop()
        self.watcher.join(2)
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait()

    def press(self, *codes, value=1):
        for c in codes:
            os.write(self.w, ev(c, value))


class ComboTests(WatcherCase):
    def test_holding_select_and_start_stops_the_port(self):
        self.start(["sleep", "30"])
        self.press(portexit.BTN_SELECT, portexit.BTN_START)
        self.assertEqual(self.proc.wait(5), -signal.SIGTERM)
        self.watcher.join(2)
        self.assertTrue(self.watcher.fired)

    def test_releasing_before_the_hold_keeps_the_port_running(self):
        self.start(["sleep", "30"], hold=0.6)
        self.press(portexit.BTN_SELECT, portexit.BTN_START)
        time.sleep(0.2)
        self.press(portexit.BTN_START, value=0)
        time.sleep(0.8)
        self.assertIsNone(self.proc.poll())
        self.assertFalse(self.watcher.fired)

    def test_one_button_alone_never_stops_it(self):
        self.start(["sleep", "30"])
        self.press(portexit.BTN_START)
        time.sleep(0.8)
        self.assertIsNone(self.proc.poll())

    def test_other_buttons_are_ignored(self):
        self.start(["sleep", "30"])
        self.press(0x130, 0x131, 0x13C)
        time.sleep(0.6)
        self.assertIsNone(self.proc.poll())

    def test_a_port_that_ignores_sigterm_is_killed(self):
        self.start(["sh", "-c", "trap '' TERM; sleep 30"])
        time.sleep(0.2)
        self.press(portexit.BTN_SELECT, portexit.BTN_START)
        self.assertEqual(self.proc.wait(5), -signal.SIGKILL)

    def test_child_processes_of_the_port_are_stopped_too(self):
        self.start(["sh", "-c", "sleep 30 & echo $! > %s; wait" % os.path.join(tempfile.gettempdir(), "rgos-exit-child")])
        time.sleep(0.3)
        with open(os.path.join(tempfile.gettempdir(), "rgos-exit-child")) as f:
            child = int(f.read())
        self.press(portexit.BTN_SELECT, portexit.BTN_START)
        self.proc.wait(5)
        time.sleep(0.3)
        try:
            with open("/proc/%d/stat" % child) as f:
                state = f.read().rsplit(")", 1)[1].split()[0]
        except OSError:
            state = "X"
        self.assertIn(state, ("X", "Z"))


class FindTests(unittest.TestCase):
    def test_finds_only_the_hub_pad_event_nodes(self):
        d = tempfile.mkdtemp(prefix="rgos-sysinput-")
        self.addCleanup(shutil.rmtree, d, True)
        for node, name in (("event0", "gpio-keys"), ("event3", "RG OS Gamepad"), ("js0", "RG OS Gamepad")):
            os.makedirs(os.path.join(d, node, "device"))
            with open(os.path.join(d, node, "device", "name"), "w") as f:
                f.write(name + "\n")
        self.assertEqual(portexit.find_pad_events(d, "/dev/input"), ["/dev/input/event3"])

    def test_no_pad_means_nothing_to_watch(self):
        self.assertEqual(portexit.find_pad_events("/nonexistent"), [])


class LauncherTests(unittest.TestCase):
    def test_call_native_returns_the_exit_code_and_not_stopped(self):
        launch = load_launch()
        self.assertEqual(launch.call_native(["sh", "-c", "exit 3"]), (3, False))
        self.assertEqual(launch.call_native(["true"]), (0, False))


if __name__ == "__main__":
    unittest.main()
