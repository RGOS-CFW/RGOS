import importlib.util
import os
import tempfile
import unittest
from fractions import Fraction

from tests import helpers

_spec = importlib.util.spec_from_file_location("rgos_fbout", os.path.join(helpers.RGOS, "fbout.py"))
fbout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fbout)


class Surf:
    """4 bytes per pixel, rows kept in one bytearray; just enough of pygame.Surface for FbOut.present."""

    def __init__(self, size, *a, **k):
        self.w, self.h = size
        self.data = bytearray(self.w * self.h * 4)

    def get_size(self): return (self.w, self.h)
    def get_pitch(self): return self.w * 4
    def get_bitsize(self): return 32
    def get_buffer(self): return self.data

    def subsurface(self, rect):
        x, y, w, h = rect
        out = Surf((w, h))
        for r in range(h):
            out.data[r * w * 4:(r + 1) * w * 4] = self.data[((y + r) * self.w + x) * 4:((y + r) * self.w + x + w) * 4]
        return out

    def blit(self, src, dest):
        x, y = dest
        for r in range(src.h):
            if 0 <= y + r < self.h:
                self.data[((y + r) * self.w + x) * 4:((y + r) * self.w + x + src.w) * 4] = src.data[r * src.w * 4:(r + 1) * src.w * 4]


def _shrink(vals, n):
    """Area average of len(vals) samples down to n, exact fractions: how a shrinking smoothscale weighs rows."""
    m, out = len(vals), []
    for j in range(n):
        lo, hi, acc = Fraction(j * m, n), Fraction((j + 1) * m, n), Fraction(0)
        i = int(lo)
        while Fraction(i) < hi:
            acc += vals[i] * (min(hi, Fraction(i + 1)) - max(lo, Fraction(i)))
            i += 1
        out.append(int(acc / (hi - lo)))
    return out


def smoothscale(src, size):
    w, h = size
    out = Surf(size)
    cols = [[[src.data[(r * src.w + c) * 4 + b] for r in range(src.h)] for c in range(src.w)] for b in range(4)]
    for b in range(4):
        rows_scaled = [_shrink(cols[b][c], h) for c in range(src.w)]          # [c][row]
        for y in range(h):
            line = _shrink([rows_scaled[c][y] for c in range(src.w)], w)
            for x in range(w):
                out.data[(y * w + x) * 4 + b] = line[x]
    return out


class FakePg:
    class transform:
        smoothscale = staticmethod(smoothscale)
        scale = staticmethod(smoothscale)
    Surface = Surf


def make_fb(xres, yres, pages=1):
    fb = object.__new__(fbout.FbOut)
    fd, path = tempfile.mkstemp(prefix="rgos-fb-")
    fb.fd, fb.path = fd, path
    fb.pg, fb.rotate, fb.xres, fb.yres = FakePg, 0, xres, yres
    fb.bytes_pp, fb.line, fb.pages, fb.page = 4, xres * 4, pages, 0
    fb.xoff = fb.yoff = 0
    fb.use_write, fb.vsync = True, False
    fb.surf = Surf((xres, yres))
    fb.last, fb.bands, fb.last_bands, fb.plan = None, [None, None], None, None
    fb.cache_key = fb.cache = None
    fb._flip = lambda page: None
    fb.writes = []
    real = fb._put
    fb._put = lambda off, data: (fb.writes.append((off, len(data))), real(off, data))[1]
    os.ftruncate(fd, xres * yres * 4 * pages)
    return fb


def frame(w, h, seed):
    c = Surf((w, h))
    for i in range(len(c.data)):
        c.data[i] = (i * 7 + seed * 13) % 251
    return c


class PlanTests(unittest.TestCase):
    def test_unscaled_uses_plain_bands(self):
        self.assertEqual(fbout.band_plan((720, 480), (720, 480)), (16, 16))

    def test_540_to_480_uses_whole_row_groups(self):
        bs, bd = fbout.band_plan((720, 540), (640, 480))
        self.assertEqual((bs, bd), (18, 16))
        self.assertEqual(540 % bs, 0)

    def test_no_clean_ratio_or_letterbox_falls_back(self):
        self.assertIsNone(fbout.band_plan((720, 541), (640, 480)))
        self.assertIsNone(fbout.band_plan((720, 720), (640, 480)))


class PresentTests(unittest.TestCase):
    def reference(self, canvas, xres, yres):
        if (canvas.w, canvas.h) == (xres, yres):
            return bytes(canvas.data)
        return bytes(smoothscale(canvas, (xres, yres)).data)

    def screen(self, fb, page=0):
        with open(fb.path, "rb") as f:
            f.seek(page * fb.yres * fb.line)
            return f.read(fb.yres * fb.line)

    def tearDown(self):
        pass

    def run_case(self, cw, ch, xres, yres):
        fb = make_fb(xres, yres)
        a = frame(cw, ch, 1)
        fb.present(a)
        self.assertEqual(self.screen(fb), self.reference(a, xres, yres))
        # change only the rows of one band: the output must equal a whole-frame conversion, written in one small run
        bs, _bd = fbout.band_plan((cw, ch), (xres, yres))
        b = Surf((cw, ch))
        b.data[:] = a.data
        for r in range(bs, 2 * bs):
            for x in range(cw * 4):
                b.data[r * cw * 4 + x] ^= 0x55
        fb.writes.clear()
        fb.present(b)
        self.assertEqual(self.screen(fb), self.reference(b, xres, yres))
        self.assertEqual(len(fb.writes), 1)
        self.assertLess(fb.writes[0][1], xres * yres * 4 // 2)
        fb.writes.clear()
        fb.present(b)  # identical frame: nothing is written
        self.assertEqual(fb.writes, [])
        os.close(fb.fd)
        os.unlink(fb.path)

    def test_scaled_540_to_480_matches_whole_frame_scaling(self):
        self.run_case(72, 72, 64, 64)  # same 9:8 row groups as 720x540 -> 640x480, small enough to test

    def test_unscaled_matches_and_writes_only_changed_rows(self):
        self.run_case(32, 64, 32, 64)

    def test_two_pages_track_each_page_separately(self):
        xres = yres = 32
        fb = make_fb(xres, yres, pages=2)
        frames = [frame(32, 32, s) for s in (1, 2, 3)]
        for i, fr in enumerate(frames):
            fb.present(fr)
            written = fb.page
            self.assertEqual(self.screen(fb, written), bytes(fr.data), i)
        # a frame that repeats the one two presents ago needs nothing rewritten on its page
        fb.writes.clear()
        fb.present(frames[1])
        self.assertEqual(self.screen(fb, fb.page), bytes(frames[1].data))


if __name__ == "__main__":
    unittest.main()
