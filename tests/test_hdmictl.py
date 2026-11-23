import importlib.util
import os
import tempfile
import unittest

from tests import helpers

_spec = importlib.util.spec_from_file_location("rgos_hdmictl", os.path.join(helpers.RGOS, "hdmictl.py"))
hdmictl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hdmictl)


class HDMIControlTests(unittest.TestCase):
    def test_patch_adds_and_replaces_video_argument_only_on_append(self):
        src = "LABEL RGOS\n  LINUX /KERNEL\n  APPEND root=/dev/mmcblk0p2 quiet\n"
        out = hdmictl.patch_extlinux_text(src, "720p")
        self.assertIn("video=HDMI-A-1:1280x720@60", out)
        self.assertEqual(hdmictl.patch_extlinux_text(out, "480p").count("video="), 1)
        self.assertIn("video=HDMI-A-1:720x480@60", hdmictl.patch_extlinux_text(out, "480p"))
        self.assertIn("LINUX /KERNEL", out)

    def test_auto_removes_video_argument(self):
        src = "APPEND root=/dev/mmcblk0p2 video=HDMI-A-1:1280x720@60 quiet\n"
        self.assertNotIn("video=HDMI", hdmictl.patch_extlinux_text(src, "auto"))
        self.assertIn("quiet", hdmictl.patch_extlinux_text(src, "auto"))

    def test_set_mode_persists_and_backs_up_extlinux(self):
        with tempfile.TemporaryDirectory() as td:
            ext = os.path.join(td, "extlinux.conf")
            conf = os.path.join(td, "data", "display.json")
            with open(ext, "w") as f:
                f.write("APPEND root=/dev/mmcblk0p2 quiet\n")
            ok, changed = hdmictl.set_mode("1080p", conf, ext)
            self.assertTrue(ok)
            self.assertTrue(changed)
            self.assertEqual(hdmictl.get_mode(conf), "1080p")
            self.assertTrue(os.path.isfile(ext + ".pre-hdmi"))
            with open(ext) as f:
                self.assertIn("1920x1080@60", f.read())

    def test_invalid_mode_does_not_change_config(self):
        self.assertEqual(hdmictl.set_mode("4k", "/tmp/rgos-hdmi-invalid.json", "/no/such/file"), (False, False))

    def test_audio_card_detection(self):
        cards = " 0 [codec          ]: sun4i-codec - onboard\n 1 [hdmi           ]: dw-hdmi - HDMI Audio\n"
        self.assertEqual(hdmictl.audio_hdmi_card(cards), 1)

    def test_retroarch_lines_only_when_hdmi_active(self):
        self.assertEqual(hdmictl.retroarch_lines("/not/a/sysfs/path"), [])


if __name__ == "__main__":
    unittest.main()
