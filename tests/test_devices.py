"""Every device build.sh can build is wired in everywhere: menu canvas, CI workflow, README, update-tar manifest docs."""
import os
import re
import unittest

from tests import helpers


def read(*parts):
    with open(os.path.join(helpers.ROOT, *parts), newline="") as f:
        return f.read()


def build_devices():
    m = re.search(r"^ALL_DEVICES=\(([^)]*)\)", read("build.sh"), re.M)
    return m.group(1).split()


class DeviceWiringTests(unittest.TestCase):
    def test_build_lists_the_rg35xxsp(self):
        self.assertIn("rg35xxsp", build_devices())

    def test_every_device_has_a_menu_canvas(self):
        menu = helpers.load_menu()
        for dev in build_devices():
            self.assertIn(dev, menu.CANVAS, dev)

    def test_rg35xxsp_uses_the_640x480_layout_of_the_rg35xxh(self):
        menu = helpers.load_menu()
        self.assertEqual(menu.CANVAS["rg35xxsp"], menu.CANVAS["rg35xxh"])

    def test_every_device_is_in_the_workflow_readme_and_update_docs(self):
        wf, readme, upd = read(".github", "workflows", "build-rgos.yml"), read("README.md"), read("rgos", "rgos-update")
        for dev in build_devices():
            self.assertIn("- %s" % dev, wf, dev)
            self.assertIn("`%s`" % dev, readme, dev)
            self.assertIn('"%s"' % dev, upd, dev)

    def test_rg35xxsp_gets_no_analog_stick_config(self):
        # the SP has no sticks: the build must only install input-<device>.json / axis binds for the H700 consoles that have them
        m = re.search(r'if \[\[ "\$DEVICE" == "rg34xxsp" \|\| "\$DEVICE" == "rg35xxh" \]\]; then\n\s+mkdir -p "\$ROOTFS/etc/rgos"\n\s+echo \'\{"analog": true\}\'',
                      read("build.sh"))
        self.assertIsNotNone(m)


if __name__ == "__main__":
    unittest.main()
