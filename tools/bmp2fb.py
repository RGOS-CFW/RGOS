#!/usr/bin/env python3
"""Convert a boot logo BMP into a raw framebuffer image that busybox can paint with a plain `cat > /dev/fb0`.

usage: bmp2fb.py <bootlogo.bmp> <out dir>

Reads an uncompressed 24-bit BMP and writes <out dir>/bootlogo-<W>x<H>.raw: top-down rows of 32-bit B,G,R,X pixels
(the XRGB8888 layout of a DRM fbdev console, stride = W * 4). The file name carries the width so the init scripts can
pick the right file for the framebuffer they find, and skip painting when none matches. Pure Python, no Pillow.
"""
import os
import struct
import sys


def convert(data):
    """BMP bytes -> (width, height, raw BGRX bytes, top-down)."""
    if data[:2] != b"BM":
        raise ValueError("not a BMP file")
    off = struct.unpack_from("<I", data, 10)[0]
    w, h, planes, bpp, comp = struct.unpack_from("<iiHHI", data, 18)
    if bpp != 24 or comp != 0:
        raise ValueError("need an uncompressed 24-bit BMP (got %d bpp, compression %d)" % (bpp, comp))
    bottom_up = h > 0
    h = abs(h)
    if w <= 0 or h == 0:
        raise ValueError("empty image")
    row = (w * 3 + 3) & ~3
    if len(data) < off + row * h:
        raise ValueError("BMP is truncated")
    out = bytearray(w * 4 * h)
    for y in range(h):
        src = off + (h - 1 - y if bottom_up else y) * row
        px = data[src:src + w * 3]
        line = bytearray(w * 4)
        line[0::4], line[1::4], line[2::4] = px[0::3], px[1::3], px[2::3]
        out[y * w * 4:(y + 1) * w * 4] = line
    return w, h, bytes(out)


def main(argv):
    if len(argv) != 3:
        sys.exit(__doc__)
    with open(argv[1], "rb") as f:
        w, h, raw = convert(f.read())
    os.makedirs(argv[2], exist_ok=True)
    path = os.path.join(argv[2], "bootlogo-%dx%d.raw" % (w, h))
    with open(path, "wb") as f:
        f.write(raw)
    print(path)


if __name__ == "__main__":
    main(sys.argv)
