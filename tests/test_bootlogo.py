import importlib.util
import os
import struct
import subprocess
import tempfile
import unittest

from tests import helpers


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(helpers.ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bmp2fb = load("tools/bmp2fb.py", "bmp2fb")
mkinitramfs = load("initramfs/mkinitramfs.py", "mkinitramfs")
patch_extlinux = load("initramfs/patch-extlinux.py", "patch_extlinux")


def make_bmp(w, h, pixels, top_down=False):
    """24-bit BMP; pixels is a list of rows (top to bottom) of (r, g, b)."""
    row = (w * 3 + 3) & ~3
    body = b""
    for y in (range(h) if top_down else range(h - 1, -1, -1)):
        line = b"".join(bytes((b, g, r)) for r, g, b in pixels[y])
        body += line + b"\0" * (row - len(line))
    hdr = b"BM" + struct.pack("<IHHI", 54 + len(body), 0, 0, 54)
    hdr += struct.pack("<IiiHHIIiiII", 40, w, -h if top_down else h, 1, 24, 0, len(body), 0, 0, 0, 0)
    return hdr + body


class Bmp2FbTests(unittest.TestCase):
    def test_bottom_up_bmp_becomes_top_down_bgrx(self):
        px = [[(1, 2, 3), (4, 5, 6), (7, 8, 9)], [(10, 11, 12), (13, 14, 15), (16, 17, 18)]]
        w, h, raw = bmp2fb.convert(make_bmp(3, 2, px))
        self.assertEqual((w, h, len(raw)), (3, 2, 24))
        self.assertEqual(raw[:8], bytes((3, 2, 1, 0, 6, 5, 4, 0)))      # first screen row = first row of the picture
        self.assertEqual(raw[12:16], bytes((12, 11, 10, 0)))           # second screen row

    def test_top_down_bmp_gives_the_same_result(self):
        px = [[(1, 2, 3), (4, 5, 6), (7, 8, 9)], [(10, 11, 12), (13, 14, 15), (16, 17, 18)]]
        self.assertEqual(bmp2fb.convert(make_bmp(3, 2, px))[2], bmp2fb.convert(make_bmp(3, 2, px, top_down=True))[2])

    def test_other_formats_are_refused(self):
        with self.assertRaises(ValueError):
            bmp2fb.convert(b"PNG....")
        bad = bytearray(make_bmp(1, 1, [[(0, 0, 0)]]))
        bad[28:30] = struct.pack("<H", 8)
        with self.assertRaises(ValueError):
            bmp2fb.convert(bytes(bad))

    def test_every_shipped_logo_converts_to_a_file_named_after_its_size(self):
        d = tempfile.mkdtemp(prefix="rgos-logo-")
        for dev, (w, h) in (("rg-rotate", (720, 720)), ("rg34xxsp", (720, 480)), ("rg35xxh", (640, 480)), ("rg35xxsp", (640, 480))):
            src = os.path.join(helpers.ROOT, "bootlogo", "bootlogo-%s.bmp" % dev)
            bmp2fb.main(["x", src, d])
            self.assertEqual(os.path.getsize(os.path.join(d, "bootlogo-%dx%d.raw" % (w, h))), w * h * 4)


class InitramfsLogoTests(unittest.TestCase):
    def test_logo_files_go_into_the_cpio_under_logo(self):
        d = tempfile.mkdtemp(prefix="rgos-cpio-")
        files = {}
        for n, data in (("busybox", b"BB"), ("init", b"#!/bin/sh\n"), ("bootlogo-2x1.raw", b"\1\2\3\0\4\5\6\0")):
            files[n] = os.path.join(d, n)
            with open(files[n], "wb") as f:
                f.write(data)
        with_logo = mkinitramfs.build(files["busybox"], files["init"], [files["bootlogo-2x1.raw"]])
        self.assertIn(b"logo/bootlogo-2x1.raw", with_logo)
        self.assertIn(b"\1\2\3\0\4\5\6\0", with_logo)
        self.assertNotIn(b"logo/", mkinitramfs.build(files["busybox"], files["init"]))

    def test_init_script_paints_before_it_waits_and_stops_before_switch_root(self):
        text = open(os.path.join(helpers.ROOT, "initramfs", "init")).read()
        self.assertLess(text.index("paint_logo /logo"), text.index("until find_boot"))
        self.assertLess(text.index('kill "$LOGO_PID"'), text.index("exec switch_root"))


class ExtlinuxQuietTests(unittest.TestCase):
    SRC = "LABEL a\n  LINUX /Image\n  APPEND boot=LABEL=RGOS console=tty1\n"

    def test_quiet_and_cursor_off_are_added_once(self):
        out = patch_extlinux.patch(self.SRC, "/i.cpio")
        self.assertEqual(out.count("quiet"), 1)
        self.assertEqual(out.count("vt.global_cursor_default=0"), 1)
        self.assertEqual(patch_extlinux.patch(out, "/i.cpio"), out)

    def test_existing_quiet_is_not_doubled(self):
        out = patch_extlinux.patch(self.SRC.replace("console=tty1", "quiet console=tty1"), "/i.cpio")
        self.assertEqual(out.count("quiet"), 1)

    def test_a_block_without_append_gets_one(self):
        out = patch_extlinux.patch("LABEL a\n LINUX /Image\n", "/i")
        self.assertIn("APPEND quiet loglevel=0 vt.global_cursor_default=0 rdinit=/rgos-init", out)


class PaintLogoShellTests(unittest.TestCase):
    """Run the real paint_logo() from the init script against a fake sysfs / framebuffer."""

    def run_paint(self, bpp, stride, size, raw_name="bootlogo-4x2.raw"):
        d = tempfile.mkdtemp(prefix="rgos-fb-")
        fb = os.path.join(d, "fb0")
        os.makedirs(fb)
        for n, v in (("bits_per_pixel", bpp), ("stride", stride), ("virtual_size", size)):
            with open(os.path.join(fb, n), "w") as f:
                f.write(v + "\n")
        logo = os.path.join(d, "logo")
        os.makedirs(logo)
        with open(os.path.join(logo, raw_name), "wb") as f:
            f.write(b"\xaa" * 32)
        dev = os.path.join(d, "devfb")
        open(dev, "wb").close()
        text = open(os.path.join(helpers.ROOT, "initramfs", "init")).read()
        start = text.index("paint_logo() {")
        func = text[start:text.index("\n}\n", start) + 3]
        func = func.replace("/sys/class/graphics/fb0", fb).replace("[ -c /dev/fb0 ]", "[ -f %s ]" % dev).replace("> /dev/fb0", "> " + dev)
        rc = subprocess.run(["sh", "-c", func + '\npaint_logo "%s"' % logo]).returncode
        return rc, open(dev, "rb").read()

    def test_matching_framebuffer_is_painted(self):
        rc, data = self.run_paint("32", "16", "4,2")
        self.assertEqual((rc, data), (0, b"\xaa" * 32))

    def test_other_framebuffers_are_left_alone(self):
        for bpp, stride, size in (("16", "8", "4,2"), ("32", "20", "4,2"), ("32", "16", "5,2")):
            rc, data = self.run_paint(bpp, stride, size)
            self.assertEqual((rc, data), (1, b""), (bpp, stride, size))


if __name__ == "__main__":
    unittest.main()
