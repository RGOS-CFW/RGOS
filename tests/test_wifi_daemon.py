import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "rgos"))
import wifictl


class _Proc:
    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, t=None):
        pass

    def send_signal(self, s):
        pass


class DisableThenEnable(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp(prefix="rgos-wifi-")
        self.cmds = []
        self.conf = {"enabled": True, "networks": [{"ssid": "x"}], "prio": 0, "country": ""}
        patches = (
            mock.patch.object(wifictl, "RUN_DIR", self.run_dir),
            mock.patch.object(wifictl, "SLEEP_FLAG", os.path.join(self.run_dir, "sleeping")),
            mock.patch.object(wifictl, "STATUS_FILE", os.path.join(self.run_dir, "wifi.status")),
            mock.patch.object(wifictl, "load_conf", lambda: self.conf),
            mock.patch.object(wifictl, "sys_conf", lambda: {}),
            mock.patch.object(wifictl, "find_iface", lambda: "wlan0"),
            mock.patch.object(wifictl, "run", lambda cmd, timeout=8: (self.cmds.append(list(cmd)), (0, ""))[1]),
            mock.patch.object(wifictl, "wpa_state", lambda iface: ({"wpa_state": "COMPLETED", "ssid": "x"}, -50)),
            mock.patch.object(wifictl, "ip_of", lambda iface: "10.0.0.2"),
            mock.patch.object(wifictl.time, "sleep", lambda s: None),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def step(self, d):
        with mock.patch.object(wifictl.Daemon, "start_wpa", lambda s, i: setattr(s, "wpa", _Proc())), \
             mock.patch.object(wifictl.Daemon, "start_dhcp", lambda s, i: setattr(s, "dhcp", _Proc())):
            d.step([0.0])

    def test_link_is_brought_up_again_after_wifi_was_switched_off(self):
        d = wifictl.Daemon()
        self.step(d)                       # connected
        self.assertEqual(d.last_state, "connected")
        self.conf["enabled"] = False
        self.step(d)                       # switched off: link goes down
        self.assertIn(["ip", "link", "set", "wlan0", "down"], self.cmds)
        self.cmds.clear()
        self.conf["enabled"] = True
        self.step(d)                       # switched on again
        self.assertIn(["ip", "link", "set", "wlan0", "up"], self.cmds)
        self.assertIn(["rfkill", "unblock", "wifi"], self.cmds)


if __name__ == "__main__":
    unittest.main()
