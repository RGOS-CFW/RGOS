"""Hardware overlay plane: draws a small picture ABOVE a running DRM/KMS program (a native port, SDL kmsdrm, ...).

Why: a program that renders through DRM/KMS owns the screen, so pixels written into /dev/fb0 are never shown over it
(they only appear on the console / launcher). The display controller has extra "overlay" planes that are composited
above the program's own plane in hardware. This module puts one of them in front of everything with the picture the
caller gives it, using only ctypes + ioctl (no libdrm).

Safety rules (a wrong move here could stop the game from getting the screen):
  * the card is opened only while a game runs, and master is dropped again right away, so the game keeps (or can take) it;
  * atomic commits need no master, and only this one plane is touched; a free plane (no CRTC, no FB) is chosen;
  * every failure raises DrmError and the caller falls back to the old framebuffer drawing.
Environment: RGOS_DRM_DEV (/dev/dri/card0).
"""
import ctypes, fcntl, mmap, os, struct

DRM_DEV = os.environ.get("RGOS_DRM_DEV", "/dev/dri/card0")
FOURCC_ARGB8888 = 0x34325241
CAP_UNIVERSAL_PLANES, CAP_ATOMIC = 2, 3
PLANE_OVERLAY = 0


class DrmError(Exception):
    pass


def _ioc(nr, size, rw=3):
    return (rw << 30) | (size << 16) | (ord("d") << 8) | nr


IO_SET_CLIENT_CAP = _ioc(0x0D, 16, 1)
IO_DROP_MASTER = (0 << 30) | (ord("d") << 8) | 0x1F
IO_GETRESOURCES, IO_GETCRTC = _ioc(0xA0, 64), _ioc(0xA1, 104)
IO_GETPROPERTY, IO_CREATE_DUMB, IO_MAP_DUMB = _ioc(0xAA, 64), _ioc(0xB2, 32), _ioc(0xB3, 16)
IO_DESTROY_DUMB, IO_RMFB, IO_ADDFB2 = _ioc(0xB4, 4), _ioc(0xAF, 4), _ioc(0xB8, 104)
IO_PLANERES, IO_GETPLANE, IO_OBJ_PROPS, IO_ATOMIC = _ioc(0xB5, 16), _ioc(0xB6, 32), _ioc(0xB9, 32), _ioc(0xBC, 56)
OBJ_PLANE = 0xEEEEEEEE


def fb_rect_for(rect, lw, lh, rotate):
    """Rectangle of the upright screen -> where it sits on the panel (same maths as rgos-overlay's to_fb_rect)."""
    x, y, w, h = rect
    if rotate == 90:
        return lh - y - h, x, h, w
    if rotate == 180:
        return lw - x - w, lh - y - h, w, h
    if rotate == 270:
        return y, lw - x - w, h, w
    return x, y, w, h


def _buf(n):
    return (ctypes.c_char * n)()


def _addr(b):
    return ctypes.addressof(b)


class DrmOverlay:
    def __init__(self, dev=None):
        self.fd = None
        try:
            self.fd = os.open(dev or DRM_DEV, os.O_RDWR | os.O_CLOEXEC)
        except OSError as e:
            raise DrmError("cannot open %s: %r" % (dev or DRM_DEV, e))
        try:
            self._ioctl(IO_DROP_MASTER, 0, quiet=True)
            for cap in (CAP_UNIVERSAL_PLANES, CAP_ATOMIC):
                self._ioctl(IO_SET_CLIENT_CAP, bytearray(struct.pack("<QQ", cap, 1)))
            self.crtc_id, self.crtc_index, self.size = self._active_crtc()
            self.plane_id, self.props, self.blend = self._pick_plane()
            self.dumb = self.fb_id = self.mm = None
            self.shown = None
        except Exception:
            self.close()
            raise

    def _ioctl(self, req, arg, quiet=False):
        try:
            fcntl.ioctl(self.fd, req, arg, True) if isinstance(arg, bytearray) else fcntl.ioctl(self.fd, req, arg)
        except OSError as e:
            if quiet:
                return False
            raise DrmError("ioctl 0x%x failed: %r" % (req, e))
        return True

    def _resources(self):
        res = bytearray(64)
        self._ioctl(IO_GETRESOURCES, res)
        n = struct.unpack_from("<4I", res, 32)
        arrs = [(ctypes.c_uint32 * max(1, c))() for c in n]
        struct.pack_into("<4Q", res, 0, *[_addr(a) for a in arrs])
        struct.pack_into("<4I", res, 32, *n)
        self._ioctl(IO_GETRESOURCES, res)
        return [list(a[:c]) for a, c in zip(arrs, n)]

    def _active_crtc(self):
        _, crtcs, _, _ = self._resources()
        for i, cid in enumerate(crtcs):
            c = bytearray(104)
            struct.pack_into("<I", c, 12, cid)
            self._ioctl(IO_GETCRTC, c)
            if struct.unpack_from("<I", c, 32)[0]:
                hd, vd = struct.unpack_from("<H", c, 36 + 4)[0], struct.unpack_from("<H", c, 36 + 14)[0]
                if hd and vd:
                    return cid, i, (hd, vd)
        raise DrmError("no active CRTC")

    def _obj_props(self, obj_id, obj_type):
        h = bytearray(32)
        struct.pack_into("<II", h, 20, obj_id, obj_type)
        self._ioctl(IO_OBJ_PROPS, h)
        n = struct.unpack_from("<I", h, 16)[0]
        ids, vals = (ctypes.c_uint32 * max(1, n))(), (ctypes.c_uint64 * max(1, n))()
        struct.pack_into("<QQ", h, 0, _addr(ids), _addr(vals))
        self._ioctl(IO_OBJ_PROPS, h)
        return list(ids[:n]), list(vals[:n])

    def _prop_info(self, pid):
        """(name, flags, {enum name: value})"""
        p = bytearray(64)
        struct.pack_into("<I", p, 16, pid)
        self._ioctl(IO_GETPROPERTY, p)
        nv, ne = struct.unpack_from("<2I", p, 56)
        flags = struct.unpack_from("<I", p, 20)[0]
        name = bytes(p[24:56]).split(b"\0")[0].decode("ascii", "replace")
        enums = {}
        if ne:
            vals, blobs = (ctypes.c_uint64 * max(1, nv))(), _buf(40 * ne)
            struct.pack_into("<QQ", p, 0, _addr(vals), _addr(blobs))
            struct.pack_into("<2I", p, 56, nv, ne)
            self._ioctl(IO_GETPROPERTY, p)
            raw = bytes(blobs)
            for i in range(ne):
                v = struct.unpack_from("<Q", raw, i * 40)[0]
                enums[raw[i * 40 + 8:i * 40 + 40].split(b"\0")[0].decode("ascii", "replace")] = v
        return name, flags, enums

    def _plane_formats(self, pid):
        g = bytearray(32)
        struct.pack_into("<I", g, 0, pid)
        self._ioctl(IO_GETPLANE, g)
        possible, n = struct.unpack_from("<I", g, 12)[0], struct.unpack_from("<I", g, 20)[0]
        fm = (ctypes.c_uint32 * max(1, n))()
        struct.pack_into("<Q", g, 24, _addr(fm))
        self._ioctl(IO_GETPLANE, g)
        return struct.unpack_from("<I", g, 4)[0], struct.unpack_from("<I", g, 8)[0], possible, list(fm[:n])

    def _pick_plane(self):
        r = bytearray(16)
        self._ioctl(IO_PLANERES, r)
        n = struct.unpack_from("<I", r, 8)[0]
        ids = (ctypes.c_uint32 * max(1, n))()
        struct.pack_into("<Q", r, 0, _addr(ids))
        self._ioctl(IO_PLANERES, r)
        best = None
        for pid in list(ids[:n]):
            crtc, fb, possible, fmts = self._plane_formats(pid)
            if crtc or fb or not possible & (1 << self.crtc_index) or FOURCC_ARGB8888 not in fmts:
                continue
            pids, pvals = self._obj_props(pid, OBJ_PLANE)
            props, blend, kind = {}, None, None
            for i, v in zip(pids, pvals):
                name, _, enums = self._prop_info(i)
                props[name] = i
                if name == "type":
                    kind = v
                if name == "pixel blend mode":
                    blend = enums.get("Coverage")
            rank = 0 if kind == PLANE_OVERLAY else 1
            if kind == 2 or "FB_ID" not in props:
                continue
            if best is None or rank < best[0]:
                best = (rank, pid, props, blend)
        if best is None:
            raise DrmError("no free overlay plane that takes ARGB8888")
        return best[1], best[2], best[3]

    def _free_buffer(self):
        if self.fb_id:
            self._ioctl(IO_RMFB, bytearray(struct.pack("<I", self.fb_id)), quiet=True)
        if self.mm:
            self.mm.close()
        if self.dumb:
            self._ioctl(IO_DESTROY_DUMB, bytearray(struct.pack("<I", self.dumb)), quiet=True)
        self.dumb = self.fb_id = self.mm = None

    def _make_buffer(self, w, h):
        c = bytearray(32)
        struct.pack_into("<3I", c, 0, h, w, 32)
        self._ioctl(IO_CREATE_DUMB, c)
        handle, pitch, size = struct.unpack_from("<IIQ", c, 16)
        self.dumb = handle
        m = bytearray(16)
        struct.pack_into("<I", m, 0, handle)
        self._ioctl(IO_MAP_DUMB, m)
        off = struct.unpack_from("<Q", m, 8)[0]
        self.mm = mmap.mmap(self.fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=off)
        f = bytearray(104)
        struct.pack_into("<4I", f, 4, w, h, FOURCC_ARGB8888, 0)
        struct.pack_into("<I", f, 20, handle)
        struct.pack_into("<I", f, 36, pitch)
        self._ioctl(IO_ADDFB2, f)
        self.fb_id = struct.unpack_from("<I", f, 0)[0]
        self.pitch, self.wh = pitch, (w, h)

    def _commit(self, fb, crtc, x, y, w, h):
        names = {"FB_ID": fb, "CRTC_ID": crtc, "SRC_X": 0, "SRC_Y": 0, "SRC_W": w << 16, "SRC_H": h << 16,
                 "CRTC_X": x, "CRTC_Y": y, "CRTC_W": w, "CRTC_H": h}
        if self.blend is not None and "pixel blend mode" in self.props:
            names["pixel blend mode"] = self.blend
        items = [(self.props[k], v) for k, v in names.items() if k in self.props]
        ids = (ctypes.c_uint32 * 1)(self.plane_id)
        cnt = (ctypes.c_uint32 * 1)(len(items))
        pr = (ctypes.c_uint32 * len(items))(*[i for i, _ in items])
        vl = (ctypes.c_uint64 * len(items))(*[v for _, v in items])
        a = bytearray(56)
        struct.pack_into("<IIQQQQ", a, 0, 0, 1, _addr(ids), _addr(cnt), _addr(pr), _addr(vl))
        self._ioctl(IO_ATOMIC, a)

    def show(self, rect, bgra):
        """rect (x, y, w, h) in panel pixels; bgra: w*h*4 bytes of ARGB8888 (premultiplied unless blend mode is Coverage)."""
        x, y, w, h = rect
        if self.fb_id and self.wh != (w, h):
            self.hide()
        if not self.fb_id:
            self._make_buffer(w, h)
        row = w * 4
        for r in range(h):
            self.mm[r * self.pitch:r * self.pitch + row] = bgra[r * row:(r + 1) * row]
        if self.shown != (x, y, w, h):
            self._commit(self.fb_id, self.crtc_id, x, y, w, h)
            self.shown = (x, y, w, h)

    def premultiplied(self):
        return self.blend is None

    def hide(self):
        if self.shown is not None:
            try:
                self._commit(0, 0, 0, 0, 0, 0)
            except DrmError:
                pass
            self.shown = None
        self._free_buffer()

    def close(self):
        try:
            self.hide()
        except Exception:
            pass
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
