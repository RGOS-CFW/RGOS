#!/usr/bin/env python3
"""Render the per-device boot logos (bootlogo/bootlogo-<device>.bmp) from bootlogo/rgos-logo.png.

The logo tile is centred at native panel size on a gradient fitted to the tile's own background, so the
rounded tile edge disappears into the panel. Output is a plain 24-bit uncompressed BMP, which is what
U-Boot's bmp loader accepts.

usage: python3 tools/render-bootlogo.py          (needs Pillow and numpy)
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "bootlogo", "rgos-logo.png")
SIZES = {"rg34xxsp": (720, 480), "rg35xxh": (640, 480), "rg35xxsp": (640, 480), "rg-rotate": (720, 720), "miniloong": (960, 720)}
FEATHER = 0.16
FILL = 0.84


def basis(u, v):
    return np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=-1)


def fit_gradient(tile):
    """Quadratic surface per channel over the opaque outer ring of the tile (nothing but background there)."""
    a = np.asarray(tile, dtype=np.float64)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    ring = ((xx < 12) | (yy < 12) | (xx >= w - 12) | (yy >= h - 12)) & (a[..., 3] == 255)
    u, v = xx[ring] / w, yy[ring] / h
    coefs, _, _, _ = np.linalg.lstsq(basis(u, v), a[ring][:, :3], rcond=None)
    err = np.abs(basis(u, v) @ coefs - a[ring][:, :3]).max()
    print("gradient fit: max error %.1f / 255 on %d ring pixels" % (err, ring.sum()))
    return coefs


def render(tile, coefs, size):
    cw, ch = size
    th = round(min(cw, ch) * FILL)
    ox, oy = (cw - th) // 2, (ch - th) // 2
    yy, xx = np.mgrid[0:ch, 0:cw]
    u, v = np.clip((xx - ox) / th, -0.25, 1.25), np.clip((yy - oy) / th, -0.25, 1.25)
    bg = np.clip(basis(u, v) @ coefs, 0, 255).round().astype(np.uint8)
    img = Image.fromarray(bg, "RGB")
    t = tile.resize((th, th), Image.LANCZOS)
    ramp = np.clip(np.minimum(np.arange(th), th - 1 - np.arange(th)) / (th * FEATHER), 0, 1)
    ramp = ramp * ramp * (3 - 2 * ramp)
    a = np.asarray(t.getchannel("A"), dtype=np.float64) * np.minimum.outer(ramp, ramp)
    t.putalpha(Image.fromarray(a.round().astype(np.uint8), "L"))
    img.paste(t, (ox, oy), t)
    return img


def main():
    tile = Image.open(SRC).convert("RGBA")
    coefs = fit_gradient(tile)
    for dev, size in SIZES.items():
        out = os.path.join(HERE, "bootlogo", "bootlogo-%s.bmp" % dev)
        render(tile, coefs, size).save(out, "BMP")
        print("%s: %dx%d -> %s" % (dev, size[0], size[1], os.path.relpath(out, HERE)))


if __name__ == "__main__":
    sys.exit(main())
