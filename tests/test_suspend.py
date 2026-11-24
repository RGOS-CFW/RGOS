import os
import sys
import unittest

from tests import helpers

sys.path.insert(0, helpers.RGOS)
import suspend


def fake_sys(with_state=False):
    root = helpers.sandbox()
    def w(rel, text):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)
    w("class/backlight/panel/brightness", "200")
    w("class/backlight/panel/max_brightness", "255")
    w("class/leds/pwr/brightness", "1")
    w("class/rfkill/rfkill0/type", "wlan")
    w("class/rfkill/rfkill0/soft", "0")
    if with_state:
        w("power/state", "freeze mem")
        w("power/mem_sleep", "s2idle [deep]")
    return root


def read(root, rel):
    return open(os.path.join(root, rel)).read().strip()


class SleepManagerTests(unittest.TestCase):
    def mgr(self, root, mode="auto"):
        return suspend.SleepManager({"suspend": {"mode": mode}}, sys_root=root, run_dir=os.path.join(root, "run"))

    def test_soft_sleep_then_resume(self):
        root = fake_sys()
        m = self.mgr(root)
        self.assertEqual(m.toggle(100.0), "soft")
        self.assertTrue(m.asleep)
        self.assertEqual(read(root, "class/backlight/panel/brightness"), "0")
        self.assertEqual(read(root, "class/leds/pwr/brightness"), "0")
        self.assertEqual(read(root, "class/rfkill/rfkill0/soft"), "1")
        self.assertEqual(m.toggle(200.0), "awake")
        self.assertFalse(m.asleep)
        self.assertGreater(int(read(root, "class/backlight/panel/brightness")), 100)
        self.assertEqual(read(root, "class/leds/pwr/brightness"), "1")
        self.assertEqual(read(root, "class/rfkill/rfkill0/soft"), "0")

    def test_press_right_after_wake_is_ignored(self):
        root = fake_sys()
        m = self.mgr(root)
        m.toggle(100.0)
        m.wake(100.0)
        self.assertEqual(m.toggle(100.2), "ignored")
        self.assertFalse(m.asleep)

    def test_real_suspend_returns_awake(self):
        root = fake_sys(with_state=True)
        m = self.mgr(root, mode="mem")
        self.assertEqual(m.toggle(100.0), "awake")
        self.assertEqual(read(root, "power/state"), "mem")
        self.assertFalse(m.asleep)

    def test_auto_without_wake_source_stays_soft(self):
        root = fake_sys(with_state=True)
        m = self.mgr(root)
        self.assertFalse(m.real_suspend_ok())
        self.assertEqual(m.toggle(100.0), "soft")


if __name__ == "__main__":
    unittest.main()
