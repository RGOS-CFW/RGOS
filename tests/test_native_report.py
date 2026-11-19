import os
import tempfile
import unittest
from unittest import mock

from tests import helpers
from tests.test_launch import load_launch


class NativeReportTests(unittest.TestCase):
    def setUp(self):
        self.launch = load_launch()
        self.tmp = tempfile.mkdtemp(prefix="rgos-nreport-")
        self.boot = os.path.join(self.tmp, "boot")
        os.makedirs(self.boot)
        self.port = os.path.join(self.tmp, "PortMaster")
        os.makedirs(self.port)
        open(os.path.join(self.port, "PortMaster.sh"), "w").close()
        self.launch.NATIVE_LOG = os.path.join(self.tmp, "native.log")
        self.launch.LAUNCH_LOG = os.path.join(self.tmp, "launch.log")

    def report(self):
        with open(os.path.join(self.boot, "rgos-native.txt")) as f:
            return f.read()

    def test_report_lands_on_the_boot_partition_with_the_native_log(self):
        with open(self.launch.NATIVE_LOG, "w") as f:
            f.write("line one\nunzip: command not found\n")
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}):
            self.launch.save_native_report("PortMaster", ["bash", "PortMaster.sh"], 127, 3.2, self.port, boot_dir=self.boot)
        text = self.report()
        self.assertIn("PortMaster rc=127", text)
        self.assertIn("missing tools:", text)
        self.assertIn("PortMaster.sh", text)
        self.assertIn("unzip: command not found", text)

    def test_a_port_that_printed_nothing_is_said_so(self):
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}):
            self.launch.save_native_report("native port", ["sh", "x.sh"], 0, 1.0, self.port, boot_dir=self.boot)
        self.assertIn("the port printed nothing", self.report())

    def test_a_missing_boot_partition_never_raises(self):
        with mock.patch.dict(os.environ, {"RGOS_NO_HW": "1"}):
            self.launch.save_native_report("native port", ["sh"], 1, 1.0, self.port, boot_dir=os.path.join(self.tmp, "nope"))

    def test_session_snapshot_does_not_print_tail_errors_for_missing_logs(self):
        with open(os.path.join(helpers.RGOS, "rgos-session"), newline="") as f:
            text = f.read()
        self.assertIn('if [ -f "$f" ]; then tail -n 100 "$f"', text)
        self.assertNotIn('echo "--- $f"; tail -n 100 "$f" 2>&1; done', text)


if __name__ == "__main__":
    unittest.main()
