#!/usr/bin/env python3
"""Render the startup splash natively for the H700 consoles (no letterbox bars).

The old files were the 16:9 animation letterboxed inside the screen.  This redraws it at the
exact menu canvas size of each device (see CANVAS in rgos/menu.py), so every frame is blitted
1:1 and fills the whole screen, the same way tools/render-splash-rotate.py does for the Rotate.

    rg34xxsp  720x480  (3:2)   logo on one row, RG OS
    rg35xxh   720x540  (4:3)   logo stacked, RG over OS (same file is used for rg35xxsp)

Same palette, same timeline (6 s @ 24 fps, 144 frames) so splash.wav still lines up.

usage: python3 tools/render-splash.py <rg34xxsp|rg35xxh> [out.mjpg] [frames_dir]
needs: Pillow, numpy, scipy, ffmpeg, DejaVu Sans Mono
"""
import math, os, random, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter

DEVICES = {
    "rg34xxsp": (720, 480, "row", 24, 1.00),
    "rg35xxh": (720, 540, "stack", 24, 1.07),
}
DEVICE = sys.argv[1] if len(sys.argv) > 1 else "rg35xxh"
if DEVICE not in DEVICES:
    sys.exit("unknown device %r (use one of: %s)" % (DEVICE, ", ".join(DEVICES)))
SW, SH, LAYOUT, PITCH, FS = DEVICES[DEVICE]
FPS = 24
NFRAMES = 144
OUT = sys.argv[2] if len(sys.argv) > 2 else "splash-%s.mjpg" % DEVICE
FRAMES_DIR = sys.argv[3] if len(sys.argv) > 3 else None

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

GLYPH = {
    "R": ["XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"],
    "G": [".XXX.", "X...X", "X....", "X.XXX", "X...X", "X...X", ".XXX."],
    "O": [".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "S": [".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."],
}

K = PITCH / 30.0
CELL = PITCH - 4

if LAYOUT == "row":
    PLACE = [(0, 0, 0), (1, 0, 6), (2, 0, 14), (3, 0, 20)]
    COLS, ROWS_N = 25, 7
else:
    PLACE = [(0, 0, 0), (1, 0, 6), (2, 1, 0), (3, 1, 6)]
    COLS, ROWS_N = 11, 15
LETTERS = "RGOS"
ROW_Y = {0: 0, 1: 8}

LOGO_W = COLS * PITCH - (PITCH - CELL)
LOGO_H = ROWS_N * PITCH - (PITCH - CELL)
LOGO_X = (SW - LOGO_W) // 2

TAG = "EMULATION FIRMWARE FOR RETRO HANDHELDS"
TAG_GAP, BAR_GAP = 54, 32
BAR_W, BAR_H = (400 if LAYOUT == "row" else 360), 14
BAR_CELLS = 24
BLOCK_H = LOGO_H + TAG_GAP + BAR_GAP + BAR_H
LOGO_Y = max(70, (SH - BLOCK_H) // 2 - SH // 40)
TAG_Y = LOGO_Y + LOGO_H + TAG_GAP
BAR_X, BAR_Y = (SW - BAR_W) // 2, TAG_Y + BAR_GAP

LOG = [
    ("RG OS bootloader v1.0", None, 0.50),
    ("Initializing display", "OK", 0.72),
    ("Mounting /roms", "OK", 0.95),
    ("Loading emulator cores", "OK", 1.18),
    ("Starting input daemon", "OK", 1.40),
    ("Ready", "OK", 1.55),
]

CYAN = np.array([0, 255, 255], float)
WHITE = np.array([232, 205, 255], float)
MAG = np.array([255, 70, 255], float)


def grad(t):
    t = min(1.0, max(0.0, t))
    if t < 0.5:
        return CYAN + (WHITE - CYAN) * (t / 0.5)
    return WHITE + (MAG - WHITE) * ((t - 0.5) / 0.5)


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


yy, xx = np.mgrid[0:SH, 0:SW].astype(np.float32)
r = np.hypot(xx - SW / 2, yy - SH * 0.47) / (max(SW, SH) * 0.72)
BG = np.zeros((SH, SW, 3), np.float32)
BG[..., 0] = 10 - 9 * r
BG[..., 1] = 17 - 15 * r
BG[..., 2] = 35 - 31 * r
BG = np.clip(BG, 0, None)
grid = ((xx % 36 == 0) | (yy % 36 == 0)).astype(np.float32)
BG += grid[..., None] * np.array([2.0, 3.0, 6.0], np.float32) * np.clip(1.2 - r, 0, 1)[..., None]

SCAN = np.ones((SH, SW, 1), np.float32)
SCAN[1::3] = 0.93

cells = []
idx_map = -np.ones((SH, SW), np.int32)
rng = random.Random(7)
for letter, row, col0 in PLACE:
    for gy, line in enumerate(GLYPH[LETTERS[letter]]):
        for gx, c in enumerate(line):
            if c != "X":
                continue
            cx = LOGO_X + (col0 + gx) * PITCH
            cy = LOGO_Y + (ROW_Y[row] + gy) * PITCH
            t = (letter + gx / 4.0) / 4.0
            col = grad(t)
            reveal = 1.85 + letter * 0.20 + rng.random() * 0.45
            cells.append((cx, cy, col, letter, gx, gy, reveal, rng.random()))
            idx_map[cy:cy + CELL, cx:cx + CELL] = len(cells) - 1

N = len(cells)
CELL_COL = np.array([c[2] for c in cells], np.float32)
CELL_REVEAL = np.array([c[6] for c in cells], np.float32)
CELL_RAND = np.array([c[7] for c in cells], np.float32)
CELL_X = np.array([c[0] + CELL / 2 for c in cells], np.float32)
CELL_Y = np.array([c[1] + CELL / 2 for c in cells], np.float32)

shade = np.ones((SH, SW), np.float32)
inside = idx_map >= 0
ly = (yy - LOGO_Y) % PITCH
shade[inside & (ly < 2)] = 1.12
shade[inside & (ly > CELL - 3)] = 0.9
shade = shade[..., None]

F_LOG = ImageFont.truetype(MONO, round(15 * FS))
F_TAG = ImageFont.truetype(MONO, round(16 * FS))
F_VER = ImageFont.truetype(MONO, 12)
CH = F_LOG.getlength("M")


def text_layer(draw_fn):
    im = Image.new("RGB", (SW, SH), (0, 0, 0))
    draw_fn(ImageDraw.Draw(im))
    return np.asarray(im, np.float32)


def draw_log(d, t):
    y = 26
    lh = round(22 * FS)
    for text, tag, t0 in LOG:
        if t < t0:
            break
        k = min(1.0, (t - t0) / 0.18)
        shown = text[: int(len(text) * k + 0.999)]
        if tag is None:
            d.text((28, y), shown, font=F_LOG, fill=(70, 90, 100))
        else:
            d.text((28, y), "[", font=F_LOG, fill=(80, 100, 105))
            d.text((28 + CH * 2, y), tag, font=F_LOG, fill=(70, 200, 120))
            d.text((28 + CH * 5, y), "]", font=F_LOG, fill=(80, 100, 105))
            d.text((28 + CH * 7, y), shown, font=F_LOG, fill=(80, 170, 120))
        y += lh


def draw_tag(d, t):
    if t < 3.3:
        return
    k = min(1.0, (t - 3.3) / 1.1)
    n = int(round(len(TAG) * k))
    w = d.textlength(TAG, font=F_TAG)
    x0 = (SW - w) / 2
    d.text((x0, TAG_Y), TAG[:n], font=F_TAG, fill=(196, 208, 236))
    if k < 1.0 or (t - 4.4) < 0.5 and int(t * 4) % 2 == 0:
        cx = x0 + d.textlength(TAG[:n], font=F_TAG)
        d.rectangle([cx + 1, TAG_Y + 1, cx + 8, TAG_Y + round(17 * FS)], fill=(230, 235, 255))


def draw_bar(d, t):
    if t < 3.5:
        return
    d.rectangle([BAR_X, BAR_Y, BAR_X + BAR_W, BAR_Y + BAR_H], outline=(60, 72, 112))
    p = smooth((t - 3.5) / 1.3)
    n = int(round(BAR_CELLS * p))
    cw = (BAR_W - 6) / BAR_CELLS
    for i in range(n):
        c = CYAN * 0.85 + (MAG - CYAN * 0.85) * (i / (BAR_CELLS - 1))
        x = BAR_X + 3 + i * cw
        d.rectangle([x, BAR_Y + 3, x + cw - 3, BAR_Y + BAR_H - 3], fill=tuple(int(v) for v in c))


def frame(n):
    t = n / FPS
    img = BG * smooth(t / 0.3)

    if 0.04 < t < 0.30:
        k = (t - 0.04) / 0.26
        h = max(1, int(2 + 40 * smooth(k)))
        a = (1 - k) ** 1.5
        y0 = SH // 2 - h // 2
        img[y0:y0 + h] += (np.array([120, 180, 255], np.float32) * a * 0.5)

    fade = 1.0 - smooth((t - 5.33) / 0.5)

    if 0.5 <= t < 1.83:
        lg = text_layer(lambda d: draw_log(d, t))
        out = 1.0 - smooth((t - 1.68) / 0.15)
        img = img + lg * out

    lt = t - 0.0
    alpha = np.zeros(N, np.float32)
    pop = np.zeros(N, np.float32)
    for i in range(N):
        dt = lt - CELL_REVEAL[i]
        if dt < 0:
            continue
        if dt < 0.22:
            f = (math.sin((dt * 60 + CELL_RAND[i] * 30)) > -0.2 + dt * 3)
            alpha[i] = 0.45 if f else 0.0
            pop[i] = 0.9 * (1 - dt / 0.22)
        else:
            alpha[i] = 1.0
            pop[i] = 0.35 * max(0.0, 1 - (dt - 0.22) / 0.3)

    sheen = np.zeros(N, np.float32)
    if 3.35 <= t <= 3.85:
        k = (t - 3.35) / 0.5
        pos = -150 + k * (LOGO_W + LOGO_H * 0.6 + 300)
        d = (CELL_X - LOGO_X) + (CELL_Y - LOGO_Y) * 0.6 - pos
        sheen = np.exp(-(d / (90.0 * K)) ** 2).astype(np.float32) * 0.85

    breathe = 0.96 + 0.04 * math.sin(t * 2 * math.pi * 0.8) if t > 3.2 else 1.0

    cell_rgb = CELL_COL * (1 - np.clip(pop + sheen, 0, 1)[:, None]) + 255.0 * np.clip(pop + sheen, 0, 1)[:, None]
    cell_rgb = cell_rgb * (alpha * breathe)[:, None]
    safe = np.where(idx_map >= 0, idx_map, 0)
    logo = cell_rgb[safe] * inside[..., None] * shade
    if alpha.any():
        g1 = gaussian_filter(logo, sigma=(9 * K, 9 * K, 0))
        g2 = gaussian_filter(logo, sigma=(28 * K, 28 * K, 0))
        img = img + logo * 0.92 + g1 * 0.95 + g2 * 0.85

    if t >= 3.3:
        tb = text_layer(lambda d: (draw_tag(d, t), draw_bar(d, t)))
        img = img + tb
        img = img + gaussian_filter(tb, sigma=(6, 6, 0)) * 0.25

    if t > 3.4:
        vv = text_layer(lambda d: d.text((SW - 50, SH - 28), "v1.0", font=F_VER, fill=(70, 82, 105)))
        img = img + vv * 0.8

    img = img * SCAN * fade
    img = np.clip(img, 0, 255)
    return Image.fromarray(img.astype(np.uint8))


def main():
    if FRAMES_DIR:
        os.makedirs(FRAMES_DIR, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
           "-c:v", "mjpeg", "-q:v", "3", "-pix_fmt", "yuvj420p", "-f", "mjpeg", OUT]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(NFRAMES):
        im = frame(n)
        if FRAMES_DIR:
            im.save(os.path.join(FRAMES_DIR, "n%03d.png" % n))
        im.save(p.stdin, "PNG")
    p.stdin.close()
    p.wait()


if __name__ == "__main__":
    main()
