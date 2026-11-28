"""Tools > Music: the library, tags, play queue and transport behind the PSP-style player screen.

Plain Python with no pygame import, so it runs (and is tested) without a device: the mixer is handed in.

* ``scan`` lists the tracks in ROMS/music (sub folders included, natural sort order).
* ``read_meta`` reads title / artist / album / length and the cover picture straight from the file header
  (ID3v2 / ID3v1 for MP3, Vorbis comments for FLAC and Ogg, RIFF for WAV). Nothing is decoded: the length of an
  MP3 comes from its Xing / VBRI header, or from bitrate and file size for constant-bitrate files.
* ``Library`` keeps the track list and fills in the tags on a background thread.
* ``Player`` is the transport: play / pause / stop / previous / next / seek, shuffle and repeat. It keeps its own
  clock because pygame cannot report the position after a seek.
* ``ArtLoader`` decodes cover pictures off the UI thread.
"""
import io
import math
import os
import random
import re
import struct
import threading
import time

EXTS = (".mp3", ".ogg", ".oga", ".wav", ".flac", ".mod", ".xm", ".it", ".s3m")
MAX_TRACKS = 4000
SEEK_STEP = 10.0
SEEK_SETTLE = 0.3
RESTART_AFTER = 3.0
VOLUME = 1.0
MIXER_RATE = 44100
REPEAT_MODES = ("off", "all", "one")


def music_dir(roms_root):
    return os.path.join(roms_root, "music")


def _natural(s):
    return [int(p) if i % 2 else p for i, p in enumerate(re.split(r"(\d+)", s.lower()))]


def scan(root):
    """Every playable file under root, hidden files and folders skipped, in natural path order."""
    found = []
    if not os.path.isdir(root):
        return found
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            if not name.startswith(".") and name.lower().endswith(EXTS):
                found.append(os.path.join(base, name))
    found.sort(key=lambda p: _natural(os.path.relpath(p, root)))
    return found[:MAX_TRACKS]


def fmt_time(sec):
    """m:ss (h:mm:ss from an hour up); '--:--' when the length is unknown."""
    if sec is None or sec < 0:
        return "--:--"
    sec = int(sec)
    if sec >= 3600:
        return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)
    return "%d:%02d" % (sec // 60, sec % 60)


def viz_bars(t, n, energy):
    """n smooth pseudo-random bar heights (0..1) for the equaliser. Purely decorative: pygame cannot tap the audio
    stream, so the bars move with the clock, scaled by energy (1 while playing, easing to 0 when paused)."""
    out = []
    for i in range(n):
        v = (math.sin(t * (2.3 + 0.37 * i) + i * 1.7) + 0.6 * math.sin(t * (3.1 + 0.21 * i) + i * 0.6) + 1.6) / 3.2
        out.append(max(0.0, min(1.0, v * energy)))
    return out


def _synchsafe(b):
    return (b[0] & 127) << 21 | (b[1] & 127) << 14 | (b[2] & 127) << 7 | (b[3] & 127)


def _text(enc, data):
    try:
        if enc == 1:
            s = data.decode("utf-16")
        elif enc == 2:
            s = data.decode("utf-16-be")
        elif enc == 3:
            s = data.decode("utf-8")
        else:
            s = data.decode("latin-1")
    except UnicodeDecodeError:
        s = data.decode("latin-1", "replace")
    return s.split("\x00")[0].strip()


_ID3_TEXT = {"TIT2": "title", "TPE1": "artist", "TALB": "album", "TT2": "title", "TP1": "artist", "TAL": "album"}
_ID3_PIC = ("APIC", "PIC")
_IMG_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")


def _picture(data):
    """The image bytes inside an APIC / PIC frame (found by their magic number, which spares parsing the
    encoding-dependent description in between)."""
    best = -1
    for magic in _IMG_MAGIC:
        i = data.find(magic, 0, 1024)
        if i >= 0 and (best < 0 or i < best):
            best = i
    return data[best:] if best >= 0 else None


def _id3v2(f, want_art):
    """Read an ID3v2.2 / 2.3 / 2.4 tag at the start of f. Returns {'end': offset of the audio, <tags>} or None.
    Frames are walked with seek, so a multi-megabyte cover is skipped without being read unless it is wanted."""
    head = f.read(10)
    if len(head) < 10 or head[:3] != b"ID3":
        return None
    ver, flags, size = head[3], head[5], _synchsafe(head[6:10])
    out = {"end": 10 + size + (10 if ver == 4 and flags & 0x10 else 0)}
    if ver not in (2, 3, 4):
        return out
    src, limit = f, size
    if flags & 0x80 and ver < 4:
        body = f.read(size).replace(b"\xff\x00", b"\xff")
        src, limit = io.BytesIO(body), len(body)
    pos = 0
    if flags & 0x40 and ver >= 3:
        raw = src.read(4)
        if len(raw) < 4:
            return out
        skip = (_synchsafe(raw) - 4) if ver == 4 else struct.unpack(">I", raw)[0]
        src.seek(max(0, skip), 1)
        pos = 4 + max(0, skip)
    hlen = 6 if ver == 2 else 10
    while pos + hlen <= limit:
        h = src.read(hlen)
        if len(h) < hlen or h[0] == 0:
            break
        fid = h[:3].decode("latin-1") if ver == 2 else h[:4].decode("latin-1")
        if ver == 2:
            fsz = int.from_bytes(h[3:6], "big")
        else:
            fsz = _synchsafe(h[4:8]) if ver == 4 else struct.unpack(">I", h[4:8])[0]
        pos += hlen
        if fsz <= 0 or pos + fsz > limit:
            break
        key = _ID3_TEXT.get(fid)
        wanted = (key is not None and key not in out) or (fid in _ID3_PIC and want_art and "art" not in out)
        if wanted:
            data = src.read(fsz)
            fflags = h[9] if ver >= 3 else 0
            usable = not (fflags & 0x80 or fflags & 0x40) if ver == 3 else not (fflags & 0x0C)
            if usable and ver == 4:
                if fflags & 0x01:
                    data = data[4:]
                if fflags & 0x02:
                    data = data.replace(b"\xff\x00", b"\xff")
            if usable and data:
                if key:
                    out[key] = _text(data[0], data[1:])
                else:
                    pic = _picture(data)
                    if pic:
                        out["art"] = pic
        else:
            src.seek(fsz, 1)
        pos += fsz
    return out


def _id3v1(f, size):
    if size < 128:
        return None
    f.seek(size - 128)
    b = f.read(128)
    if b[:3] != b"TAG":
        return None
    cut = lambda x: x.split(b"\x00")[0].decode("latin-1").strip()
    return {"title": cut(b[3:33]), "artist": cut(b[33:63]), "album": cut(b[63:93])}


_MP3_BR = {(1, 1): [32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
           (1, 2): [32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
           (1, 3): [32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
           (2, 1): [32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
           (2, 2): [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
           (2, 3): [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
_MP3_SR = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def _mp3_frame(h):
    """Parse a 4-byte MPEG audio frame header -> dict, or None when it is not a valid one."""
    if len(h) < 4 or h[0] != 0xFF or (h[1] & 0xE0) != 0xE0:
        return None
    vb, lb = (h[1] >> 3) & 3, (h[1] >> 1) & 3
    bi, si = h[2] >> 4, (h[2] >> 2) & 3
    if vb == 1 or lb == 0 or bi in (0, 15) or si == 3:
        return None
    mpeg1, layer = vb == 3, 4 - lb
    kbps = _MP3_BR[(1 if mpeg1 else 2, layer)][bi - 1]
    rate = _MP3_SR[vb][si]
    pad = (h[2] >> 1) & 1
    if layer == 1:
        length = (12 * kbps * 1000 // rate + pad) * 4
    else:
        length = (144 if mpeg1 or layer == 2 else 72) * kbps * 1000 // rate + pad
    return {"mpeg1": mpeg1, "layer": layer, "kbps": kbps, "rate": rate, "length": length,
            "spf": 384 if layer == 1 else (1152 if mpeg1 or layer == 2 else 576),
            "mono": (h[3] >> 6) == 3, "crc": not h[1] & 1}


def _mp3_duration(f, start, size):
    """Length in seconds of an MP3 whose audio begins near `start`, or None."""
    f.seek(start)
    buf = f.read(131072)
    i = buf.find(b"\xff")
    while 0 <= i < len(buf) - 4:
        fr = _mp3_frame(buf[i:i + 4])
        nxt = i + fr["length"] if fr else 0
        if fr and not (nxt + 4 <= len(buf) and _mp3_frame(buf[nxt:nxt + 4]) is None):
            side = (17 if fr["mono"] else 32) if fr["mpeg1"] else (9 if fr["mono"] else 17)
            off = i + 4 + (2 if fr["crc"] else 0) + side
            frames = 0
            if buf[off:off + 4] in (b"Xing", b"Info") and len(buf) >= off + 12 and buf[off + 7] & 1:
                frames = struct.unpack(">I", buf[off + 8:off + 12])[0]
            elif buf[i + 36:i + 40] == b"VBRI" and len(buf) >= i + 54:
                frames = struct.unpack(">I", buf[i + 50:i + 54])[0]
            if frames:
                return frames * fr["spf"] / float(fr["rate"])
            audio = size - (start + i)
            if size >= 128:
                f.seek(size - 128)
                if f.read(3) == b"TAG":
                    audio -= 128
            return max(0.0, audio * 8.0 / (fr["kbps"] * 1000.0))
        i = buf.find(b"\xff", i + 1)
    return None


def _vorbis_comments(b):
    """{'title': ..., 'artist': ..., 'album': ...} from a Vorbis comment block."""
    out = {}
    try:
        n = struct.unpack("<I", b[:4])[0]
        pos = 4 + n
        count = struct.unpack("<I", b[pos:pos + 4])[0]
        pos += 4
        for _ in range(count):
            ln = struct.unpack("<I", b[pos:pos + 4])[0]
            item = b[pos + 4:pos + 4 + ln].decode("utf-8", "replace")
            pos += 4 + ln
            k, _sep, v = item.partition("=")
            if _sep and k.lower() in ("title", "artist", "album") and v.strip():
                out.setdefault(k.lower(), v.strip())
    except (struct.error, IndexError):
        pass
    return out


def _flac(f, want_art):
    if f.read(4) != b"fLaC":
        return None
    out = {}
    while True:
        h = f.read(4)
        if len(h) < 4:
            break
        last, kind, ln = h[0] >> 7, h[0] & 127, int.from_bytes(h[1:4], "big")
        if kind == 0 and ln >= 18:
            d = f.read(ln)
            rate = (d[10] << 12) | (d[11] << 4) | (d[12] >> 4)
            total = ((d[13] & 15) << 32) | int.from_bytes(d[14:18], "big")
            if rate and total:
                out["duration"] = total / float(rate)
        elif kind == 4:
            out.update(_vorbis_comments(f.read(ln)))
        elif kind == 6 and want_art and ln < 16 * 1024 * 1024:
            d = f.read(ln)
            try:
                mlen = struct.unpack(">I", d[4:8])[0]
                dlen = struct.unpack(">I", d[8 + mlen:12 + mlen])[0]
                pos = 12 + mlen + dlen + 16
                n = struct.unpack(">I", d[pos:pos + 4])[0]
                out["art"] = d[pos + 4:pos + 4 + n] or None
            except (struct.error, IndexError):
                pass
        else:
            f.seek(ln, 1)
        if last:
            break
    return out


def _ogg_packets(f, want, limit=1 << 20):
    """The first `want` packets of an Ogg stream (the header packets)."""
    packets, cur, used = [], b"", 0
    while len(packets) < want and used < limit:
        h = f.read(27)
        if len(h) < 27 or h[:4] != b"OggS":
            break
        for lace in f.read(h[26]):
            cur += f.read(lace)
            used += lace
            if lace < 255:
                packets.append(cur)
                cur = b""
                if len(packets) >= want:
                    break
    return packets


def _ogg(f, size):
    pk = _ogg_packets(f, 2)
    if not pk:
        return None
    out, rate, skip = {}, None, 0
    if pk[0][:7] == b"\x01vorbis" and len(pk[0]) >= 16:
        rate = struct.unpack("<I", pk[0][12:16])[0]
    elif pk[0][:8] == b"OpusHead" and len(pk[0]) >= 12:
        rate, skip = 48000, struct.unpack("<H", pk[0][10:12])[0]
    if len(pk) > 1:
        if pk[1][:7] == b"\x03vorbis":
            out.update(_vorbis_comments(pk[1][7:]))
        elif pk[1][:8] == b"OpusTags":
            out.update(_vorbis_comments(pk[1][8:]))
    if rate:
        f.seek(max(0, size - 65536))
        tail = f.read()
        i = tail.rfind(b"OggS")
        if i >= 0 and len(tail) >= i + 14:
            gran = struct.unpack("<q", tail[i + 6:i + 14])[0]
            if gran > skip:
                out["duration"] = (gran - skip) / float(rate)
    return out


def _wav_duration(f, size):
    head = f.read(12)
    if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        return None
    byte_rate = None
    while True:
        ch = f.read(8)
        if len(ch) < 8:
            return None
        cid, ln = ch[:4], struct.unpack("<I", ch[4:])[0]
        if cid == b"fmt ":
            byte_rate = struct.unpack("<I", f.read(ln)[8:12])[0]
            f.seek(ln & 1, 1)
        elif cid == b"data":
            if not byte_rate:
                return None
            return min(ln, max(0, size - f.tell())) / float(byte_rate)
        else:
            f.seek(ln + (ln & 1), 1)


def read_meta(path, art=False):
    """{'title', 'artist', 'album', 'duration' (seconds or None), 'art' (bytes or None)} for one file.
    A damaged or unknown file simply gives fewer fields: reading tags must never get in the player's way."""
    meta = {"title": "", "artist": "", "album": "", "duration": None, "art": None}
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            magic = f.read(4)
            f.seek(0)
            found = {}
            if magic[:3] == b"ID3" or path.lower().endswith(".mp3"):
                tag = _id3v2(f, art) or {}
                found = dict(tag)
                if not found.get("title"):
                    found.update({k: v for k, v in (_id3v1(f, size) or {}).items() if v})
                found["duration"] = _mp3_duration(f, tag.get("end", 0), size)
            elif magic == b"fLaC":
                found = _flac(f, art) or {}
            elif magic == b"OggS":
                found = _ogg(f, size) or {}
            elif magic == b"RIFF":
                found = {"duration": _wav_duration(f, size)}
            for k in meta:
                if found.get(k):
                    meta[k] = found[k]
    except Exception:
        pass
    return meta


class Track:
    __slots__ = ("path", "name", "title", "artist", "album", "duration", "tagged", "bad")

    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.title = self.artist = self.album = ""
        self.duration = None
        self.tagged = False
        self.bad = False

    @property
    def label(self):
        return self.title or self.name


class Library:
    """The track list for a folder. rescan() is cheap (a directory walk); tags and lengths are read by a background
    thread, top of the list first, so a long list shows up at once and fills in."""

    def __init__(self, root):
        self.root = root
        self.tracks = []
        self._known = {}
        self._worker = None
        self._lock = threading.Lock()

    def rescan(self):
        paths = scan(self.root)
        with self._lock:
            self._known = {p: self._known.get(p) or Track(p) for p in paths}
            self.tracks = [self._known[p] for p in paths]
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._read_tags, daemon=True)
                self._worker.start()
        return self.tracks

    def _read_tags(self):
        while True:
            with self._lock:
                todo = [t for t in self.tracks if not t.tagged]
                if not todo:
                    self._worker = None
                    return
            for t in todo:
                meta = read_meta(t.path)
                t.title, t.artist, t.album, t.duration = meta["title"], meta["artist"], meta["album"], meta["duration"]
                t.tagged = True
                time.sleep(0.002)


class ArtLoader:
    """Cover pictures decoded and cropped to a square on a worker thread. ask(path) returns the surface once it is
    ready, and None while it loads or when the file has no picture."""

    def __init__(self, pygame_mod, size, keep=6):
        self.pg, self.size, self.keep = pygame_mod, size, keep
        self._done, self._busy, self._lock = {}, set(), threading.Lock()

    def ask(self, path):
        with self._lock:
            if path in self._done:
                surf = self._done.pop(path)
                self._done[path] = surf
                return surf
            if path in self._busy:
                return None
            self._busy.add(path)
        threading.Thread(target=self._work, args=(path,), daemon=True).start()
        return None

    def _work(self, path):
        surf = None
        try:
            data = read_meta(path, art=True)["art"]
            if data:
                img = self.pg.image.load(io.BytesIO(data))
                w, h = img.get_size()
                s = min(w, h)
                sq = img.subsurface(((w - s) // 2, (h - s) // 2, s, s))
                try:
                    surf = self.pg.transform.smoothscale(sq, (self.size, self.size))
                except ValueError:
                    surf = self.pg.transform.scale(sq, (self.size, self.size))
        except Exception:
            surf = None
        with self._lock:
            self._done[path] = surf
            while len(self._done) > self.keep:
                self._done.pop(next(iter(self._done)))
            self._busy.discard(path)


class Player:
    """Plays Track objects through pygame's mixer.music.

    The queue is the track list in order, or a shuffled copy that starts with the song you picked and does not
    repeat a song until the whole list has played. At the end of the queue it stops (repeat off), starts over
    (repeat all) or keeps replaying the song (repeat one). A file the mixer cannot decode is marked bad and skipped.
    """

    def __init__(self, mixer, clock=time.monotonic, log=None, rng=None):
        self.mixer = mixer
        self.now = clock
        self.log = log or (lambda msg: None)
        self.rng = rng or random.Random()
        self.tracks = []
        self.cur = None
        self.state = "stopped"
        self.shuffle = False
        self.repeat = "all"
        self.hold = False
        self.msg, self.msg_until = "", 0.0
        self._order, self._opos = [], -1
        self._t0 = self._paused_at = 0.0
        self._seek_to, self._seek_at = None, 0.0

    @property
    def active(self):
        return self.state != "stopped"

    @property
    def engaged(self):
        """True while the launcher's own background music must stay quiet."""
        return self.hold or self.state != "stopped"

    def say(self, text, secs=3.0):
        self.msg, self.msg_until = text, self.now() + secs

    def message(self):
        return self.msg if self.now() < self.msg_until else ""

    def position(self):
        if self._seek_to is not None:
            return self._seek_to
        if self.state == "stopped":
            return 0.0
        pos = max(0.0, (self._paused_at if self.state == "paused" else self.now()) - self._t0)
        d = self.cur.duration if self.cur is not None else None
        return min(pos, d) if d else pos

    def set_tracks(self, tracks):
        same = len(tracks) == len(self.tracks) and all(a is b for a, b in zip(tracks, self.tracks))
        self.tracks = tracks
        if not same:
            self._build_order(self.cur)

    def _build_order(self, first):
        order = list(self.tracks)
        if self.shuffle:
            self.rng.shuffle(order)
            if first in order:
                order.remove(first)
                order.insert(0, first)
        self._order = order
        self._opos = order.index(first) if first in order else -1

    def cycle_repeat(self):
        self.repeat = REPEAT_MODES[(REPEAT_MODES.index(self.repeat) + 1) % len(REPEAT_MODES)]
        return self.repeat

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self._build_order(self.cur)
        return self.shuffle

    def _ensure_mixer(self):
        m = self.mixer
        info = m.get_init()
        if not info:
            m.init(MIXER_RATE, -16, 2, 4096)
        elif isinstance(info, (tuple, list)) and info[0] < MIXER_RATE:
            m.quit()
            m.init(MIXER_RATE, -16, 2, 4096)

    def _start(self, track, at=0.0):
        try:
            self._ensure_mixer()
            music = self.mixer.music
            music.load(track.path)
            music.set_volume(VOLUME)
            music.play(0, at) if at else music.play()
        except Exception as e:
            track.bad = True
            self.log("music player: cannot play %s: %s" % (track.path, e))
            return False
        track.bad = False
        self.cur, self.state = track, "playing"
        self._t0 = self.now() - at
        self._seek_to = None
        return True

    def enter(self):
        """The player screen opened: silence the launcher's background track so only one thing plays."""
        if self.state == "stopped":
            try:
                if self.mixer.get_init():
                    self.mixer.music.stop()
            except Exception:
                pass

    def play(self, track):
        """Start this song now (the A button on a list row)."""
        if track not in self._order or self.shuffle:
            self._build_order(track)
        else:
            self._opos = self._order.index(track)
        if not self._start(track):
            self.stop()
            self.say("Can't play %s" % track.label)
            return False
        return True

    def toggle(self):
        """Play / pause; from stopped it starts the last song (or the first)."""
        if self.state == "playing":
            self.mixer.music.pause()
            self._paused_at, self.state = self.now(), "paused"
        elif self.state == "paused":
            self.mixer.music.unpause()
            self._t0 += self.now() - self._paused_at
            self.state = "playing"
        elif self.tracks:
            return self.play(self.cur if self.cur in self.tracks else self.tracks[0])

    def stop(self):
        try:
            if self.mixer.get_init():
                self.mixer.music.stop()
        except Exception:
            pass
        self.state, self._seek_to = "stopped", None

    def _step(self, direction, auto):
        """Move along the queue to the next playable song. False when playback ended (or nothing plays)."""
        n = len(self._order)
        for _ in range(n):
            pos = (self._opos if self._opos >= 0 or direction > 0 else n) + direction
            if pos >= n or pos < 0:
                if auto and self.repeat != "all":
                    self.stop()
                    return False
                if pos >= n and self.shuffle and n > 1:
                    last = self._order[-1]
                    self.rng.shuffle(self._order)
                    if self._order[0] is last:
                        self._order.append(self._order.pop(0))
                pos %= n
            self._opos = pos
            if self._start(self._order[pos]):
                return True
        self.stop()
        if n:
            self.say("None of the songs can be played")
        return False

    def next(self):
        return self._step(1, False)

    def prev(self):
        if self.state != "stopped" and self.position() > RESTART_AFTER and self.cur is not None:
            return self._start(self.cur)
        return self._step(-1, False)

    def seek(self, delta):
        """Move the playhead by delta seconds. The target shows at once; the decoder is asked after SEEK_SETTLE."""
        if self.state == "stopped" or self.cur is None:
            return
        base = self._seek_to if self._seek_to is not None else self.position()
        target = max(0.0, base + delta)
        if self.cur.duration:
            target = min(target, self.cur.duration)
        self._seek_to, self._seek_at = target, self.now() + SEEK_SETTLE

    def _apply_seek(self, now):
        target, self._seek_to = self._seek_to, None
        d = self.cur.duration
        if d and target >= d - 0.5:
            self._ended()
            return
        try:
            self.mixer.music.set_pos(target)
        except Exception as e:
            self.log("music player: seek failed: %s" % e)
            self.say("This file cannot be searched")
            return
        if self.state == "paused":
            self._paused_at = now
        self._t0 = now - target

    def _busy(self):
        try:
            return bool(self.mixer.get_init()) and bool(self.mixer.music.get_busy())
        except Exception:
            return False

    def _ended(self):
        if self.repeat == "one" and self.cur is not None:
            if self._start(self.cur):
                return
            self.stop()
            return
        self._step(1, True)

    def tick(self):
        """Once per frame: apply a settled seek and move on when the song has finished."""
        if self.state == "stopped":
            return
        now = self.now()
        if self._seek_to is not None and now >= self._seek_at:
            self._apply_seek(now)
        if self.state == "playing" and self._seek_to is None and not self._busy():
            self._ended()
