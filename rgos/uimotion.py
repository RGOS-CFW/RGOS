"""Motion for the first-boot installer, ported from the RG OS launcher (menu.py) so both look and feel the same.

What is here, and where it comes from in menu.py:
  * easing and the damped spring        _out_cubic / _out_back / _smooth_damp, SPRING_K / SPRING_C (rgclassic.py)
  * eased 3D buttons that lift          draw_button / _btn_face
  * staggered entrance                  home_intro and the tile loop of the home screen
  * spring focus ring                   _ring_step / _ring_surf / _draw_ring
  * drifting embers                     home_embers
  * diagonal shine sweep on the focus   _shine_surf
  * fade between screens and popups     _VT (the "fade" kind)

menu.py imports pygame and half the system at import time, so it cannot be imported by the installer, which runs before there
is anything on the card. This module takes pygame as an argument and imports nothing heavy; the constants are copied and a test
(tests/test_installer.py) checks they still match rgclassic.py.

One Motion object belongs to one screen loop. Call tick() once per frame; it says whether the last frame had something moving
(then the loop should run at full rate) or was at rest (then it can drop to the idle rate).
"""
import math
import random
import time

SPRING_K, SPRING_C = 784.0, 39.0     # ~28 rad/s, damping ratio 0.7 -> ~5% overshoot (rgclassic.SPRING_K / SPRING_C)
ANIM_STEPS, ANIM_SPEED, LIFT_PX = 24, 16.0, 4
INTRO_S = 1.0                        # the entrance of a screen takes about this long (menu.HOME_INTRO_S)
FADE_S = 0.18                        # popup / screen crossfade (menu._VT "fade")
SHINE_EVERY, SHINE_SWEEP = 2.8, 0.7  # a shine sweeps the focused tile for SHINE_SWEEP seconds every SHINE_EVERY


def c01(v):
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def out_cubic(p):
    p = c01(p)
    return 1.0 - (1.0 - p) ** 3


def out_back(p, c1=1.9):
    p = c01(p)
    q = p - 1.0
    return 1.0 + (c1 + 1.0) * q * q * q + c1 * q * q


def mix(a, b, t):
    """Blend colour a toward b by t (the launcher's later, truncating _mix, which is the one its buttons use)."""
    return tuple(max(0, min(255, int(a[i] + (b[i] - a[i]) * t))) for i in range(3))


def smooth_damp(pos, vel, target, dt, omega=22.0):
    """Critically damped glide of pos toward target (no overshoot); snaps when close enough to be at rest."""
    e = math.exp(-omega * dt)
    err = pos - target
    tmp = (vel + omega * err) * dt
    vel = (vel - omega * tmp) * e
    pos = target + (err + tmp) * e
    if abs(pos - target) < 0.002 and abs(vel) < 0.02:
        return float(target), 0.0
    return pos, vel


class Motion:
    """Animation state and drawing helpers for one screen loop. `colors` needs BG, PANEL, SEL_BG, ACCENT, TEXT and DIM.

    settled=True starts every entrance already finished (for a single static draw, e.g. in tests).
    """

    def __init__(self, pg, size, colors, settled=False, clock=time.monotonic):
        self.pg, self.size, self.c, self.settled, self.clock = pg, tuple(size), colors, settled, clock
        self.now = clock()
        self.dt = 1 / 30
        self.moving = False
        self._flag = False
        self.av = {}                 # key -> [value, velocity, last drawn]
        self.btn = {}                # key -> [highlight 0..1, base while selected, base while not]
        self.seen = {}               # key -> [entrance start, last drawn]
        self.marks = {}              # key -> [value, when it last changed]
        self.ring = {"p": None, "v": [0.0, 0.0]}
        self.embers = None
        self._faces, self._shadows, self._rings, self._shines, self._masks = {}, {}, {}, {}, {}
        self.vt = {"key": None, "t0": 0.0, "dur": 0.0, "bufs": None}

    # ---- the clock ----------------------------------------------------------------------------------------------
    def tick(self, now=None):
        """Start a frame. Returns True if something was moving in the previous one (run at full frame rate)."""
        now = self.clock() if now is None else now
        self.dt = min(0.05, max(0.001, now - self.now))
        self.now = now
        moving, self._flag = self._flag, False
        self.moving = moving
        return moving

    def busy(self):
        """Ask for full frame rate for the next frame."""
        self._flag = True

    def val(self, key, target, omega=20.0):
        """Glide a number toward target (menu.anim_val). Snaps on first use or when not asked for in a while."""
        st = self.av.get(key)
        if st is None or self.now - st[2] > 0.4:
            st = self.av[key] = [float(target), 0.0, self.now]
        st[2] = self.now
        st[0], st[1] = smooth_damp(st[0], st[1], target, self.dt, omega)
        if st[0] != target:
            self._flag = True
        return st[0]

    def since(self, key, span=INTRO_S, reset_ring=False):
        """Seconds since screen `key` started its entrance. It starts over when the screen was not drawn for a moment, so a
        popup replays its entrance every time it opens and the welcome screen replays when it comes back. reset_ring puts the
        focus ring back on its tile at the start (menu.home_intro does that for the home screen)."""
        st = self.seen.get(key)
        if st is None or self.now - st[1] > 0.3:
            st = self.seen[key] = [self.now - (1e9 if self.settled else 0.0), self.now]
            if reset_ring:
                self.ring["p"] = None
        st[1] = self.now
        el = self.now - st[0]
        if el < span + 0.6:
            self._flag = True
        return el

    def changed(self, key, value, span=0.3):
        """Seconds since `value` (e.g. the selected tile) last changed under `key`; it counts from the first call, so a
        caption fades up when its screen first appears as well as after every move (menu: _HOME_FX["sel_t"])."""
        st = self.marks.get(key)
        if st is None or st[0] != value:
            st = self.marks[key] = [value, self.now - (1e9 if self.settled else 0.0)]
        el = self.now - st[1]
        if el < span:
            self._flag = True
        return el

    # ---- buttons -------------------------------------------------------------------------------------------------
    def _face(self, w, h, base, radius):
        key = (w, h, base, radius)
        surf = self._faces.get(key)
        if surf is None:
            pg = self.pg
            if len(self._faces) > 600:
                self._faces.clear()
            top, bot = mix(base, (255, 255, 255), 0.16), mix(base, (0, 0, 0), 0.12)
            surf = pg.Surface((w, h), pg.SRCALPHA)
            for yy in range(h):
                pg.draw.line(surf, mix(top, bot, yy / max(1, h - 1)), (0, yy), (w, yy))
            pg.draw.line(surf, mix(base, (255, 255, 255), 0.35), (radius, 1), (w - radius - 1, 1))
            surf.blit(self._mask(w, h, radius), (0, 0), special_flags=pg.BLEND_RGBA_MIN)
            self._faces[key] = surf
        return surf

    def _mask(self, w, h, radius):
        key = (w, h, radius)
        m = self._masks.get(key)
        if m is None:
            pg = self.pg
            if len(self._masks) > 100:
                self._masks.clear()
            m = pg.Surface((w, h), pg.SRCALPHA)
            pg.draw.rect(m, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
            self._masks[key] = m
        return m

    def button(self, surf, rect, base, radius=12, depth=4, sel=False, key=None, border=True):
        """The launcher's button (menu.draw_button): a gradient face on a darker side, a soft shadow, the colour and the lift
        easing toward the selected look. Returns (highlight 0..1, lift in px); the caller draws its content at y - lift."""
        pg = self.pg
        x, y, w, h = rect
        bk = rect if key is None else key
        st = self.btn.get(bk)
        if st is None:
            if len(self.btn) > 300:
                self.btn.clear()
            st = self.btn[bk] = [1.0 if sel else 0.0, base, base]
        st[1 if sel else 2] = base
        target = 1.0 if sel else 0.0
        if abs(st[0] - target) < 0.002:
            st[0] = target
        else:
            st[0] += (target - st[0]) * (1.0 - math.exp(-self.dt * ANIM_SPEED))
            self._flag = True
        e = st[0] * st[0] * (3.0 - 2.0 * st[0])
        hl = round(e * ANIM_STEPS) / ANIM_STEPS
        base = mix(st[2], st[1], hl)
        lift = int(round(LIFT_PX * hl)) if h >= 80 else 0
        y -= lift
        side = mix(base, (0, 0, 0), 0.55)
        skey = (w, h, depth, radius)
        sh = self._shadows.get(skey)
        if sh is None:
            if len(self._shadows) > 200:
                self._shadows.clear()
            sh = self._shadows[skey] = pg.Surface((w, h + depth + 3), pg.SRCALPHA)
            pg.draw.rect(sh, (0, 0, 0, 70), (0, 3, w, h + depth), border_radius=radius)
        surf.blit(sh, (x, y + lift))
        pg.draw.rect(surf, side, (x, y + depth, w, h), border_radius=radius)
        surf.blit(self._face(w, h, base, radius), (x, y))
        if hl > 0 and border:
            pg.draw.rect(surf, mix(base, self.c["ACCENT"], hl), (x, y, w, h), 2 if h < 80 else 3, border_radius=radius)
        return hl, lift

    def shine(self, surf, rect, radius, hl):
        """A faint diagonal highlight sweeping across a focused, resting tile now and then (the launcher's _shine_surf)."""
        if hl < 0.999:
            return
        ph = (self.now % SHINE_EVERY) / SHINE_SWEEP
        if ph >= 1.0:
            return
        self._flag = True
        pg = self.pg
        x, y, w, h = rect
        sw = h + 22
        s = self._shines.get(h)
        if s is None:
            if len(self._shines) > 16:
                self._shines.clear()
            s = self._shines[h] = pg.Surface((sw, h), pg.SRCALPHA)
            for r in range(h):
                pg.draw.line(s, (255, 255, 255, 56), (h - r, r), (h - r + 18, r))
        tmp = pg.Surface((w, h), pg.SRCALPHA)
        tmp.blit(s, (int((w + sw) * out_cubic(ph)) - sw, 0))
        tmp.blit(self._mask(w, h, radius), (0, 0), special_flags=pg.BLEND_RGBA_MIN)
        surf.blit(tmp, (x, y))

    # ---- the focus ring ------------------------------------------------------------------------------------------
    def ring_step(self, tx, ty):
        """Damped spring glide of the focus ring to (tx, ty) (menu._ring_step). Integrated in steps of at most 8 ms so a long
        frame cannot make it unstable. Returns (speed, distance left)."""
        st = self.ring
        if st["p"] is None:
            st["p"], st["v"] = [float(tx), float(ty)], [0.0, 0.0]
        p, v = st["p"], st["v"]
        steps = max(1, int(self.dt / 0.008) + 1)
        h = self.dt / steps
        for _ in range(steps):
            for a, g in ((0, tx), (1, ty)):
                v[a] += ((g - p[a]) * SPRING_K - v[a] * SPRING_C) * h
                p[a] += v[a] * h
        if math.hypot(tx - p[0], ty - p[1]) < 0.002 and math.hypot(v[0], v[1]) < 0.02:
            p[0], p[1], v[0], v[1] = float(tx), float(ty), 0.0, 0.0    # settled: snap so the loop can go idle
        rem, speed = math.hypot(tx - p[0], ty - p[1]), math.hypot(v[0], v[1])
        if rem > 0.0 or speed > 0.0:
            self._flag = True
        return speed, rem

    def draw_ring(self, c, bw, bh, cur_in, speed, rem, radius=18):
        """The focus ring: glides between tiles and breathes softly when resting (menu._draw_ring)."""
        if cur_in <= 0.05 or self.ring["p"] is None:
            return
        pg = self.pg
        key = (bw, bh, radius, tuple(self.c["ACCENT"][:3]))
        s = self._rings.get(key)
        if s is None:
            if len(self._rings) > 48:
                self._rings.clear()
            col = tuple(self.c["ACCENT"][:3])
            s = self._rings[key] = pg.Surface((bw + 12, bh + 12), pg.SRCALPHA)
            pg.draw.rect(s, col + (64,), (0, 0, bw + 12, bh + 12), 5, border_radius=radius + 6)
            pg.draw.rect(s, col + (255,), (6, 6, bw, bh), 3, border_radius=radius)
        a = 255 if (speed > 60 or rem > 1.5) else 215 + 40 * math.sin(self.now * 3.0)
        s.set_alpha(max(0, min(255, int(a * min(1.0, cur_in)))))
        x, y = self.ring["p"]
        c.blit(s, (int(x + 0.5) - 6, int(y + 0.5) - 6))

    # ---- embers --------------------------------------------------------------------------------------------------
    def draw_embers(self, c):
        """Three layers of slow embers in the accent colour drifting up behind everything (menu.home_embers)."""
        pg = self.pg
        W, H = self.size
        u = max(1, W // 320)
        if self.embers is None:
            r = random.Random(7)
            self.embers = [[r.uniform(0, W), r.uniform(0, H), r.uniform(10, 26), r.uniform(0, 6.28), i % 3] for i in range(30)]
        top = H * 0.2
        for e in self.embers:
            lay = e[4]
            e[1] -= e[2] * (0.6 + 0.4 * lay) * self.dt * u * 0.6
            if e[1] < -4:
                e[1], e[0] = H + 4.0, random.uniform(0, W)
            x = int(e[0] + (2 + 1.5 * lay) * math.sin(self.now * (0.6 + 0.25 * lay) + e[3]))
            y = int(e[1])
            k = 0.16 + 0.12 * lay + 0.22 * (0.5 + 0.5 * math.sin(self.now * 4.0 + e[3] * 7.0))
            if y < top:
                k *= max(0.0, y) / top
            if k > 0.03:
                sz = u * (2 if lay == 2 else 1)
                pg.draw.rect(c, mix(self.c["BG"], self.c["ACCENT"], min(1.0, k)), (x, y, sz, sz))

    # ---- entrance of a tile --------------------------------------------------------------------------------------
    def pop(self, canvas, rect, p, paint):
        """Entrance of one tile: it glides up 28 px and fades in. `paint(surf, x, y)` draws it with its top left at x, y;
        p is the progress 0..1 (menu: out_cubic((el - 0.05 - 0.06 * i) / 0.42))."""
        pg = self.pg
        bx, by, bw, bh = rect
        if p >= 0.999:
            paint(canvas, bx, by)
        elif p > 0.02:
            tmp = pg.Surface((bw + 12, bh + 30), pg.SRCALPHA)
            paint(tmp, 6, 14)
            tmp.set_alpha(int(255 * p))
            canvas.blit(tmp, (bx - 6, by - 14 + int((1.0 - p) * 28)))

    # ---- fade between screens ------------------------------------------------------------------------------------
    def transition(self, canvas, key, dur=FADE_S):
        """Call at the end of every frame with the screen's name. When the name changes, the old screen fades into the new
        one (menu._VT "fade"), so opening or closing a popup, or going on to the install console, never jumps."""
        pg, vt = self.pg, self.vt
        if vt["bufs"] is None:
            vt["bufs"] = tuple(pg.Surface(self.size) for _ in range(3))     # last frame, previous screen, this frame
        buf, old, new = vt["bufs"]
        if vt["key"] is None:
            vt["key"] = key
        elif key != vt["key"]:
            old.blit(buf, (0, 0))
            vt["t0"], vt["dur"], vt["key"] = self.now, dur, key
        p = (self.now - vt["t0"]) / vt["dur"] if vt["dur"] else 1.0
        buf.blit(canvas, (0, 0))
        if 0.0 <= p < 1.0:
            self._flag = True
            new.blit(canvas, (0, 0))
            old.set_alpha(255)
            canvas.blit(old, (0, 0))
            new.set_alpha(int(255 * out_cubic(p)))
            canvas.blit(new, (0, 0))
