"""The X rescan runs on a worker thread: start() returns at once, take() delivers the result once, a failed scan keeps the old list."""
import threading
import time
import unittest
from unittest import mock

from tests.helpers import load_menu

menu = load_menu()


def wait_for(rs, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = rs.take()
        if got is not None:
            return got
        time.sleep(0.005)
    return None


class RescanTest(unittest.TestCase):
    def test_start_does_not_block_and_take_delivers_once(self):
        gate = threading.Event()

        def slow():
            gate.wait(2)
            return [{"title": "A"}]
        rs = menu.Rescan()
        with mock.patch.object(menu, "scan_roms", slow):
            t0 = time.monotonic()
            self.assertTrue(rs.start())
            self.assertLess(time.monotonic() - t0, 0.5)
            self.assertTrue(rs.busy)
            self.assertIsNone(rs.take())
            gate.set()
            self.assertEqual(wait_for(rs), [{"title": "A"}])
        self.assertFalse(rs.busy)
        self.assertIsNone(rs.take())

    def test_second_start_is_ignored_while_scanning(self):
        gate = threading.Event()
        calls = []

        def slow():
            calls.append(1)
            gate.wait(2)
            return []
        rs = menu.Rescan()
        with mock.patch.object(menu, "scan_roms", slow):
            self.assertTrue(rs.start())
            self.assertFalse(rs.start())
            gate.set()
            wait_for(rs) or time.sleep(0.05)
        self.assertEqual(len(calls), 1)

    def test_failed_scan_gives_no_list_and_is_not_stuck_busy(self):
        rs = menu.Rescan()
        with mock.patch.object(menu, "scan_roms", side_effect=OSError("card removed")):
            rs.start()
            end = time.monotonic() + 2
            while rs.busy and time.monotonic() < end:
                self.assertIsNone(rs.take())
                time.sleep(0.005)
        self.assertFalse(rs.busy)
        with mock.patch.object(menu, "scan_roms", return_value=[]):
            self.assertTrue(rs.start())
            self.assertEqual(wait_for(rs), [])


if __name__ == "__main__":
    unittest.main()
