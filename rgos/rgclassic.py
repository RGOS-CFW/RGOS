"""RG Classic launcher style: the Galla pixel look (red gradient, bitmap font,
16x16 icons, tile grid) carrying the six stock RG OS home buttons.

Font and icon data come from GallaCFW's galla-pixel.h. Only the six icons the
stock launcher needs are included (no Information / Restart). The screen is
drawn on a 240-wide logical surface and scaled up with nearest-neighbour so
pixels stay crisp on every RG OS canvas.

Animation (all pixel-snapped, no sub-pixel blending of the art itself):
  * entrance   tiles pop in with a staggered overshoot, header/footer slide in,
               label bar wipes open, description fades up. Replays (faster)
               whenever the launcher comes back after not being drawn.
  * cursor     one focus box on a damped spring that glides between tiles with
               a hop arc, squash/stretch along the travel axis and a ghost
               trail; wrapping at a row edge flies the cursor in from the side.
  * focus      pulsing border, periodic diagonal shine, twinkle sparkles,
               bobbing icon.
  * label      old name slides out / new name slides in in the move direction,
               arrows kick on a press, description fades in after.
  * ambience   3-layer parallax embers with flicker, slow scanline sweep,
               blinking clock colon, low-battery blink, charging pulse.
"""
import math, random, time
import pygame

LW = 240

BLACK, WHITE, DIM = (8, 0, 3), (255, 244, 244), (216, 168, 172)
RED, REDL, REDM, PANEL = (232, 40, 52), (255, 112, 120), (150, 18, 32), (44, 6, 14)
TONE = ((0, 0, 0), (255, 244, 244), (255, 168, 176), (110, 8, 18))

FONT = (
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    (0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04, 0x00, 0x00),
    (0x0a, 0x0a, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    (0x0a, 0x1f, 0x0a, 0x0a, 0x0a, 0x1f, 0x0a, 0x00, 0x00),
    (0x04, 0x0f, 0x14, 0x0e, 0x05, 0x1e, 0x04, 0x00, 0x00),
    (0x19, 0x19, 0x02, 0x04, 0x08, 0x13, 0x13, 0x00, 0x00),
    (0x0c, 0x12, 0x14, 0x08, 0x15, 0x12, 0x0d, 0x00, 0x00),
    (0x04, 0x04, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    (0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02, 0x00, 0x00),
    (0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08, 0x00, 0x00),
    (0x00, 0x15, 0x0e, 0x1f, 0x0e, 0x15, 0x00, 0x00, 0x00),
    (0x00, 0x04, 0x04, 0x1f, 0x04, 0x04, 0x00, 0x00, 0x00),
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x06, 0x04, 0x08),
    (0x00, 0x00, 0x00, 0x1f, 0x00, 0x00, 0x00, 0x00, 0x00),
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x06, 0x00, 0x00),
    (0x01, 0x02, 0x02, 0x04, 0x08, 0x08, 0x10, 0x00, 0x00),
    (0x0e, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0e, 0x00, 0x00),
    (0x04, 0x0c, 0x04, 0x04, 0x04, 0x04, 0x0e, 0x00, 0x00),
    (0x0e, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1f, 0x00, 0x00),
    (0x0e, 0x11, 0x01, 0x06, 0x01, 0x11, 0x0e, 0x00, 0x00),
    (0x02, 0x06, 0x0a, 0x12, 0x1f, 0x02, 0x02, 0x00, 0x00),
    (0x1f, 0x10, 0x1e, 0x01, 0x01, 0x11, 0x0e, 0x00, 0x00),
    (0x06, 0x08, 0x10, 0x1e, 0x11, 0x11, 0x0e, 0x00, 0x00),
    (0x1f, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08, 0x00, 0x00),
    (0x0e, 0x11, 0x11, 0x0e, 0x11, 0x11, 0x0e, 0x00, 0x00),
    (0x0e, 0x11, 0x11, 0x0f, 0x01, 0x02, 0x0c, 0x00, 0x00),
    (0x00, 0x00, 0x06, 0x06, 0x00, 0x06, 0x06, 0x00, 0x00),
    (0x00, 0x00, 0x06, 0x06, 0x00, 0x06, 0x04, 0x08, 0x00),
    (0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02, 0x00, 0x00),
    (0x00, 0x00, 0x1f, 0x00, 0x1f, 0x00, 0x00, 0x00, 0x00),
    (0x08, 0x04, 0x02, 0x01, 0x02, 0x04, 0x08, 0x00, 0x00),
    (0x0e, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04, 0x00, 0x00),
    (0x0e, 0x11, 0x17, 0x15, 0x17, 0x10, 0x0e, 0x00, 0x00),
    (0x0e, 0x11, 0x11, 0x1f, 0x11, 0x11, 0x11, 0x00, 0x00),
    (0x1e, 0x11, 0x11, 0x1e, 0x11, 0x11, 0x1e, 0x00, 0x00),
    (0x0e, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0e, 0x00, 0x00),
    (0x1e, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1e, 0x00, 0x00),
    (0x1f, 0x10, 0x10, 0x1e, 0x10, 0x10, 0x1f, 0x00, 0x00),
    (0x1f, 0x10, 0x10, 0x1e, 0x10, 0x10, 0x10, 0x00, 0x00),
    (0x0e, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0f, 0x00, 0x00),
    (0x11, 0x11, 0x11, 0x1f, 0x11, 0x11, 0x11, 0x00, 0x00),
    (0x0e, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0e, 0x00, 0x00),
    (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0c, 0x00, 0x00),
    (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11, 0x00, 0x00),
    (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1f, 0x00, 0x00),
    (0x11, 0x1b, 0x15, 0x15, 0x11, 0x11, 0x11, 0x00, 0x00),
    (0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11, 0x00, 0x00),
    (0x0e, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0e, 0x00, 0x00),
    (0x1e, 0x11, 0x11, 0x1e, 0x10, 0x10, 0x10, 0x00, 0x00),
    (0x0e, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0d, 0x00, 0x00),
    (0x1e, 0x11, 0x11, 0x1e, 0x14, 0x12, 0x11, 0x00, 0x00),
    (0x0f, 0x10, 0x10, 0x0e, 0x01, 0x01, 0x1e, 0x00, 0x00),
    (0x1f, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x00),
    (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0e, 0x00, 0x00),
    (0x11, 0x11, 0x11, 0x11, 0x11, 0x0a, 0x04, 0x00, 0x00),
    (0x11, 0x11, 0x11, 0x15, 0x15, 0x1b, 0x11, 0x00, 0x00),
    (0x11, 0x11, 0x0a, 0x04, 0x0a, 0x11, 0x11, 0x00, 0x00),
    (0x11, 0x11, 0x0a, 0x04, 0x04, 0x04, 0x04, 0x00, 0x00),
    (0x1f, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1f, 0x00, 0x00),
    (0x0e, 0x08, 0x08, 0x08, 0x08, 0x08, 0x0e, 0x00, 0x00),
    (0x10, 0x08, 0x08, 0x04, 0x02, 0x02, 0x01, 0x00, 0x00),
    (0x0e, 0x02, 0x02, 0x02, 0x02, 0x02, 0x0e, 0x00, 0x00),
    (0x04, 0x0a, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1f, 0x00),
    (0x08, 0x04, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    (0x00, 0x00, 0x0e, 0x01, 0x0f, 0x11, 0x0f, 0x00, 0x00),
    (0x10, 0x10, 0x1e, 0x11, 0x11, 0x11, 0x1e, 0x00, 0x00),
    (0x00, 0x00, 0x0e, 0x11, 0x10, 0x11, 0x0e, 0x00, 0x00),
    (0x01, 0x01, 0x0f, 0x11, 0x11, 0x11, 0x0f, 0x00, 0x00),
    (0x00, 0x00, 0x0e, 0x11, 0x1f, 0x10, 0x0e, 0x00, 0x00),
    (0x06, 0x08, 0x1e, 0x08, 0x08, 0x08, 0x08, 0x00, 0x00),
    (0x00, 0x00, 0x0f, 0x11, 0x11, 0x11, 0x0f, 0x01, 0x0e),
    (0x10, 0x10, 0x1e, 0x11, 0x11, 0x11, 0x11, 0x00, 0x00),
    (0x04, 0x00, 0x0c, 0x04, 0x04, 0x04, 0x0e, 0x00, 0x00),
    (0x02, 0x00, 0x06, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0c),
    (0x10, 0x10, 0x12, 0x14, 0x18, 0x14, 0x12, 0x00, 0x00),
    (0x0c, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0e, 0x00, 0x00),
    (0x00, 0x00, 0x1a, 0x15, 0x15, 0x15, 0x15, 0x00, 0x00),
    (0x00, 0x00, 0x1e, 0x11, 0x11, 0x11, 0x11, 0x00, 0x00),
    (0x00, 0x00, 0x0e, 0x11, 0x11, 0x11, 0x0e, 0x00, 0x00),
    (0x00, 0x00, 0x1e, 0x11, 0x11, 0x11, 0x1e, 0x10, 0x10),
    (0x00, 0x00, 0x0f, 0x11, 0x11, 0x11, 0x0f, 0x01, 0x01),
    (0x00, 0x00, 0x16, 0x19, 0x10, 0x10, 0x10, 0x00, 0x00),
    (0x00, 0x00, 0x0f, 0x10, 0x0e, 0x01, 0x1e, 0x00, 0x00),
    (0x00, 0x08, 0x1e, 0x08, 0x08, 0x08, 0x06, 0x00, 0x00),
    (0x00, 0x00, 0x11, 0x11, 0x11, 0x11, 0x0f, 0x00, 0x00),
    (0x00, 0x00, 0x11, 0x11, 0x11, 0x0a, 0x04, 0x00, 0x00),
    (0x00, 0x00, 0x11, 0x11, 0x15, 0x15, 0x0a, 0x00, 0x00),
    (0x00, 0x00, 0x11, 0x0a, 0x04, 0x0a, 0x11, 0x00, 0x00),
    (0x00, 0x00, 0x11, 0x11, 0x11, 0x0f, 0x01, 0x11, 0x0e),
    (0x00, 0x00, 0x1f, 0x02, 0x04, 0x08, 0x1f, 0x00, 0x00),
    (0x06, 0x08, 0x08, 0x10, 0x08, 0x08, 0x06, 0x00, 0x00),
    (0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    (0x0c, 0x02, 0x02, 0x01, 0x02, 0x02, 0x0c, 0x00, 0x00),
    (0x00, 0x00, 0x0d, 0x16, 0x00, 0x00, 0x00, 0x00, 0x00),
    (0x04, 0x04, 0x1f, 0x0e, 0x0e, 0x1b, 0x11, 0x00, 0x00),
    (0x00, 0x00, 0x04, 0x0e, 0x1f, 0x00, 0x00, 0x00, 0x00),
    (0x00, 0x00, 0x1f, 0x0e, 0x04, 0x00, 0x00, 0x00, 0x00),
    (0x02, 0x06, 0x0e, 0x1e, 0x0e, 0x06, 0x02, 0x00, 0x00),
    (0x08, 0x0c, 0x0e, 0x0f, 0x0e, 0x0c, 0x08, 0x00, 0x00),
    (0x00, 0x00, 0x0e, 0x0e, 0x0e, 0x00, 0x00, 0x00, 0x00),
)
GLYPH_LEFT, GLYPH_RIGHT = 98, 99
ADV = 6

ICON_DATA = {
    "games": (
        0x00000000, 0x00000000, 0x00000000, 0x0ffffff0,
        0x3555555c, 0xd5555557, 0xd5d557d7, 0xd7f55557,
        0xd5d55f57, 0xe555555b, 0x355aa55c, 0x355ff55c,
        0x3aac3aac, 0x0ff00ff0, 0x00000000, 0x00000000,
    ),
    "recents": (
        0x000c0000, 0x0037fc00, 0x00d55700, 0x0356a5c0,
        0x0d57f970, 0x0eab7e5c, 0x3fff735c, 0xd5c37f57,
        0xd5c3aa57, 0xe5c0ff5b, 0x35c0035c, 0x39700d6c,
        0x0e5ff5b0, 0x039556c0, 0x00eaab00, 0x003ffc00,
    ),
    "favorites": (
        0x00000000, 0x0003c000, 0x000d7000, 0x000d7000,
        0x000d7000, 0x3ff55ffc, 0xe955556b, 0x3e5555bc,
        0x039556c0, 0x00d55700, 0x00d55700, 0x035aa5c0,
        0x036ff9c0, 0x03b00ec0, 0x00c00300, 0x00000000,
    ),
    "tools": (
        0x0ffc3ff0, 0x3557d55c, 0xd557d557, 0xd557d557,
        0xd557d557, 0xd557d557, 0xeaabeaab, 0x3ffc3ffc,
        0x3ffc3ffc, 0xd557d557, 0xd557d557, 0xd557d557,
        0xd557d557, 0xe557d55b, 0x3aabeaac, 0x0ffc3ff0,
    ),
    "settings": (
        0x000ff000, 0x03f96fc0, 0x0d7d7d70, 0x3555555c,
        0x3955556c, 0x3d57d57c, 0xdd5ff577, 0xd57ffd57,
        0xd97ffd67, 0xed5ff57b, 0x3d57d57c, 0x3555555c,
        0x3969696c, 0x0ebd7eb0, 0x03faafc0, 0x000ff000,
    ),
    "power": (
        0x0003c000, 0x000d7000, 0x00cd7300, 0x037d7dc0,
        0x0d7d7d70, 0x35bd7e5c, 0x35cd735c, 0x35cd735c,
        0xd5ceb357, 0xe5c3c35b, 0x35c0035c, 0x35c0035c,
        0x397ffd6c, 0x0e5555b0, 0x03a96ac0, 0x00febf00,
    ),
}


def _glyph(ch):
    o = ord(ch) - 32
    return o if 0 <= o < 95 else 31


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t + 0.5) for i in range(3))


def _c01(v):
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def _out_cubic(p):
    p = _c01(p)
    return 1.0 - (1.0 - p) ** 3


def _out_back(p, c1=1.9):
    p = _c01(p)
    q = p - 1.0
    return 1.0 + (c1 + 1.0) * q * q * q + c1 * q * q


_DITHER = {}


def dither_levels(lw, lh):
    """Row-major bytes of the ordered-dither level (0..5) of the background gradient; cached per size.
    Shared with the themed subclass in menu.py so the per-pixel work is done once, in one tight loop."""
    k = (lw, lh)
    out = _DITHER.get(k)
    if out is None:
        if len(_DITHER) > 4:
            _DITHER.clear()
        bay = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
        den = lw * 0.85 + lh
        buf = bytearray(lw * lh)
        i = 0
        for y in range(lh):
            row = bay[y & 3]
            for x in range(lw):
                f = 1.0 - (x * 0.85 + y) / den * 1.55
                v = (0.0 if f < 0.0 else 1.0 if f > 1.0 else f) * 5.0
                lv = int(v)
                if lv < 5 and (v - lv) * 16.0 > row[x & 3] + 0.5:
                    lv += 1
                buf[i] = lv
                i += 1
        out = _DITHER[k] = bytes(buf)
    return out


SPRING_K, SPRING_C = 784.0, 39.0


class Classic:
    def __init__(self, w, h):
        self.W, self.H = w, h
        self.LH = max(120, h * LW // w)
        self.s = pygame.Surface((LW, self.LH))
        self._gc, self._ic = {}, {}
        self._sc = {}
        self._rc, self._tmps = {}, {}
        self.zoom = {}
        self.t0 = self.last = time.monotonic()
        self.intro, self.intro_speed = None, 1.0
        self._sel = None
        self.cur = None
        self.move_dist, self.trail, self.ghosts = 1.0, [], []
        self.lbl_old, self.lbl_t0, self.lbl_dir = None, -9.0, (0, 0)
        self.kick_t0 = -9.0
        self._spark = (None, 0, 0)
        rnd = random.Random(7)
        self.embers = [[rnd.uniform(0, LW), rnd.uniform(0, self.LH), 0, rnd.uniform(0, 6.28), i % 3]
                       for i in range(30)]
        for e in self.embers:
            e[2] = (4.0, 8.0, 14.0)[e[4]] * rnd.uniform(0.8, 1.25)
        self._bake_bg()

    def replay_intro(self, fast=True):
        self.intro, self.intro_speed = time.monotonic(), 1.6 if fast else 1.0
        self._sel = None

    def _bake_bg(self):
        ramp = ((6, 0, 2), (24, 2, 7), (46, 4, 12), (76, 8, 18), (112, 12, 26), (150, 18, 34))
        lv = dither_levels(LW, self.LH)
        bg = pygame.Surface((LW, self.LH))
        try:
            rgb = bytearray(len(lv) * 3)
            for c in range(3):
                rgb[c::3] = lv.translate(bytes(ramp[min(i, 5)][c] for i in range(256)))
            bg.blit(pygame.image.frombuffer(bytes(rgb), (LW, self.LH), "RGB"), (0, 0))
        except Exception:
            i = 0
            for y in range(self.LH):
                for x in range(LW):
                    bg.set_at((x, y), ramp[lv[i]])
                    i += 1
        self.bg = bg

    def _glyph_surf(self, g, col):
        k = (g, col)
        sf = self._gc.get(k)
        if sf is None:
            sf = pygame.Surface((5, 9), pygame.SRCALPHA)
            for y in range(9):
                for x in range(5):
                    if FONT[g][y] & (0x10 >> x):
                        sf.set_at((x, y), col)
            self._gc[k] = sf
        return sf

    def _icon(self, hid, dim):
        k = (hid, dim)
        sf = self._ic.get(k)
        if sf is None:
            sf = pygame.Surface((16, 16), pygame.SRCALPHA)
            for y, row in enumerate(ICON_DATA[hid]):
                for x in range(16):
                    v = (row >> (30 - 2 * x)) & 3
                    if v:
                        sf.set_at((x, y), TONE[v])
            if dim:
                sf.fill((200, 170, 175, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self._ic[k] = sf
        return sf

    def _icon_s(self, hid, dim, sz):
        """Scaled icon, cached in _ic so a subclass clearing _ic on a theme change drops these too."""
        k = ("s", hid, dim, sz)
        sf = self._ic.get(k)
        if sf is None:
            sf = self._icon(hid, dim)
            if sz != 16:
                sf = pygame.transform.scale(sf, (sz, sz))
            self._ic[k] = sf
        return sf

    def _tmp(self, w, h):
        sf = self._tmps.get((w, h))
        if sf is None:
            sf = self._tmps[(w, h)] = pygame.Surface((w, h), pygame.SRCALPHA)
        sf.fill((0, 0, 0, 0))
        sf.set_alpha(255)
        return sf

    def _text_on(self, sf, *a, **kw):
        real, self.s = self.s, sf
        try:
            self.text(*a, **kw)
        finally:
            self.s = real

    def rect(self, x, y, w, h, col, a=255):
        if w <= 0 or h <= 0 or a <= 0:
            return
        if a >= 255:
            self.s.fill(col, (x, y, w, h))
            return
        k = (w, h, col, a)
        r = self._rc.get(k)
        if r is None:
            if len(self._rc) > 400:
                self._rc.clear()
            r = pygame.Surface((w, h))
            r.fill(col)
            r.set_alpha(a)
            self._rc[k] = r
        self.s.blit(r, (x, y))

    def pbox(self, x, y, w, h, fill, border):
        self.rect(x + 1, y, w - 2, h, border)
        self.rect(x, y + 1, w, h - 2, border)
        self.rect(x + 1, y + 1, w - 2, h - 2, fill)

    def outline(self, x, y, w, h, col, a):
        self.rect(x + 1, y, w - 2, 1, col, a)
        self.rect(x + 1, y + h - 1, w - 2, 1, col, a)
        self.rect(x, y + 1, 1, h - 2, col, a)
        self.rect(x + w - 1, y + 1, 1, h - 2, col, a)

    @staticmethod
    def text_w(t, sc=1):
        return len(t) * ADV * sc

    def _str_surf(self, t, col, sc, bold):
        """One pre-composed surface per (string, colour, scale, bold): a label is a single blit per frame instead of
        a blit (and, when scaled, a transform) per character. Pixel-identical to drawing glyph by glyph."""
        k = (t, col, sc, bold)
        sf = self._sc.get(k)
        if sf is None:
            if len(self._sc) > 600:
                self._sc.clear()
            adv = ADV * sc
            sf = pygame.Surface((len(t) * adv + (1 if bold else 0), 9 * sc), pygame.SRCALPHA)
            gl = {}
            for i, ch in enumerate(t):
                g = _glyph(ch)
                if g == 0:
                    continue
                gs = gl.get(g)
                if gs is None:
                    gs = self._glyph_surf(g, col)
                    if sc != 1:
                        gs = pygame.transform.scale(gs, (5 * sc, 9 * sc))
                    gl[g] = gs
                sf.blit(gs, (i * adv, 0))
                if bold:
                    sf.blit(gs, (i * adv + 1, 0))
            self._sc[k] = sf
        return sf

    def text(self, t, x, y, col=None, sc=1, align=0, bold=False):
        if not t:
            return
        if col is None:
            col = WHITE
        w = len(t) * ADV * sc
        x -= (w // 2 if align == 1 else w if align == 2 else 0)
        self.s.blit(self._str_surf(t, col, sc, bold), (x, y))

    def glyph(self, g, x, y, col):
        self.s.blit(self._glyph_surf(g, col), (x, y))

    def cap(self, x, y, ch):
        self.rect(x + 1, y, 9, 11, WHITE)
        self.rect(x, y + 1, 11, 9, WHITE)
        self.rect(x + 1, y + 9, 9, 2, DIM)
        self.text(ch, x + 3, y + 2, REDM)

    def _embers(self, dt, t):
        LH = self.LH
        for e in self.embers:
            e[1] -= e[2] * dt
            if e[1] < -3:
                e[1], e[0] = LH + 2, random.uniform(0, LW)
            lay = e[4]
            x = int(e[0] + (2 + 1.5 * lay) * math.sin(t * (0.6 + 0.25 * lay) + e[3]))
            y = int(e[1])
            fl = 0.5 + 0.5 * math.sin(t * 5.0 + e[3] * 7.0)
            a = 40 + 28 * lay + int(46 * fl)
            if y < 30:
                a = a * max(0, y) // 30
            col = REDL if lay == 2 and fl > 0.5 else RED
            self.rect(x, y, 2 if lay == 2 else 1, 2 if lay == 2 else 1, col, a // 16 * 16)

    def _header(self, clk, bat, now, oy):
        if int(now) & 1:
            clk = clk.replace(":", " ")
        self.text(clk, 8, 6 + oy)
        if bat:
            pct, status = bat
            chg = status.lower() == "charging"
            low = pct <= 15 and not chg
            fill = REDL if low else WHITE
            bx, by = LW - 8 - 16, 6 + oy
            self.rect(bx, by, 15, 1, WHITE); self.rect(bx, by + 6, 15, 1, WHITE)
            self.rect(bx, by, 1, 7, WHITE); self.rect(bx + 14, by, 1, 7, WHITE)
            self.rect(bx + 15, by + 2, 1, 3, WHITE)
            n = max(1, min(11, 11 * pct // 100))
            if not low or int(now * 3) & 1:
                self.rect(bx + 2, by + 2, n, 3, fill)
            if chg and n < 11 and int(now * 2.5) & 1:
                self.rect(bx + 2 + n, by + 2, 1, 3, REDL)
            if chg:
                bc = RED if int(now * 2) & 1 else REDL
                self.rect(bx + 6, by + 1, 1, 2, bc); self.rect(bx + 5, by + 3, 3, 1, bc)
                self.rect(bx + 7, by + 4, 1, 2, bc)
            self.text("%d%%" % pct, bx - 4, by, WHITE, 1, 2)
        self.rect(0, 19 + oy, LW, 1, REDM)
        self.rect(0, 20 + oy, LW, 1, BLACK)

    def _on_move(self, old, new, cols, nrows, pos, tw, th, gap, rgap, now):
        oc, orow, nc, nr = old % cols, old // cols, new % cols, new // cols
        dc, dr = nc - oc, nr - orow
        wrap_x = cols > 2 and abs(dc) == cols - 1
        wrap_y = nrows > 2 and abs(dr) == nrows - 1
        dx = (-1 if dc > 0 else 1) if wrap_x else (dc > 0) - (dc < 0)
        dy = (-1 if dr > 0 else 1) if wrap_y else (dr > 0) - (dr < 0)
        if dx and dy:
            dy = 0
        self.lbl_dir, self.lbl_t0, self.kick_t0 = (dx, dy), now, now
        tx, ty = pos(new)
        if wrap_x or wrap_y:
            ox, oy = pos(old)
            self.ghosts.append((ox, oy, tw, th, now))
            self.cur[0], self.cur[1] = tx - dx * (tw + gap), ty - dy * (th + rgap)
            self.cur[2], self.cur[3] = dx * 160.0, dy * 160.0
        self.move_dist = max(1.0, math.hypot(tx - self.cur[0], ty - self.cur[1]))

    def draw(self, canvas, items, descs, sel, clk, bat, hints, cols=3):
        """items: [(id, label)]; descs: {id: text}; bat: (pct, status) or None."""
        now = time.monotonic()
        gap_t = now - self.last
        dt = min(0.1, gap_t)
        self.last = now
        if self.intro is None:
            self.intro, self.intro_speed = now, 1.0
        elif gap_t > 0.4:
            self.intro, self.intro_speed, self._sel = now, 1.6, None
        ti = (now - self.intro) * self.intro_speed
        t = now - self.t0
        s, LH = self.s, self.LH

        n = len(items)
        rows = (n + cols - 1) // cols
        gap, rgap, tw = 8, 8, 64
        th = max(30, min(50, (LH - 26 - rgap * (rows - 1) - 6 - 22 - 12 - 25) // rows))
        isz = 32 if th >= 36 else 16
        gx = (LW - (cols * tw + (cols - 1) * gap)) // 2
        content = rows * th + (rows - 1) * rgap + 6 + 22 + 12
        gy = max(26, 21 + (LH - 25 - 21 - content) // 2)
        bw = cols * tw + (cols - 1) * gap
        by = gy + rows * th + (rows - 1) * rgap + 6

        def pos(i):
            return gx + (i % cols) * (tw + gap), gy + (i // cols) * (th + rgap)

        tx, ty = pos(sel)
        if self.cur is None or self._sel is None:
            self.cur = [float(tx), float(ty), 0.0, 0.0]
            self.lbl_old, self.trail, self.ghosts = None, [], []
        elif sel != self._sel:
            self.lbl_old = items[self._sel][1] if self._sel < n else None
            self._on_move(self._sel, sel, cols, rows, pos, tw, th, gap, rgap, now)
        self._sel = sel
        x, y, vx, vy = self.cur
        steps = max(1, int(dt / 0.008) + 1)
        h = dt / steps
        for _ in range(steps):
            vx += ((tx - x) * SPRING_K - vx * SPRING_C) * h
            vy += ((ty - y) * SPRING_K - vy * SPRING_C) * h
            x += vx * h
            y += vy * h
        self.cur = [x, y, vx, vy]
        speed = math.hypot(vx, vy)
        self.trail.append((now, x, y))
        while self.trail and now - self.trail[0][0] > 0.2:
            self.trail.pop(0)

        s.blit(self.bg, (0, 0))
        self._embers(dt, t)
        sy = int((t % 6.0) / 6.0 * (LH + 24)) - 12
        self.rect(0, sy, LW, 2, WHITE, 16)
        self.rect(0, sy + 2, LW, 1, WHITE, 16)

        self._header(clk, bat, now, -int(22 * (1.0 - _out_cubic(ti / 0.30))))

        bob = int(now * 1000 / 380) & 1
        cur_in = _out_back((ti - 0.55) / 0.22, 2.6)
        box_x, box_y = int(x + 0.5), int(y + 0.5)
        rem0 = math.hypot(tx - x, ty - y)
        settled = speed < 60 and rem0 < 1.5
        focus = -1
        if cur_in > 0.0:
            for i in range(n):
                px, py = pos(i)
                ox = max(0.0, min(box_x + tw, px + tw) - max(box_x, px)) / tw
                oy = max(0.0, min(box_y + th, py + th) - max(box_y, py)) / th
                if ox * oy > 0.5:
                    focus = i
                    break
        for i, (hid, _lbl) in enumerate(items):
            if i == focus and settled:
                continue
            p = _out_back((ti - (0.12 + 0.07 * i)) / 0.30)
            if p <= 0.05:
                continue
            px, py = pos(i)
            w2, h2 = max(3, int(tw * p + 0.5)), max(3, int(th * p + 0.5))
            x2, y2 = px + (tw - w2) // 2, py + (th - h2) // 2
            self.rect(x2 + 2, y2 + 2, w2, h2, BLACK, 90)
            self.pbox(x2, y2, w2, h2, PANEL, REDM)
            if p > 0.55:
                sz = isz if p >= 0.999 else max(4, int(isz * min(p, 1.0)) // 2 * 2)
                if i != focus:
                    s.blit(self._icon_s(hid, True, sz), (px + (tw - sz) // 2, py + (th - sz) // 2))

        if cur_in > 0.0:
            rem = math.hypot(tx - x, ty - y)
            arc = int(math.sin(math.pi * _c01(1.0 - rem / self.move_dist)) * 3 + 0.5) if rem > 0.5 else 0
            svx, svy = min(4, int(abs(vx) / 110)), min(3, int(abs(vy) / 110))
            w2, h2 = int((tw + svx) * cur_in + 0.5), int((th + svy) * cur_in + 0.5)
            cx = box_x + tw // 2 - w2 // 2
            cy = box_y + th // 2 - h2 // 2 - 2 - arc
            self.rect(cx + 2, box_y + th // 2 - h2 // 2 + 2, w2, h2, BLACK, 150 if arc == 0 else 105)
            if speed > 140:
                for lag, a in ((0.045, 120), (0.09, 60)):
                    older = [q for q in self.trail if q[0] <= now - lag]
                    if older:
                        q = older[-1]
                        if math.hypot(q[1] - x, q[2] - y) > 5:
                            self.outline(int(q[1] + 0.5), int(q[2] + 0.5) - 2, tw, th, REDL, a)
            for gh in self.ghosts[:]:
                gp = (now - gh[4]) / 0.20
                if gp >= 1.0:
                    self.ghosts.remove(gh)
                    continue
                gw, ghh = max(4, int(gh[2] * (1 - gp))), max(4, int(gh[3] * (1 - gp)))
                self.outline(gh[0] + (gh[2] - gw) // 2, gh[1] + (gh[3] - ghh) // 2 - 2, gw, ghh, WHITE, int(200 * (1 - gp)) // 16 * 16)
            moving = speed > 60 or rem > 1.5
            border = WHITE if moving else _mix(WHITE, REDL, 0.55 * (0.5 + 0.5 * math.sin(t * 5.0)))
            self.pbox(cx, cy, w2, h2, RED, border)
            self.rect(cx + 3, cy + 2, w2 - 6, 1, REDL)
            if not moving and cur_in >= 1.0:
                ph = (t % 2.8) / 0.55
                if ph < 1.0:
                    sx0 = cx - 6 + int(ph * (w2 + 12))
                    for r in range(2, h2 - 2):
                        a0, b0 = max(sx0 - r // 2, cx + 2), min(sx0 - r // 2 + 3, cx + w2 - 2)
                        if b0 > a0:
                            self.rect(a0, cy + r, b0 - a0, 1, WHITE, 64)
                bk = int(t / 0.85)
                if self._spark[0] != bk:
                    rr = random.Random(bk * 7 + 3)
                    self._spark = (bk, rr.randrange(8, max(9, w2 - 8)), rr.randrange(6, max(7, h2 - 6)))
                sp = (t % 0.85) / 0.85
                spx, spy = cx + self._spark[1], cy + self._spark[2]
                if sp < 0.15 or 0.35 <= sp < 0.55:
                    self.rect(spx, spy, 1, 1, WHITE)
                elif sp < 0.35:
                    self.rect(spx - 1, spy, 3, 1, WHITE); self.rect(spx, spy - 1, 1, 3, WHITE)
            if focus >= 0 and cur_in > 0.6:
                sz = isz
                s.blit(self._icon_s(items[focus][0], False, sz),
                       (cx + (w2 - sz) // 2, cy + (h2 - sz) // 2 - (0 if moving else bob)))

        bar_e = _out_cubic((ti - 0.45) / 0.30)
        wl = int(bw * bar_e)
        if wl >= 4:
            bx0 = gx + (bw - wl) // 2
            self.rect(bx0 + 2, by + 2, wl, 22, BLACK, 120)
            self.pbox(bx0, by, wl, 22, REDM, REDL)
        hid, lbl = items[sel]
        if bar_e >= 1.0:
            dx, dy = self.lbl_dir
            p = _c01((now - self.lbl_t0) / 0.30)
            lw_ = bw - 28
            sf = self._tmp(lw_, 20)
            mid = lw_ // 2
            nx = ny = 0
            if p < 1.0 and self.lbl_old is not None:
                q1 = _c01(p / 0.45)
                q2 = _out_cubic((p - 0.40) / 0.60)
                dist_x, dist_y = mid + 62, 20
                if p < 0.45:
                    self._text_on(sf, self.lbl_old, mid + int(-dx * dist_x * q1 * q1), 1 + int(-dy * dist_y * q1 * q1), WHITE, 2, 1, True)
                if p > 0.40:
                    nx, ny = int(dx * dist_x * (1 - q2)), int(dy * dist_y * (1 - q2))
                    self._text_on(sf, lbl, mid + nx, 1 + ny, WHITE, 2, 1, True)
            else:
                self._text_on(sf, lbl, mid, 1, WHITE, 2, 1, True)
            s.blit(sf, (gx + 14, by + 1))
            kp = max(0.0, 1.0 - (now - self.kick_t0) / 0.20)
            kk = int(3 * kp + 0.5)
            lcol = WHITE if kp > 0 else REDL
            self.glyph(GLYPH_LEFT, gx + 6 - bob - (kk if dx < 0 else 0), by + 7, lcol if dx <= 0 else REDL)
            self.glyph(GLYPH_RIGHT, gx + bw - 11 + bob + (kk if dx > 0 else 0), by + 7, lcol if dx >= 0 else REDL)
            ed = _out_cubic((now - self.lbl_t0 - 0.18) / 0.22) if self.lbl_old is not None else _out_cubic((ti - 0.75) / 0.25)
            d = descs.get(hid, "")[:bw // ADV]
            if ed > 0.0:
                sf2 = self._tmp(bw, 10)
                self._text_on(sf2, d, bw // 2, 0, DIM, 1, 1)
                sf2.set_alpha(int(255 * ed) // 16 * 16 if ed < 1 else 255)
                s.blit(sf2, (gx, by + 24 + int(3 * (1 - ed))))

        fo = int(22 * (1.0 - _out_cubic((ti - 0.30) / 0.30)))
        fy = LH - 8 - 11 + fo
        self.rect(0, fy - 6, LW, LH - fy + 6, BLACK, 90)
        self.rect(0, fy - 6, LW, 1, REDM)
        hx = 8
        for g, lab in hints:
            self.cap(hx, fy, g)
            self.text(lab, hx + 15, fy + 2)
            hx += 15 + self.text_w(lab) + 10

        if ti < 0.4:
            self.rect(0, 0, LW, LH, (0, 0, 0), int(255 * (1.0 - ti / 0.4)) // 17 * 17)

        if (self.W, self.H) == (LW, LH):
            canvas.blit(s, (0, 0))
        else:
            pygame.transform.scale(s, (self.W, self.H), canvas)
