#!/usr/bin/env python3
import glob
import atexit, io, json, math, os, random, re, signal, subprocess, sys, threading, time
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
from evpad import EvPads, CODES as EV_CODES, EV_KEY, EV_ABS
import fbout
import uiboost
import splash
import wifictl
import btctl
import sshctl
import biosctl
import coreinstall
import filemanager
import rgclassic
import artwork
try:
    import sdcard
except Exception:
    sdcard = None

ROMS_ROOT = os.environ.get("RGOS_ROMS", "/media/roms")
SYSTEMS = [("gba", "GBA", "retroarch", (".gba",), "Game Boy Advance"),
           ("gb", "GB", "retroarch", (".gb",), "Game Boy"),
           ("gbc", "GBC", "retroarch", (".gbc",), "Game Boy Color"),
           ("nes", "NES", "retroarch", (".nes", ".unf", ".unif"), "Nintendo Entertainment System"),
           ("snes", "SNES", "retroarch", (".sfc", ".smc", ".swc", ".fig", ".bs"), "Super Nintendo Entertainment System"),
           ("genesis", "MD", "retroarch", (".md", ".gen", ".smd", ".bin"), "Sega Mega Drive / Genesis"),
           ("mastersystem", "SMS", "retroarch", (".sms",), "Sega Master System / Mark III"),
           ("gamegear", "GG", "retroarch", (".gg",), "Sega Game Gear"),
           ("sg1000", "SG", "retroarch", (".sg", ".sc", ".sf"), "Sega SG-1000 / SC-3000"),
           ("segacd", "CD", "retroarch", (".cue", ".chd", ".iso", ".m3u", ".ccd"), "Sega CD / Mega-CD"),
           ("sega32x", "32X", "retroarch", (".32x", ".md", ".gen", ".smd", ".bin"), "Sega 32X"),
           ("segapico", "PICO", "retroarch", (".pico", ".bin"), "Sega Pico"),
           ("atari2600", "A26", "retroarch", (".a26", ".bin"), "Atari 2600"),
           ("atari5200", "A52", "retroarch", (".a52", ".bin", ".car"), "Atari 5200"),
           ("atari7800", "A78", "retroarch", (".a78", ".bin"), "Atari 7800"),
           ("ngp", "NGP", "retroarch", (".ngp", ".ngc", ".ngpc"), "Neo Geo Pocket"),
           ("ngpc", "NGPC", "retroarch", (".ngc", ".ngpc", ".ngp"), "Neo Geo Pocket Color"),
           ("ws", "WS", "retroarch", (".ws", ".wsc", ".pc2"), "WonderSwan"),
           ("wsc", "WSC", "retroarch", (".wsc", ".ws", ".pc2"), "WonderSwan Color"),
           ("psx", "PSX", "retroarch", (".cue", ".chd", ".pbp", ".m3u", ".iso", ".img", ".ccd"), "Sony PlayStation"),
           ("gc", "GC", "retroarch", (".gcm", ".iso", ".gcz", ".rvz", ".ciso", ".m3u", ".dol", ".elf"), "Nintendo GameCube"),
           ("arcade", "ARC", "retroarch", (".zip", ".7z"), "Arcade (FinalBurn Neo)"),
           ("neogeo", "NEO", "retroarch", (".zip", ".7z"), "Neo Geo"),
           ("ports", "PORT", "native", (".sh",), "Ports")]
ROMS_DIR = os.path.join(ROMS_ROOT, "roms")
RUN_DIR = os.environ.get("RGOS_RUN", "/run/rgos")
STATE_FILE = os.environ.get("RGOS_STATE", "/var/lib/rgos/state.json")
FAVORITES_FILE = os.environ.get("RGOS_FAVORITES", os.path.join(ROMS_ROOT, "favorites.txt"))
SPLASH_DONE = os.path.join(RUN_DIR, "splash-done")
INPUT_CONF = os.environ.get("RGOS_INPUT", "/etc/rgos/input.json")
EXIT_LAUNCH, EXIT_POWER = 10, 20
def _device():
    try:
        with open("/etc/rgos-device") as f:
            return f.read().strip()
    except OSError:
        return ""


DEVICE_ID = os.environ.get("RGOS_DEVICE") or _device() or "rg-rotate"
CANVAS = {"rg-rotate": (720, 720), "rg34xxsp": (720, 480), "rg35xxh": (720, 540), "rg35xxsp": (720, 540)}
W, H = CANVAS.get(DEVICE_ID, CANVAS["rg-rotate"])
DY = H - 480
DX = 0

THEMES = [
    ("midnight", "Midnight", dict(BG=(13, 15, 26), PANEL=(24, 28, 46), SEL_BG=(44, 50, 82), ACCENT=(255, 99, 71), TEXT=(232, 235, 245), DIM=(130, 138, 165))),
    ("ocean", "Ocean", dict(BG=(7, 19, 31), PANEL=(13, 35, 55), SEL_BG=(25, 63, 94), ACCENT=(64, 200, 232), TEXT=(226, 240, 248), DIM=(116, 152, 176))),
    ("forest", "Forest", dict(BG=(10, 21, 15), PANEL=(18, 37, 27), SEL_BG=(33, 66, 47), ACCENT=(126, 217, 120), TEXT=(228, 242, 230), DIM=(122, 152, 132))),
    ("sunset", "Sunset", dict(BG=(28, 13, 22), PANEL=(48, 23, 38), SEL_BG=(84, 40, 56), ACCENT=(255, 154, 62), TEXT=(250, 234, 226), DIM=(176, 130, 128))),
    ("purple", "Purple Haze", dict(BG=(19, 12, 31), PANEL=(35, 22, 57), SEL_BG=(65, 40, 103), ACCENT=(198, 120, 255), TEXT=(238, 230, 250), DIM=(150, 130, 184))),
    ("amber", "Amber Terminal", dict(BG=(0, 0, 0), PANEL=(22, 15, 0), SEL_BG=(54, 38, 0), ACCENT=(255, 176, 0), TEXT=(255, 205, 100), DIM=(158, 114, 38))),
    ("gameboy", "Game Boy", dict(BG=(15, 56, 15), PANEL=(28, 78, 28), SEL_BG=(48, 98, 48), ACCENT=(184, 214, 40), TEXT=(224, 248, 208), DIM=(139, 172, 15))),
    ("paper", "Paper (light)", dict(BG=(238, 235, 227), PANEL=(252, 250, 245), SEL_BG=(213, 220, 238), ACCENT=(208, 62, 38), TEXT=(32, 34, 46), DIM=(108, 112, 128))),
    ("mustard", "MustardOS", dict(BG=(24, 22, 18), PANEL=(38, 35, 28), SEL_BG=(84, 70, 20), ACCENT=(240, 184, 0), TEXT=(245, 238, 220), DIM=(158, 148, 118))),
    ("contrast", "High Contrast", dict(BG=(0, 0, 0), PANEL=(28, 28, 28), SEL_BG=(72, 72, 72), ACCENT=(255, 235, 0), TEXT=(255, 255, 255), DIM=(176, 176, 176))),
]
DEFAULT_THEME = THEMES[0][0]
BG = PANEL = SEL_BG = ACCENT = TEXT = DIM = (0, 0, 0)
XMB_COLORS = {"midnight": ((9, 11, 28), (62, 52, 130), (190, 180, 255)),
              "ocean": ((4, 18, 34), (14, 110, 160), (170, 235, 255)),
              "forest": ((8, 24, 12), (70, 130, 50), (205, 245, 190)),
              "sunset": ((30, 10, 24), (190, 80, 60), (255, 215, 170)),
              "purple": ((18, 10, 32), (120, 60, 190), (235, 205, 255)),
              "amber": ((0, 0, 0), (140, 90, 0), (255, 220, 130)),
              "gameboy": ((12, 46, 12), (110, 150, 30), (220, 240, 150)),
              "paper": ((226, 223, 213), (168, 184, 214), (255, 255, 255)),
              "mustard": ((22, 20, 14), (170, 130, 20), (255, 235, 170)),
              "contrast": ((0, 0, 0), (50, 50, 50), (255, 255, 255))}
XMB_TOP = XMB_LOW = XMB_SILK = (0, 0, 0)
BIOS_GOOD, BIOS_WARN, BIOS_BAD = (70, 170, 90), (214, 150, 20), (222, 64, 52)


def theme_index(tid):
    for i, t in enumerate(THEMES):
        if t[0] == tid:
            return i
    return 0


def apply_theme(tid):
    global BG, PANEL, SEL_BG, ACCENT, TEXT, DIM, XMB_TOP, XMB_LOW, XMB_SILK
    tid, _name, c = THEMES[theme_index(tid)]
    BG, PANEL, SEL_BG, ACCENT, TEXT, DIM = c["BG"], c["PANEL"], c["SEL_BG"], c["ACCENT"], c["TEXT"], c["DIM"]
    XMB_TOP, XMB_LOW, XMB_SILK = XMB_COLORS.get(tid, (BG, ACCENT, TEXT))
    publish_theme()
    return tid


_theme_pub = [None]


def publish_theme():
    """Hand the colours to rgos-overlay (the volume bar), which runs outside the launcher."""
    line = " ".join("%d,%d,%d" % tuple(c) for c in (BG, PANEL, ACCENT, TEXT))
    if line == _theme_pub[0]:
        return
    _theme_pub[0] = line
    try:
        os.makedirs(RUN_DIR, exist_ok=True)
        tmp = os.path.join(RUN_DIR, "theme.tmp")
        with open(tmp, "w") as f:
            f.write(line + "\n")
        os.replace(tmp, os.path.join(RUN_DIR, "theme"))
    except OSError:
        pass


apply_theme(DEFAULT_THEME)


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t + 0.5) for i in range(3))


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


class ThemedClassic(rgclassic.Classic):
    """RG Classic launcher recoloured from the active RG OS theme.

    rgclassic.py keeps its palette in module globals, so apply() swaps those
    out and rebuilds the cached background gradient and icons when the theme
    changes.
    """
    _ramp = ((6, 0, 2), (24, 2, 7), (46, 4, 12), (76, 8, 18), (112, 12, 26), (150, 18, 34))

    def __init__(self, w, h):
        self._theme = None
        self._tones = {}
        super().__init__(w, h)

    def _bake_bg(self):
        # dither levels are baked once into an 8-bit surface; a theme change only swaps its palette
        lw, lh = rgclassic.LW, self.LH
        bay = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
        self._idx = pygame.Surface((lw, lh), 0, 8)
        self._idx.set_palette([(i, i, i) for i in range(6)])
        for y in range(lh):
            for x in range(lw):
                f = 1.0 - (x * 0.85 + y) / (lw * 0.85 + lh) * 1.55
                v = max(0.0, min(1.0, f)) * 5.0
                lv = int(v)
                if lv < 5 and (v - lv) * 16.0 > bay[y & 3][x & 3] + 0.5:
                    lv += 1
                self._idx.set_at((x, y), (lv, lv, lv))
        self.bg = pygame.Surface((lw, lh))
        self._paint_bg()

    def _paint_bg(self):
        self._idx.set_palette(self._ramp)
        self.bg.blit(self._idx, (0, 0))

    def apply(self, bg, panel, sel_bg, accent, text, dim):
        key = (bg, panel, sel_bg, accent, text, dim)
        if key == self._theme:
            return
        self._theme = key
        dark = _lum(bg) < 128
        rc = rgclassic
        rc.BLACK = _mix(bg, (0, 0, 0), 0.7)
        rc.WHITE, rc.DIM, rc.PANEL = text, dim, panel
        rc.RED = accent
        rc.REDL = _mix(accent, (255, 255, 255), 0.35)
        rc.REDM = _mix(sel_bg, accent, 0.35)
        lo, hi = (_mix(bg, (0, 0, 0), 0.55), _mix(bg, accent, 0.5)) if dark else (_mix(bg, (0, 0, 0), 0.08), _mix(bg, accent, 0.3))
        self._ramp = tuple(_mix(lo, hi, i / 5.0) for i in range(6))
        self._paint_bg()
        # icon tones (1 fill, 2 shade, 3 outline): selected tile sits on the accent, others on the panel
        la = _lum(accent)
        on = text if abs(_lum(text) - la) * 1.5 >= abs(_lum(bg) - la) else bg
        c1 = _mix(text, panel, 0.2)
        self._tones = {False: (None, on, _mix(on, accent, 0.55), _mix(accent, (0, 0, 0), 0.55)),
                       True: (None, c1, _mix(accent, c1, 0.4), _mix(accent, panel, 0.45))}
        self._ic.clear()

    def _icon(self, hid, dim):
        k = (hid, dim)
        sf = self._ic.get(k)
        if sf is None:
            tone = self._tones[dim]
            sf = pygame.Surface((16, 16), pygame.SRCALPHA)
            for y, row in enumerate(rgclassic.ICON_DATA[hid]):
                for x in range(16):
                    v = (row >> (30 - 2 * x)) & 3
                    if v:
                        sf.set_at((x, y), tone[v])
            self._ic[k] = sf
        return sf

    def text(self, t, x, y, col=None, sc=1, align=0, bold=False):
        # the base class binds its default colour at import time, so resolve it here
        super().text(t, x, y, rgclassic.WHITE if col is None else col, sc, align, bold)

DEFAULT_INPUT = {"debug": False}
KEYMAP = {pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_LEFT: "left",
          pygame.K_RIGHT: "right", pygame.K_RETURN: "a", pygame.K_z: "a",
          pygame.K_ESCAPE: "b", pygame.K_x: "b", pygame.K_q: "l", pygame.K_w: "r",
          pygame.K_PAGEUP: "l", pygame.K_PAGEDOWN: "r", pygame.K_TAB: "select",
          pygame.K_SPACE: "start", pygame.K_c: "x", pygame.K_y: "y"}
REPEATABLE = {"up", "down", "left", "right", "l", "r"}
STICK_AXES = (0x00, 0x01)
STICK_ON, STICK_OFF = 0.55, 0.35
STICK_MAX = 32767.0


def load_json(path, default):
    try:
        with open(path) as f:
            data = json.load(f)
        merged = dict(default)
        merged.update(data)
        return merged
    except Exception:
        return dict(default)


class Input:
    def __init__(self):
        self.conf = load_json(INPUT_CONF, DEFAULT_INPUT)
        self.held, self.repeat, self.last_raw = set(), {}, ""
        self.ev, self.ev_seen = EvPads(), False
        self.stick, self.stick_dir = {0x00: 0.0, 0x01: 0.0}, None

    def _down(self, a, out):
        if a in self.held:
            return
        self.held.add(a)
        out.append(a)
        if a in REPEATABLE:
            self.repeat[a] = time.time() + 0.4

    def _up(self, a):
        self.held.discard(a)
        self.repeat.pop(a, None)

    def _dir(self, neg, pos, v, out):
        for a, active in ((neg, v < 0), (pos, v > 0)):
            if active:
                self._down(a, out)
            else:
                self._up(a)

    def _stick_update(self, out):
        x, y = self.stick[0x00], self.stick[0x01]
        ax, ay = abs(x), abs(y)
        cur = self.stick_dir
        if cur is not None:
            mine, other = (ax, ay) if cur in ("left", "right") else (ay, ax)
            if mine >= STICK_OFF and mine >= other:
                return
        if max(ax, ay) >= STICK_ON:
            new = ("right" if x > 0 else "left") if ax >= ay else ("down" if y > 0 else "up")
        else:
            new = None
        if new == cur:
            return
        if cur is not None:
            self._up(cur)
        self.stick_dir = new
        if new is not None:
            self._down(new, out)

    def poll(self):
        out = []
        evs = self.ev.read()
        if os.path.exists(SCREENOFF_FILE):
            self.held.clear()
            self.repeat.clear()
            self.stick, self.stick_dir = {0x00: 0.0, 0x01: 0.0}, None
            evs = []
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    out.append("quit")
            return out
        for t, c, v in evs:
            if t == EV_KEY and c in EV_CODES:
                self.ev_seen = True
                self.last_raw = "ev 0x%x=%s" % (c, EV_CODES[c])
                if v == 1:
                    self._down(EV_CODES[c], out)
                elif v == 0:
                    self._up(EV_CODES[c])
            elif t == EV_ABS and c == 0x10:
                self._dir("left", "right", v, out)
            elif t == EV_ABS and c == 0x11:
                self._dir("up", "down", v, out)
            elif t == EV_ABS and c in STICK_AXES:
                self.stick[c] = max(-1.0, min(1.0, v / STICK_MAX))
                self._stick_update(out)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                out.append("quit")
            elif e.type == pygame.KEYDOWN and e.key in KEYMAP:
                self._down(KEYMAP[e.key], out)
            elif e.type == pygame.KEYUP and e.key in KEYMAP:
                self._up(KEYMAP[e.key])
        now = time.time()
        for a, t in list(self.repeat.items()):
            if now >= t:
                out.append(a)
                self.repeat[a] = now + 0.07
        return out


def pretty(name):
    base = os.path.splitext(name)[0]
    base = re.sub(r"\s*[\(\[].*?[\)\]]", "", base).replace("_", " ").strip()
    return base or os.path.splitext(name)[0]


def rom_roots():
    roots = [(1, ROMS_ROOT)]
    if sdcard is not None and not os.environ.get("RGOS_NO_CARD2"):
        try:
            roots += [(2, r) for r in sdcard.extra_roots() if r != ROMS_ROOT]
        except Exception:
            pass
    return roots


def scan_roms():
    games = []
    for card, root_dir in rom_roots():
        for sid, tag, core, exts, _name in SYSTEMS:
            folder = os.path.join(root_dir, "roms", sid)
            if not os.path.isdir(folder):
                continue
            for root, dirs, files in os.walk(folder):
                if sid == "ports":
                    dirs[:] = []
                for f in files:
                    if f.lower().endswith(exts) and not f.startswith("."):
                        p = os.path.join(root, f)
                        try:
                            size = os.path.getsize(p)
                        except OSError:
                            size = 0
                        games.append({"title": pretty(f), "path": p, "size": size, "tag": tag, "core": core, "sid": sid,
                                      "card": card})
    games.sort(key=lambda g: (g["title"].lower(), g["tag"], g.get("card", 1)))
    return games


class Rescan:
    def __init__(self):
        self._lock = threading.Lock()
        self._res = None
        self.busy = False

    def start(self):
        with self._lock:
            if self.busy:
                return False
            self.busy, self._res = True, None
        threading.Thread(target=self._work, daemon=True).start()
        return True

    def _work(self):
        try:
            r = scan_roms()
        except Exception:
            r = None
        with self._lock:
            self._res = (r,)

    def take(self):
        with self._lock:
            if self._res is None:
                return None
            r = self._res[0]
            self._res, self.busy = None, False
            return r


def visible_systems(games):
    have = {g["sid"] for g in games}
    return [sy for sy in SYSTEMS if sy[0] in have]


def load_state():
    return load_json(STATE_FILE, {"last": ""})


def save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(st, f)
    except Exception:
        pass


def load_favorites():
    try:
        # favorites.txt lives on the user-editable ROMS partition: tolerate a Windows BOM and non-UTF-8 bytes
        # (a stray byte raised UnicodeDecodeError, which is not an OSError, and crashed the launcher at start)
        with open(FAVORITES_FILE, "r", encoding="utf-8-sig", errors="replace") as f:
            return list(dict.fromkeys(line.strip() for line in f if line.strip()))
    except OSError:
        return []


def save_favorites(paths):
    try:
        os.makedirs(os.path.dirname(FAVORITES_FILE) or ".", exist_ok=True)
        tmp = FAVORITES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(path + "\n" for path in sorted(set(paths)))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, FAVORITES_FILE)
        return True
    except OSError as e:
        log("favorites save failed: %s" % e)
        try:
            os.unlink(FAVORITES_FILE + ".tmp")
        except OSError:
            pass
        return False


from cores import installed_cores, default_core, SYSTEM_CORE_COMPATIBILITY, compatible_cores  # noqa: E402,F401


CORE_NAMES = {"mgba": "mGBA", "gpsp": "gpSP", "vbam": "VBA-M", "gambatte": "Gambatte", "sameboy": "SameBoy", "gearboy": "Gearboy",
              "nestopia": "Nestopia", "fceumm": "FCEUmm", "quicknes": "QuickNES", "mesen": "Mesen", "mesen_s": "Mesen-S",
              "snes9x": "Snes9x", "snes9x2010": "Snes9x 2010", "bsnes": "bsnes", "bsnes_hd_beta": "bsnes-hd",
              "genesis_plus_gx": "Genesis Plus GX", "picodrive": "PicoDrive", "stella2014": "Stella 2014", "stella": "Stella",
              "atari800": "Atari800", "prosystem": "ProSystem", "mednafen_ngp": "Beetle NeoPop", "race": "RACE",
              "mednafen_wswan": "Beetle Cygne", "pcsx_rearmed": "PCSX ReARMed", "mednafen_psx": "Beetle PSX",
              "mednafen_psx_hw": "Beetle PSX HW", "swanstation": "SwanStation", "dolphin": "Dolphin", "fbneo": "FinalBurn Neo",
              "mednafen_gba": "Beetle GBA", "mednafen_gb": "Beetle GB"}


def core_label(sid, state):
    core = state.get("emulators", {}).get(sid)
    if core not in SYSTEM_CORE_COMPATIBILITY.get(sid, ()):
        core = default_core(sid)
    return CORE_NAMES.get(core) or core.replace("_", " ") or "RetroArch"


def game_runner_text(g, state):
    """What runs a game, for the details panel: a native port, or RetroArch plus the chosen core."""
    if g.get("core") == "native":
        return "Native port"
    return "RetroArch + " + core_label(g["sid"], state)


def bios_dirs():
    return [os.path.join(r, "bios") for _c, r in rom_roots()]


def bios_scan(st):
    emus = st.get("emulators") if isinstance(st, dict) else None
    emus = emus if isinstance(emus, dict) else {}

    def core_of(sid):
        core = emus.get(sid)
        return core if core in SYSTEM_CORE_COMPATIBILITY.get(sid, ()) else default_core(sid)
    return biosctl.check_all([(sy[0], sy[4]) for sy in SYSTEMS if sy[2] == "retroarch"], core_of, bios_dirs())


def bios_summary_text(summ):
    if not summ["systems"]:
        return "No installed emulator needs BIOS files"
    parts = []
    if summ["missing"]:
        parts.append("%d required missing" % summ["missing"])
    if summ["optional"]:
        parts.append("%d optional missing" % summ["optional"])
    parts.append("%d OK" % summ["ok"])
    return "   ".join(parts)


ALL_SYSTEMS = list(SYSTEMS)


def _gc_allowed():
    return (os.environ.get("RGOS_DEVICE") or _device() or "rg-rotate") == "rg-rotate"


def filter_systems():
    """Hide systems that have no installed core (and GameCube off the RG Rotate). Edits SYSTEMS in place so that
    everything holding a reference to it sees the change; the Core Installer calls this after installing a core."""
    if os.environ.get("RGOS_ALL_SYSTEMS") == "1":
        SYSTEMS[:] = ALL_SYSTEMS
        return
    have = installed_cores()
    keep = [sy for sy in ALL_SYSTEMS if sy[2] != "retroarch" or compatible_cores(sy[0], have)]
    if not _gc_allowed():
        keep = [sy for sy in keep if sy[0] != "gc"]
    SYSTEMS[:] = keep


def core_installer_rows():
    """Rows for the Core Installer: every core that could serve a RetroArch system on this device, missing ones first."""
    systems = [(sy[0], sy[1], sy[4]) for sy in ALL_SYSTEMS if sy[2] == "retroarch" and (sy[0] != "gc" or _gc_allowed())]
    return coreinstall.candidates(systems, SYSTEM_CORE_COMPATIBILITY, installed_cores(), CORE_NAMES)


filter_systems()


def ensure_folders():
    shared = ("bios", "config", "firmware", "music", "saves", "screenshots", "splash", "states", "update")
    paths = [os.path.join(ROMS_ROOT, d) for d in shared] + [ROMS_DIR]
    for sy in SYSTEMS:
        sid = sy[0]
        paths += [os.path.join(ROMS_DIR, sid)]
        if sy[2] == "retroarch":
            paths += [os.path.join(ROMS_ROOT, "saves", sid), os.path.join(ROMS_ROOT, "states", sid)]
    for d in paths:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            log("could not create %s: %s" % (d, e))


_FIT = {}


def fit(font, text, width):
    key = (font, text, width)
    r = _FIT.get(key)
    if r is None:
        if len(_FIT) > 3000:
            _FIT.clear()
        r = text
        if font.size(r)[0] > width:
            while r and font.size(r + "...")[0] > width:
                r = r[:-1]
            r = r + "..."
        _FIT[key] = r
    return r


def wrap(font, text, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if font.size(t)[0] <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:4]


def _mix(c, t, k):
    return tuple(max(0, min(255, int(c[i] + (t[i] - c[i]) * k))) for i in range(3))


class CFont:
    def __init__(self, font):
        self._f, self._r, self._s = font, {}, {}

    def render(self, text, aa, color, *bg):
        try:
            key = (text, aa, tuple(color), bg)
            surf = self._r.get(key)
        except TypeError:
            return self._f.render(text, aa, color, *bg)
        if surf is None:
            if len(self._r) > 900:
                for k in list(self._r)[:300]:
                    del self._r[k]
            surf = self._r[key] = self._f.render(text, aa, color, *bg)
        return surf

    def size(self, text):
        sz = self._s.get(text)
        if sz is None:
            if len(self._s) > 2000:
                self._s.clear()
            sz = self._s[text] = self._f.size(text)
        return sz

    def __getattr__(self, name):
        return getattr(self._f, name)


def throttled(fn, interval):
    st = [-1e9, None]

    def get():
        now = time.monotonic()
        if now - st[0] >= interval:
            st[0], st[1] = now, fn()
        return st[1]
    return get


def bg_cached(fn, interval):
    """Return the last value of fn() at once; refresh it on a worker thread when stale so a slow
    /proc, sysfs or subprocess read never stalls a frame. The first call computes synchronously."""
    st = {"t": -1e9, "v": None, "busy": False, "init": False}

    def work():
        try:
            v = fn()
            st["v"] = v
        except Exception:
            pass
        finally:
            st["t"], st["busy"] = time.monotonic(), False

    def get(force=False):
        if not st["init"]:
            st["init"] = True
            st["v"], st["t"] = fn(), time.monotonic()
            return st["v"]
        if (force or time.monotonic() - st["t"] >= interval) and not st["busy"]:
            st["busy"] = True
            threading.Thread(target=work, daemon=True).start()
        return st["v"]
    return get


CLASSIC_UI = [False, 3]          # [active, pixel unit]; set every frame while the RG Classic launcher is selected
_CLASSIC_BG = [None, None]


def classic_unit():
    return max(2, int(W / rgclassic.LW + 0.5))


class PixelFont:
    """RG Classic bitmap font (Galla 5x9) scaled to a target pixel height; stands in for the TTF fonts."""

    def __init__(self, height):
        k = height / 9.0
        self.h, self.w, self.adv = height, max(3, int(round(5 * k))), max(4, int(round(6 * k)))
        self._g, self._r = {}, {}

    def _glyph(self, g, col):
        sf = self._g.get((g, col))
        if sf is None:
            base = pygame.Surface((5, 9), pygame.SRCALPHA)
            for y in range(9):
                for x in range(5):
                    if rgclassic.FONT[g][y] & (0x10 >> x):
                        base.set_at((x, y), col)
            sf = self._g[(g, col)] = pygame.transform.scale(base, (self.w, self.h))
        return sf

    def render(self, text, aa, color, *bg):
        col = (int(color[0]), int(color[1]), int(color[2]))
        surf = self._r.get((text, col))
        if surf is None:
            if len(self._r) > 900:
                for k in list(self._r)[:300]:
                    del self._r[k]
            surf = pygame.Surface((max(1, self.adv * len(text)), self.h), pygame.SRCALPHA)
            for i, ch in enumerate(text):
                if ch != " ":
                    surf.blit(self._glyph(rgclassic._glyph(ch), col), (i * self.adv, 0))
            self._r[(text, col)] = surf
        return surf

    def size(self, text):
        return (self.adv * len(text), self.h)

    def get_linesize(self):
        return self.h + 4

    def get_height(self):
        return self.h

    def get_ascent(self):
        return self.h - 2

    def get_descent(self):
        return 2


_pg_rect = pygame.draw.rect


def _cl_fill(surf, col, rect, u):
    """Filled rectangle with the stepped (notched) pixel corners of the RG Classic tiles."""
    x, y, w, h = [int(v) for v in rect]
    if w <= 0 or h <= 0:
        return
    u = min(u, w // 3, h // 3)
    if u < 1:
        _pg_rect(surf, col, (x, y, w, h))
        return
    _pg_rect(surf, col, (x + u, y, w - 2 * u, h))
    _pg_rect(surf, col, (x, y + u, w, h - 2 * u))


def _cl_box(surf, fill, edge, rect, u, b):
    x, y, w, h = [int(v) for v in rect]
    _cl_fill(surf, edge, (x, y, w, h), u)
    if w > 2 * b + 2 and h > 2 * b + 2:
        _cl_fill(surf, fill, (x + b, y + b, w - 2 * b, h - 2 * b), max(0, u - b) if u > b else 0)


def _cl_outline(surf, col, rect, t, u):
    x, y, w, h = [int(v) for v in rect]
    u = min(u, w // 3, h // 3)
    t = max(1, min(t, u or t))
    _pg_rect(surf, col, (x + u, y, w - 2 * u, t))
    _pg_rect(surf, col, (x + u, y + h - t, w - 2 * u, t))
    _pg_rect(surf, col, (x, y + u, t, h - 2 * u))
    _pg_rect(surf, col, (x + w - t, y + u, t, h - 2 * u))
    for cx, cy in ((x + max(0, u - t), y + max(0, u - t)), (x + w - u, y + max(0, u - t)),
                   (x + max(0, u - t), y + h - u), (x + w - u, y + h - u)):
        _pg_rect(surf, col, (cx, cy, t, t))


def _rect_shim(surf, col, rect, width=0, border_radius=0, *a, **kw):
    # RG Classic has no rounded corners: popups, keys and bars all pick up the notched pixel corners
    if CLASSIC_UI[0] and border_radius and border_radius > 0:
        if width and width > 0:
            _cl_outline(surf, col, pygame.Rect(rect), width, CLASSIC_UI[1])
        else:
            _cl_fill(surf, col, pygame.Rect(rect), CLASSIC_UI[1])
        return pygame.Rect(rect)
    return _pg_rect(surf, col, rect, width, border_radius, *a, **kw)


pygame.draw.rect = _rect_shim


def _classic_button(surf, rect, hl):
    u = CLASSIC_UI[1]
    b = max(2, u - 1)
    x, y, w, h = rect
    rc = rgclassic
    if w > 4 * u and h > 4 * u:
        _cl_fill(surf, rc.BLACK, (x + u // 2 + 1, y + u // 2 + 1, w, h), u)
    _cl_box(surf, _mix(rc.PANEL, rc.RED, hl), _mix(rc.REDM, rc.WHITE, hl), (x, y, w, h), u, b)
    if hl > 0.3 and w > 4 * u:
        _pg_rect(surf, rc.REDL, (x + u + b, y + b, w - 2 * (u + b), max(1, b // 2)))
    return hl


def draw_classic_header(canvas, f_logo):
    rc = rgclassic
    band = pygame.Surface((W, 64), pygame.SRCALPHA)
    band.fill(tuple(rc.BLACK) + (110,))
    canvas.blit(band, (0, 0))
    _pg_rect(canvas, rc.REDM, (0, 60, W, 2))
    _pg_rect(canvas, rc.BLACK, (0, 62, W, 2))
    rg = f_logo.render("RG", True, rc.RED)
    canvas.blit(rg, (20, (60 - rg.get_height()) // 2))
    canvas.blit(f_logo.render("OS", True, rc.WHITE), (20 + rg.get_width() + f_logo.adv // 2, (60 - rg.get_height()) // 2))


def draw_classic_footer(canvas, font, hint):
    rc, u = rgclassic, CLASSIC_UI[1]
    ch = font.get_height() + 6
    y = H - ch - 8
    band = pygame.Surface((W, H - y + 8), pygame.SRCALPHA)
    band.fill(tuple(rc.BLACK) + (110,))
    canvas.blit(band, (0, y - 8))
    _pg_rect(canvas, rc.REDM, (0, y - 8, W, 2))
    x = 16
    for seg in hint.split("   "):
        key, _, lab = seg.strip().partition(" ")
        if not key:
            continue
        if not lab:
            key, lab = "", key
        kt = font.render(key, True, rc.REDM) if key else None
        lt = font.render(lab, True, rc.WHITE)
        need = (kt.get_width() + 16 if kt else 0) + lt.get_width()
        if x + need > W - 8:
            break
        if kt:
            kw = kt.get_width() + 10
            _cl_box(canvas, rc.WHITE, rc.WHITE, (x, y, kw, ch), 2, 2)
            _pg_rect(canvas, rc.DIM, (x + 2, y + ch - 2, kw - 4, 2))
            canvas.blit(kt, (x + 5, y + 3))
            x += kw + 6
        canvas.blit(lt, (x, y + 3))
        x += lt.get_width() + 18


_BTN_CACHE = {}
_BTN_SHADOW = {}


def _btn_face(w, h, base, radius):
    key = (w, h, base, radius)
    surf = _BTN_CACHE.get(key)
    if surf is None:
        if len(_BTN_CACHE) > 600:
            _BTN_CACHE.clear()
        top, bot = _mix(base, (255, 255, 255), 0.16), _mix(base, (0, 0, 0), 0.12)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for yy in range(h):
            pygame.draw.line(surf, _mix(top, bot, yy / max(1, h - 1)), (0, yy), (w, yy))
        hl = _mix(base, (255, 255, 255), 0.35)
        pygame.draw.line(surf, hl, (radius, 1), (w - radius - 1, 1))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        _BTN_CACHE[key] = surf
    return surf


_BTN_ANIM = {}
ANIM_STEPS, ANIM_SPEED, LIFT_PX = 24, 16.0, 4
ANIM_DT = None
_anim_clock = [time.monotonic(), 1 / 30, False]


def anim_tick():
    now = time.monotonic()
    dt = ANIM_DT if ANIM_DT else min(0.05, max(0.001, now - _anim_clock[0]))
    _anim_clock[0], _anim_clock[1] = now, dt
    moving, _anim_clock[2] = _anim_clock[2], False
    return moving


XMB_UI = [False]
_GLASS = {}


def _glass_tint():
    return (255, 255, 255) if sum(BG) / 3.0 > 140 else (0, 0, 0)


def _glass_face(w, h, radius, col, alpha, outline=45):
    key = (w, h, radius, col, alpha, outline, tuple(TEXT))
    g = _GLASS.get(key)
    if g is None:
        if len(_GLASS) > 160:
            _GLASS.clear()
        g = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        pygame.draw.rect(g, tuple(col[:3]) + (alpha,), (0, 0, w, h), border_radius=radius)
        if outline:
            pygame.draw.rect(g, tuple(TEXT[:3]) + (outline,), (0, 0, w, h), 1, border_radius=radius)
        _GLASS[key] = g
    return g


def ui_rect(surf, col, rect, radius=0):
    if CLASSIC_UI[0]:
        rc, u = rgclassic, CLASSIC_UI[1]
        if col == SEL_BG:
            fill, edge = rc.RED, rc.WHITE
        elif col == PANEL:
            fill, edge = rc.PANEL, rc.REDM
        else:
            fill = edge = col
        _cl_box(surf, fill, edge, rect, u, max(2, u - 1))
        return
    if not XMB_UI[0]:
        pygame.draw.rect(surf, col, rect, border_radius=radius)
        return
    x, y, w, h = rect
    if col == SEL_BG:
        surf.blit(_glass_face(w, h, radius, SEL_BG, 175), (x, y))
    else:
        surf.blit(_glass_face(w, h, radius, _glass_tint(), 105), (x, y))


def draw_button(surf, rect, base, radius=12, depth=4, sel=False):
    x, y, w, h = rect
    st = _BTN_ANIM.get(rect)
    if st is None:
        if len(_BTN_ANIM) > 300:
            _BTN_ANIM.clear()
        st = _BTN_ANIM[rect] = [1.0 if sel else 0.0, base, base]
    st[1 if sel else 2] = base
    target = 1.0 if sel else 0.0
    if abs(st[0] - target) < 0.002:
        st[0] = target
    else:
        st[0] += (target - st[0]) * (1.0 - math.exp(-_anim_clock[1] * ANIM_SPEED))
        _anim_clock[2] = True
    e = st[0] * st[0] * (3.0 - 2.0 * st[0])
    hl = round(e * ANIM_STEPS) / ANIM_STEPS
    base = _mix(st[2], st[1], hl)
    lift = int(round(LIFT_PX * hl)) if h >= 80 and not CLASSIC_UI[0] else 0
    y -= lift
    if CLASSIC_UI[0]:
        return _classic_button(surf, (x, y, w, h), hl), 0
    if XMB_UI[0]:
        surf.blit(_glass_face(w, h, radius, _mix(_glass_tint(), SEL_BG, hl), 105 + int(70 * hl)), (x, y))
        if hl > 0:
            pygame.draw.rect(surf, _mix(TEXT, ACCENT, hl), (x, y, w, h), 2 if h < 80 else 3, border_radius=radius)
        return hl, lift
    side = _mix(base, (0, 0, 0), 0.55)
    skey = (w, h, depth, radius)
    sh = _BTN_SHADOW.get(skey)
    if sh is None:
        if len(_BTN_SHADOW) > 200:
            _BTN_SHADOW.clear()
        sh = _BTN_SHADOW[skey] = pygame.Surface((w, h + depth + 3), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, 70), (0, 3, w, h + depth), border_radius=radius)
    surf.blit(sh, (x, y + lift))
    pygame.draw.rect(surf, side, (x, y + depth, w, h), border_radius=radius)
    surf.blit(_btn_face(w, h, base, radius), (x, y))
    if hl > 0:
        pygame.draw.rect(surf, _mix(base, ACCENT, hl), (x, y, w, h), 2 if h < 80 else 3, border_radius=radius)
    return hl, lift


HOME_COLS = 2
HOME_ITEMS = [("games", "Games"), ("recents", "Recents"), ("favorites", "Favorites"), ("tools", "Tools"), ("settings", "Settings"), ("power", "Power Off")]
TOOLS = [("files", "File Manager", "Browse, copy, move, rename and delete files on the SD cards", "@view:files"),
         ("portmaster", "PortMaster", "Browse, install and update native Linux game ports", "@tool:portmaster"),
         ("coreinstall", "Core Installer", "Download RetroArch cores for your systems", "@view:coreinstall"),
         ("retroarch", "RetroArch", "Open the RetroArch menu (cores, content, settings)", "@tool:retroarch")]
BOOT_ROOT = "/boot"
BOOT_PROTECTED = ("SYSTEM", "SYSTEM.md5", "KERNEL", "KERNEL.md5", "extlinux", "dtbs", "device_trees", "boot.ini",
                  "rgos-data", "boot.scr", "Image", "uInitrd", "initrd", "initrd.img", "u-boot.bin", "idbloader.img",
                  "trust.img", "uboot.img", "rgos-initrd.cpio")


def fm_roots():
    roots = []
    if os.path.ismount(BOOT_ROOT):
        roots.append(BOOT_ROOT)
    sd = load_json("/etc/rgos/sdcard.json", {"enabled": True, "mountpoint": "/media/roms2"})
    mp = sd.get("mountpoint", "/media/roms2")
    if sd.get("enabled", True) and mp and os.path.ismount(mp):
        roots.append(mp)
    roots.append(ROMS_ROOT)
    return roots


def make_file_manager():
    return filemanager.FileManager(fm_roots(), labels={BOOT_ROOT: "RGOS", ROMS_ROOT: "ROMS"},
                                   protected={BOOT_ROOT: BOOT_PROTECTED, ROMS_ROOT: ("rgos-data",)})


FM_ROWS = 7 + DY // 44
SETTINGS_ROWS = ["theme", "launcher", "splash", "emulators", "bios", "artwork", "bmap", "swapab", "dpadjoy", "wifi", "bluetooth", "ssh", "info"]
RECENT_MAX = 20

LAUNCHERS = [("rgos", "RG OS", "Classic tile launcher"), ("xmb", "RG XMB", "PlayStation-style cross media bar"),
             ("flow", "RG Flow", "Carousels: menu, systems, games"),
             ("rgclassic", "RG Classic", "Pixel launcher: tiles, lists and menus"),
             ("steamos", "SteamOS", "Steam Deck gaming mode: hero backdrop, capsule row, Play button, MENU side panel")]
DEFAULT_LAUNCHER = LAUNCHERS[0][0]


def launcher_index(lid):
    for i, l in enumerate(LAUNCHERS):
        if l[0] == lid:
            return i
    return 0


def dd_options(kind):
    if kind == "theme":
        return [(t[0], t[1], [t[2][k] for k in ("BG", "PANEL", "SEL_BG", "ACCENT", "TEXT")], "") for t in THEMES]
    return [(l[0], l[1], None, l[2]) for l in LAUNCHERS]


XMB_CATS = [("settings", "Settings"), ("games", "Games"), ("recents", "Recents"), ("favorites", "Favorites"), ("tools", "Tools"), ("power", "Power")]
XMB_START = 1


def icon_games(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 36, cy - 20, 72, 40), border_radius=18)
    pygame.draw.rect(c, bg, (cx - 25, cy - 3, 16, 6), border_radius=2)
    pygame.draw.rect(c, bg, (cx - 20, cy - 8, 6, 16), border_radius=2)
    pygame.draw.circle(c, bg, (cx + 14, cy + 4), 5)
    pygame.draw.circle(c, bg, (cx + 25, cy - 4), 5)


def icon_recents(c, cx, cy, col, bg):
    pygame.draw.circle(c, col, (cx, cy), 27, 4)
    pygame.draw.line(c, col, (cx, cy), (cx, cy - 16), 4)
    pygame.draw.line(c, col, (cx, cy), (cx + 12, cy + 7), 4)
    pygame.draw.circle(c, col, (cx, cy), 4)


def icon_favorites(c, cx, cy, col, bg):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = 29 if i % 2 == 0 else 13
        pts.append((int(cx + math.cos(ang) * rad), int(cy + math.sin(ang) * rad)))
    pygame.draw.polygon(c, col, pts)


def icon_power(c, cx, cy, col, bg):
    r, t = 24, 5
    cy += 3
    pts = [(cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a))) for a in range(38, 323, 4)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        pygame.draw.line(c, col, (x1, y1), (x2, y2), t)
    for x, y in pts:
        pygame.draw.circle(c, col, (int(x), int(y)), t // 2)
    pygame.draw.line(c, col, (cx, cy - r - 4), (cx, cy - 4), t)
    pygame.draw.circle(c, col, (cx, cy - r - 4), t // 2)
    pygame.draw.circle(c, col, (cx, cy - 4), t // 2)


def icon_settings(c, cx, cy, col, bg):
    for y, kx in ((cy - 18, cx - 10), (cy, cx + 14), (cy + 18, cx - 2)):
        pygame.draw.line(c, col, (cx - 32, y), (cx + 32, y), 4)
        pygame.draw.circle(c, col, (kx, y), 8)
        pygame.draw.circle(c, bg, (kx, y), 3)


def icon_tools(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 34, cy - 6, 68, 12), border_radius=4)
    pygame.draw.circle(c, col, (cx - 30, cy), 14)
    pygame.draw.circle(c, bg, (cx - 30, cy), 7)
    pygame.draw.rect(c, bg, (cx - 46, cy - 4, 18, 8))
    pygame.draw.circle(c, col, (cx + 34, cy), 6)
    pygame.draw.circle(c, bg, (cx + 34, cy), 2)


def icon_theme(c, cx, cy, col, bg):
    pygame.draw.circle(c, col, (cx, cy), 28)
    for dx, dy in ((-13, -9), (3, -17), (17, -4)):
        pygame.draw.circle(c, bg, (cx + dx, cy + dy), 5)
    pygame.draw.circle(c, bg, (cx + 10, cy + 16), 8)


def icon_launcher(c, cx, cy, col, bg):
    for dx in (-27, 3):
        for dy in (-27, 3):
            pygame.draw.rect(c, col, (cx + dx, cy + dy, 24, 24), border_radius=6)


def icon_splash(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 32, cy - 22, 64, 44), border_radius=8)
    pygame.draw.polygon(c, bg, [(cx - 8, cy - 12), (cx - 8, cy + 12), (cx + 14, cy)])


def icon_emulators(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 20, cy - 20, 40, 40), border_radius=6)
    pygame.draw.rect(c, bg, (cx - 10, cy - 10, 20, 20), border_radius=3)
    for i in (-1, 0, 1):
        pygame.draw.rect(c, col, (cx - 32, cy + i * 14 - 2, 10, 4))
        pygame.draw.rect(c, col, (cx + 22, cy + i * 14 - 2, 10, 4))
        pygame.draw.rect(c, col, (cx + i * 14 - 2, cy - 32, 4, 10))
        pygame.draw.rect(c, col, (cx + i * 14 - 2, cy + 22, 4, 10))


def icon_bios(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 24, cy - 20, 48, 40), border_radius=6)
    pygame.draw.rect(c, bg, (cx - 16, cy - 12, 32, 24), border_radius=3)
    pygame.draw.line(c, col, (cx - 8, cy), (cx - 2, cy + 6), 4)
    pygame.draw.line(c, col, (cx - 2, cy + 6), (cx + 9, cy - 7), 4)
    for i in (-1, 0, 1):
        pygame.draw.rect(c, col, (cx + i * 14 - 2, cy + 20, 4, 8))


def icon_artwork(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 28, cy - 22, 56, 44), border_radius=6)
    pygame.draw.rect(c, bg, (cx - 22, cy - 16, 44, 32), border_radius=3)
    pygame.draw.polygon(c, col, [(cx - 22, cy + 16), (cx - 8, cy - 2), (cx + 2, cy + 8), (cx + 10, cy), (cx + 22, cy + 16)])
    pygame.draw.circle(c, col, (cx + 11, cy - 8), 4)


def icon_bmap(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 10, cy - 30, 20, 60), border_radius=4)
    pygame.draw.rect(c, col, (cx - 30, cy - 10, 60, 20), border_radius=4)
    pygame.draw.circle(c, bg, (cx, cy), 5)


def icon_swapab(c, cx, cy, col, bg):
    pygame.draw.line(c, col, (cx - 28, cy - 12), (cx + 18, cy - 12), 5)
    pygame.draw.polygon(c, col, [(cx + 16, cy - 24), (cx + 34, cy - 12), (cx + 16, cy)])
    pygame.draw.line(c, col, (cx + 28, cy + 12), (cx - 18, cy + 12), 5)
    pygame.draw.polygon(c, col, [(cx - 16, cy), (cx - 34, cy + 12), (cx - 16, cy + 24)])


def icon_dpadjoy(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 8, cy - 28, 16, 56), border_radius=3)
    pygame.draw.rect(c, col, (cx - 28, cy - 8, 56, 16), border_radius=3)
    pygame.draw.circle(c, bg, (cx, cy), 9)
    pygame.draw.circle(c, col, (cx, cy), 9, 3)


def icon_wifi(c, cx, cy, col, bg):
    for r in (14, 26, 38):
        pygame.draw.arc(c, col, (cx - r, cy + 16 - r, 2 * r, 2 * r), math.radians(45), math.radians(135), 5)
    pygame.draw.circle(c, col, (cx, cy + 16), 5)


def icon_bluetooth(c, cx, cy, col, bg):
    pts = [(cx - 14, cy - 12), (cx + 14, cy + 12), (cx, cy + 26), (cx, cy - 26), (cx + 14, cy - 12), (cx - 14, cy + 12)]
    pygame.draw.lines(c, col, False, pts, 5)


def icon_ssh(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 34, cy - 24, 68, 48), 4, border_radius=6)
    pygame.draw.lines(c, col, False, [(cx - 20, cy - 10), (cx - 8, cy), (cx - 20, cy + 10)], 4)
    pygame.draw.line(c, col, (cx, cy + 10), (cx + 16, cy + 10), 4)


def icon_info(c, cx, cy, col, bg):
    pygame.draw.circle(c, col, (cx, cy), 28, 4)
    pygame.draw.circle(c, col, (cx, cy - 13), 4)
    pygame.draw.line(c, col, (cx, cy - 4), (cx, cy + 15), 5)


def icon_files(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 32, cy - 22, 28, 12), border_radius=4)
    pygame.draw.rect(c, col, (cx - 32, cy - 14, 64, 40), border_radius=6)


ICONS = {"games": icon_games, "recents": icon_recents, "favorites": icon_favorites, "tools": icon_tools, "settings": icon_settings, "power": icon_power,
         "theme": icon_theme, "launcher": icon_launcher, "splash": icon_splash, "emulators": icon_emulators, "bios": icon_bios, "artwork": icon_artwork, "bmap": icon_bmap,
         "swapab": icon_swapab, "dpadjoy": icon_dpadjoy, "wifi": icon_wifi, "bluetooth": icon_bluetooth, "ssh": icon_ssh, "info": icon_info, "files": icon_files}


# ---- per-system icons (RG XMB list, RG Flow system cards) --------------------------------------------------------
# Same convention as the icons above: drawn white-on-transparent around (cx, cy) inside a 96x96 box, `bg` cuts details out
# of the body. Generic shapes (handheld, pad, cartridge, ...), deliberately not console logos.

def _cross(c, bg, x, y, a=7, t=4):
    pygame.draw.rect(c, bg, (x - a, y - t // 2, 2 * a, t))
    pygame.draw.rect(c, bg, (x - t // 2, y - a, t, 2 * a))


def _dots(c, bg, pts, r=3):
    for x, y in pts:
        pygame.draw.circle(c, bg, (x, y), r)


def _screen(c, col, bg, x, y, w, h, colour=False):
    """A handheld's screen: bezel cut out of the body, then the glass (four colour tiles for the colour models)."""
    pygame.draw.rect(c, bg, (x, y, w, h), border_radius=2)
    if colour:
        tw, th = (w - 11) // 2, (h - 11) // 2
        for i in range(2):
            for j in range(2):
                pygame.draw.rect(c, col, (x + 4 + i * (tw + 3), y + 4 + j * (th + 3), tw, th))
    else:
        pygame.draw.rect(c, col, (x + 4, y + 4, w - 8, h - 8))


def icon_sys_gba(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 36, cy - 24, 12, 7), border_radius=3)
    pygame.draw.rect(c, col, (cx + 24, cy - 24, 12, 7), border_radius=3)
    pygame.draw.rect(c, col, (cx - 40, cy - 19, 80, 38), border_radius=14)
    _screen(c, col, bg, cx - 18, cy - 12, 36, 24)
    _cross(c, bg, cx - 29, cy, 6, 4)
    _dots(c, bg, [(cx + 25, cy + 4), (cx + 33, cy - 3)])


def _gb_body(c, cx, cy, col, bg, colour):
    pygame.draw.rect(c, col, (cx - 23, cy - 38, 46, 76), border_radius=5, border_bottom_right_radius=16)
    _screen(c, col, bg, cx - 17, cy - 33, 34, 28, colour)
    _cross(c, bg, cx - 9, cy + 14, 7, 4)
    _dots(c, bg, [(cx + 8, cy + 19), (cx + 15, cy + 11)], 4)
    for i in range(3):
        pygame.draw.line(c, bg, (cx + 3 + i * 5, cy + 33), (cx + 9 + i * 5, cy + 26), 2)


def icon_sys_gb(c, cx, cy, col, bg):
    _gb_body(c, cx, cy, col, bg, False)


def icon_sys_gbc(c, cx, cy, col, bg):
    _gb_body(c, cx, cy, col, bg, True)


def icon_sys_nes(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 40, cy - 17, 80, 34), border_radius=3)
    pygame.draw.rect(c, bg, (cx - 35, cy - 11, 70, 22), border_radius=2)
    pygame.draw.rect(c, col, (cx - 31, cy - 2, 14, 4))
    pygame.draw.rect(c, col, (cx - 26, cy - 7, 4, 14))
    pygame.draw.rect(c, col, (cx - 9, cy + 1, 9, 4), border_radius=2)
    pygame.draw.rect(c, col, (cx + 3, cy + 1, 9, 4), border_radius=2)
    pygame.draw.circle(c, col, (cx + 20, cy + 2), 4)
    pygame.draw.circle(c, col, (cx + 30, cy + 2), 4)


def icon_sys_snes(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 40, cy - 16, 80, 32), border_radius=16)
    _cross(c, bg, cx - 25, cy, 7, 4)
    _dots(c, bg, [(cx + 25, cy - 7), (cx + 25, cy + 7), (cx + 18, cy), (cx + 32, cy)], 3)
    pygame.draw.rect(c, bg, (cx - 8, cy + 3, 8, 3), border_radius=1)
    pygame.draw.rect(c, bg, (cx + 2, cy + 3, 8, 3), border_radius=1)


def icon_sys_genesis(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 40, cy - 17, 80, 34), border_radius=13)
    _cross(c, bg, cx - 24, cy, 7, 4)
    _dots(c, bg, [(cx + 4, cy + 8), (cx + 16, cy + 4), (cx + 28, cy)], 4)
    pygame.draw.rect(c, bg, (cx - 8, cy - 11, 10, 4), border_radius=2)


def icon_sys_mastersystem(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 29, cy - 36, 58, 72), border_radius=5)
    pygame.draw.polygon(c, bg, [(cx - 30, cy - 37), (cx - 18, cy - 37), (cx - 30, cy - 25)])
    pygame.draw.rect(c, bg, (cx - 21, cy - 27, 42, 36), border_radius=3)
    pygame.draw.rect(c, col, (cx - 16, cy - 22, 32, 26), border_radius=2)
    for i in range(6):
        pygame.draw.rect(c, bg, (cx - 21 + i * 8, cy + 17, 5, 14))


def icon_sys_gamegear(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 43, cy - 21, 86, 42), border_radius=10)
    _screen(c, col, bg, cx - 25, cy - 14, 50, 28)
    _cross(c, bg, cx - 34, cy - 2, 5, 4)
    _dots(c, bg, [(cx + 34, cy - 4), (cx + 34, cy + 6)], 3)


def icon_sys_sg1000(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 26, cy + 8, 52, 24), border_radius=7)
    pygame.draw.line(c, col, (cx, cy + 10), (cx, cy - 16), 8)
    pygame.draw.circle(c, col, (cx, cy - 22), 12)
    pygame.draw.circle(c, bg, (cx + 14, cy + 20), 4)
    pygame.draw.rect(c, bg, (cx - 18, cy + 18, 20, 4), border_radius=2)


def icon_sys_segacd(c, cx, cy, col, bg):
    pygame.draw.circle(c, col, (cx, cy - 7), 30)
    pygame.draw.circle(c, bg, (cx, cy - 7), 17, 2)
    pygame.draw.circle(c, bg, (cx, cy - 7), 8)
    pygame.draw.rect(c, col, (cx - 40, cy + 27, 80, 9), border_radius=4)


def icon_sys_sega32x(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 19, cy - 36, 38, 40), border_radius=4)
    pygame.draw.rect(c, bg, (cx - 13, cy - 30, 26, 16), border_radius=2)
    pygame.draw.rect(c, bg, (cx - 42, cy + 1, 84, 4))
    pygame.draw.rect(c, col, (cx - 40, cy + 6, 80, 28), border_radius=5)
    pygame.draw.rect(c, bg, (cx - 30, cy + 16, 34, 4), border_radius=2)
    pygame.draw.circle(c, bg, (cx + 28, cy + 20), 4)


def icon_sys_segapico(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 40, cy - 23, 80, 46), border_radius=8)
    pygame.draw.rect(c, bg, (cx - 33, cy - 16, 44, 32), border_radius=3)
    pygame.draw.line(c, col, (cx - 24, cy + 9), (cx - 4, cy - 9), 4)
    pygame.draw.circle(c, col, (cx - 24, cy + 9), 3)
    _dots(c, bg, [(cx + 26, cy - 9), (cx + 26, cy + 4)], 4)
    pygame.draw.rect(c, bg, (cx + 17, cy + 12, 18, 3), border_radius=1)


def icon_sys_atari2600(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 40, cy - 4, 80, 28), border_radius=4)
    pygame.draw.polygon(c, col, [(cx - 34, cy - 3), (cx - 26, cy - 24), (cx + 26, cy - 24), (cx + 34, cy - 3)])
    for i in range(3):
        pygame.draw.rect(c, bg, (cx - 22, cy - 19 + i * 6, 44, 3))
    for x in (-33, -21, 11, 23):
        pygame.draw.rect(c, bg, (cx + x, cy + 8, 10, 5), border_radius=2)


def icon_sys_atari5200(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 25, cy - 36, 50, 72), border_radius=10)
    pygame.draw.circle(c, bg, (cx, cy - 23), 10)
    pygame.draw.circle(c, col, (cx, cy - 23), 5)
    for r in range(4):
        for k in range(3):
            pygame.draw.rect(c, bg, (cx - 17 + k * 12, cy - 6 + r * 9, 10, 6), border_radius=1)


def icon_sys_atari7800(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 17, cy - 30, 34, 26), border_radius=3)
    pygame.draw.rect(c, bg, (cx - 11, cy - 24, 22, 8), border_radius=2)
    pygame.draw.rect(c, bg, (cx - 42, cy - 5, 84, 3))
    pygame.draw.rect(c, col, (cx - 40, cy - 2, 80, 32), border_radius=5)
    pygame.draw.circle(c, bg, (cx - 22, cy + 14), 7)
    pygame.draw.circle(c, bg, (cx + 22, cy + 14), 7)
    pygame.draw.circle(c, col, (cx - 22, cy + 14), 3)
    pygame.draw.circle(c, col, (cx + 22, cy + 14), 3)


def icon_sys_ngp(c, cx, cy, col, bg, colour=False):
    pygame.draw.rect(c, col, (cx - 40, cy - 22, 80, 44), border_radius=11)
    _screen(c, col, bg, cx - 17, cy - 14, 34, 28, colour)
    pygame.draw.circle(c, bg, (cx - 28, cy), 8)
    pygame.draw.circle(c, col, (cx - 28, cy), 4)
    _dots(c, bg, [(cx + 26, cy + 5), (cx + 33, cy - 3)], 3)


def icon_sys_ngpc(c, cx, cy, col, bg):
    icon_sys_ngp(c, cx, cy, col, bg, True)


def icon_sys_ws(c, cx, cy, col, bg, colour=False):
    pygame.draw.rect(c, col, (cx - 42, cy - 19, 84, 38), border_radius=9)
    _screen(c, col, bg, cx - 16, cy - 12, 32, 24, colour)
    _cross(c, bg, cx - 29, cy, 5, 3)
    _cross(c, bg, cx + 29, cy, 5, 3)


def icon_sys_wsc(c, cx, cy, col, bg):
    icon_sys_ws(c, cx, cy, col, bg, True)


def icon_sys_psx(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 31, cy - 19, 62, 30), border_radius=11)
    pygame.draw.rect(c, col, (cx - 42, cy - 5, 24, 32), border_radius=11)
    pygame.draw.rect(c, col, (cx + 18, cy - 5, 24, 32), border_radius=11)
    _cross(c, bg, cx - 22, cy - 5, 7, 4)
    _dots(c, bg, [(cx + 22, cy - 12), (cx + 22, cy + 2), (cx + 15, cy - 5), (cx + 29, cy - 5)], 3)
    pygame.draw.rect(c, bg, (cx - 9, cy - 6, 6, 3))
    pygame.draw.rect(c, bg, (cx + 3, cy - 6, 6, 3))


def icon_sys_gc(c, cx, cy, col, bg):
    pygame.draw.polygon(c, col, [(cx, cy - 32), (cx + 30, cy - 16), (cx, cy), (cx - 30, cy - 16)])
    pygame.draw.polygon(c, col, [(cx - 30, cy - 16), (cx, cy), (cx, cy + 34), (cx - 30, cy + 18)])
    pygame.draw.polygon(c, col, [(cx, cy), (cx + 30, cy - 16), (cx + 30, cy + 18), (cx, cy + 34)])
    pygame.draw.lines(c, bg, False, [(cx - 30, cy - 16), (cx, cy), (cx + 30, cy - 16)], 3)
    pygame.draw.line(c, bg, (cx, cy), (cx, cy + 34), 3)
    pygame.draw.circle(c, bg, (cx, cy - 16), 6)
    pygame.draw.circle(c, col, (cx, cy - 16), 2)


def icon_sys_arcade(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 24, cy - 39, 48, 78), border_radius=4)
    pygame.draw.rect(c, col, (cx - 36, cy + 4, 72, 16), border_radius=4)
    pygame.draw.rect(c, bg, (cx - 17, cy - 34, 34, 5), border_radius=1)
    pygame.draw.rect(c, bg, (cx - 17, cy - 24, 34, 24), border_radius=3)
    pygame.draw.circle(c, bg, (cx - 17, cy + 12), 4)
    _dots(c, bg, [(cx + 2, cy + 12), (cx + 13, cy + 12), (cx + 24, cy + 12)], 3)
    pygame.draw.rect(c, bg, (cx - 9, cy + 26, 18, 8), border_radius=2)


def icon_sys_neogeo(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 40, cy - 8, 80, 38), border_radius=8)
    pygame.draw.line(c, col, (cx - 22, cy - 8), (cx - 22, cy - 22), 5)
    pygame.draw.circle(c, col, (cx - 22, cy - 28), 9)
    pygame.draw.circle(c, bg, (cx - 22, cy + 8), 8, 2)
    _dots(c, bg, [(cx + 1 + i * 11, cy + 17 - i * 3) for i in range(4)], 4)


def icon_sys_ports(c, cx, cy, col, bg):
    pygame.draw.rect(c, col, (cx - 20, cy - 8, 40, 32), border_radius=7)
    pygame.draw.rect(c, col, (cx - 12, cy - 30, 7, 24), border_radius=2)
    pygame.draw.rect(c, col, (cx + 5, cy - 30, 7, 24), border_radius=2)
    pygame.draw.line(c, col, (cx, cy + 22), (cx, cy + 38), 9)
    pygame.draw.rect(c, bg, (cx - 10, cy + 4, 20, 4), border_radius=2)


SYSTEM_ICONS = {n[len("icon_sys_"):]: f for n, f in list(globals().items()) if n.startswith("icon_sys_")}
ICONS.update({"sys_" + sid: fn for sid, fn in SYSTEM_ICONS.items()})


def system_icon(sid):
    """ICONS key of a system's icon; systems without their own icon (a new SYSTEMS row) keep the generic pad."""
    return "sys_" + sid if "sys_" + sid in ICONS else "games"


_XI = {}
_XIT = {}
_XBG = {}
_XBG_RAW = [None]
_XSILK = {}
_XFRAME = [None, -1.0, None, None, -1.0]  # front surface, its time, in-flight redraw job, back surface, that job's time
# The silk is redrawn in pure Python (~20+ ms on the H700). That used to land in a single frame, right as navigation
# settled (or every few seconds while a direction was held), and showed up as a hitch. Now the redraw is time-sliced:
# one ribbon bundle per frame into a back buffer that is swapped in when complete, and it is paused entirely while the
# menu is animating or was just touched, so scrolling never pays for the silk. Idle it still refreshes at 15 fps.
XMB_BG_INTERVAL = 1.0 / 15.0
XMB_BG_MOVING_MAX = 8.0
XMB_BG_SETTLE = 0.6
XMB_BG_BUDGET = 0.008


def xmb_icon(kind, size, color, alpha=1.0):
    ck = tuple(min(255, (int(v) + 4) & ~7) for v in color[:3])
    a8 = int(alpha * 255) if alpha < 0.99 else 255
    aq = 255 if a8 >= 250 else max(0, a8) & ~7
    key = (kind, size, ck, aq)
    t = _XIT.get(key)
    if t is not None:
        return t
    base = _XI.get(kind)
    if base is None:
        base = pygame.Surface((96, 96), pygame.SRCALPHA)
        ICONS[kind](base, 48, 48, (255, 255, 255, 255), (0, 0, 0, 0))
        _XI[kind] = base
    sc = _XI.get((kind, size))
    if sc is None:
        sc = _XI[(kind, size)] = pygame.transform.smoothscale(base, (size, size))
    t = sc.copy()
    t.fill(ck + (255,), special_flags=pygame.BLEND_RGBA_MULT)
    if aq < 255:
        t.set_alpha(aq)
    if len(_XIT) > 900:
        for k in list(_XIT)[:300]:
            del _XIT[k]
    _XIT[key] = t
    return t


def _xq(col):
    return tuple(min(255, (int(v) + 4) & ~7) for v in col[:3])


def _smooth_damp(pos, vel, target, dt, omega=22.0):
    e = math.exp(-omega * dt)
    err = pos - target
    tmp = (vel + omega * err) * dt
    vel = (vel - omega * tmp) * e
    pos = target + (err + tmp) * e
    if abs(pos - target) < 0.002 and abs(vel) < 0.02:
        return float(target), 0.0
    return pos, vel


_XMB_SILK = ((0.68, 0.43, 16, 0.0085, 0.22, 48, 0.0060, 0.10, 0.4, 18, 0.55),
             (0.77, 0.58, 12, 0.0110, -0.18, 34, 0.0075, -0.12, 2.6, 12, 0.36))
_XMB_SPARKS = []


def xmb_tint(x, y, k):
    raw = _XBG_RAW[0]
    if raw is None:
        base = BG
    else:
        i = (max(0, min(H - 1, int(y))) * W + max(0, min(W - 1, int(x)))) * 3
        base = (raw[i], raw[i + 1], raw[i + 2])
    return _mix(base, TEXT, k)


def _xmb_silk_build(g):
    hl = XMB_SILK
    xs = list(range(0, W + 10, 10))
    wig = ([math.sin(x * 0.021) for x in xs], [math.cos(x * 0.021) for x in xs])
    bundles = []
    for yl, yr, amp, kf, sp, th, kt, st, ph, n, br in _XMB_SILK:
        yb, s1, k1, s2, k2, s3, k3 = [], [], [], [], [], [], []
        for x in xs:
            u = x / float(W)
            yb.append(H * (yl + (yr - yl) * u * u * (3 - 2 * u)))
            p1, p2, p3 = x * kf + ph, x * kf * 2.3, x * kt + ph
            s1.append(math.sin(p1)); k1.append(math.cos(p1))
            s2.append(math.sin(p2)); k2.append(math.cos(p2))
            s3.append(math.sin(p3)); k3.append(math.cos(p3))
        base = g.get_at((W // 3, min(H - 1, int(H * (yl + yr) / 2))))[:3]
        strands = []
        for k in range(n):
            f = k / float(n - 1) * 2.0 - 1.0
            strands.append((f, math.cos(k * 0.9), math.sin(k * 0.9),
                            _mix(base, hl, br * (0.30 + 0.45 * max(0.0, -f) + 0.15 * (1.0 - abs(f))))))
        bundles.append((yb, s1, k1, s2, k2, s3, k3, amp, sp, th, st, strands, _mix(base, hl, 0.12 * br / 0.55), _mix(base, hl, min(1.0, br * 1.5))))
    return xs, wig, bundles


def xmb_bg(c, t, moving=False):
    key = (XMB_TOP, XMB_LOW, XMB_SILK, W, H)
    g = _XBG.get(key)
    if g is None:
        _XBG.clear()
        _XBG_RAW[0] = None
        _XFRAME[:] = [None, -1.0, None, None, -1.0]
        gw, gh = 24, 16
        small = pygame.Surface((gw, gh))
        top, low = XMB_TOP, XMB_LOW
        for gy in range(gh):
            for gx in range(gw):
                v = 0.30 * (gx + 0.5) / gw + 0.70 * (gy + 0.5) / gh
                pygame.draw.rect(small, _mix(top, low, v ** 1.15), (gx, gy, 1, 1))
        g = pygame.transform.smoothscale(small, (W, H))
        _XBG[key] = g
        _XSILK.clear()
        _XSILK["geo"] = _xmb_silk_build(g)
        try:
            _XBG_RAW[0] = (getattr(pygame.image, "tobytes", None) or pygame.image.tostring)(g, "RGB")
        except Exception:
            _XBG_RAW[0] = None
        if not _XMB_SPARKS:
            r = random.Random(11)
            for i in range(36):
                _XMB_SPARKS.append((r.uniform(0, W), (r.uniform(0.10, 0.98) if i % 3 else r.uniform(0.40, 0.85)) * H,
                                    r.uniform(3, 12), r.uniform(0, 6.28), 2 if r.random() < 0.8 else 3))
    fr = _XFRAME
    if fr[0] is None:
        fr[0] = g.copy()
        for _ in _xmb_silk_steps(g, fr[0], t):
            pass
        fr[1] = t
    else:
        age = t - fr[1]
        if fr[2] is None and not 0.0 <= age < (XMB_BG_MOVING_MAX if moving else XMB_BG_INTERVAL):
            if fr[3] is None:
                fr[3] = g.copy()
            fr[2], fr[4] = _xmb_silk_steps(g, fr[3], t), t
        # Advance an in-flight redraw: at rest as many bundles as fit in a small time budget (a fast CPU finishes in one
        # frame, the H700 spreads it over a few); while navigating only one bundle per frame, and only once the frame is stale.
        if fr[2] is not None and (not moving or not 0.0 <= age < XMB_BG_MOVING_MAX):
            budget = 0.0 if moving else XMB_BG_BUDGET
            t0 = time.perf_counter()
            try:
                while True:
                    next(fr[2])
                    if time.perf_counter() - t0 >= budget:
                        break
            except StopIteration:
                fr[0], fr[3] = fr[3], fr[0]
                fr[1], fr[2] = fr[4], None
    c.blit(fr[0], (0, 0))
    for x0, y0, spd, ph, sz in _XMB_SPARKS:
        x, y = (x0 + t * spd) % W, y0 + 4 * math.sin(t * 0.4 + ph)
        pygame.draw.rect(c, xmb_tint(x, y, 0.22 + 0.55 * (0.5 + 0.5 * math.sin(t * 1.6 + ph))), (int(x), int(y), sz, sz))


def _xmb_silk_steps(g, f, t):
    """Draw the silk for time t onto f, yielding after the background reset and after each bundle."""
    f.blit(g, (0, 0))
    yield
    xs, (sx0, cx0), bundles = _XSILK["geo"]
    cw, sw = math.cos(t * 0.35), math.sin(t * 0.35)
    S = [a * cw + b * sw for a, b in zip(sx0, cx0)]
    C = [b * cw - a * sw for a, b in zip(sx0, cx0)]
    for yb, s1, k1, s2, k2, s3, k3, amp, sp, th, st, strands, poly_col, edge_col in bundles:
        c1, d1 = math.cos(t * sp), math.sin(t * sp)
        c2, d2 = math.cos(t * sp * 0.8), math.sin(t * sp * 0.8)
        c3, d3 = math.cos(t * st), math.sin(t * st)
        amp2 = amp * 0.5
        rows = []
        for x, y0, a1, b1, a2, b2, a3, b3, sn, cs in zip(xs, yb, s1, k1, s2, k2, s3, k3, S, C):
            tw = 0.5 + 0.5 * (a3 * c3 + b3 * d3)
            h = th * (0.10 + 0.90 * tw * tw)
            rows.append((x, y0 + amp * (a1 * c1 + b1 * d1) + amp2 * (a2 * c2 - b2 * d2), h, 0.09 * h * sn, 0.09 * h * cs))
        upper = [(x, yc - h) for x, yc, h, _s, _c in rows]
        pygame.draw.polygon(f, poly_col, upper + [(x, yc + h) for x, yc, h, _s, _c in rows][::-1])
        for sf, sck, ssk, col in strands:
            pygame.draw.aalines(f, col, False, [(x, yc + h * sf + hs * sck + hc * ssk) for x, yc, h, hs, hc in rows])
        pygame.draw.lines(f, edge_col, False, upper, 2)
        yield


def draw_xmb_home(c, f_row, f_small, cx_f, cat_i, items, vy, fade):
    ax, bar_y, big, small, sp_x = 170, int(H * 0.26), 76, 50, 118
    sp, gap = 56 + max(0, H - 480) // 10, 16
    for i, (cid, cname) in enumerate(XMB_CATS):
        d = i - cx_f
        x = int(round(ax + d * sp_x + max(-1.0, min(1.0, d)) * 24))
        if x < -60 or x > W + 60:
            continue
        t = max(0.0, 1.0 - abs(d))
        t = t * t * (3.0 - 2.0 * t)
        size = int(round((small + (big - small) * t) / 4.0)) * 4
        if t > 0.05:
            pygame.draw.circle(c, xmb_tint(x, bar_y, 0.09 * t), (x, bar_y), int(size * 0.62))
        c.blit(xmb_icon(cid, size, _mix(DIM, TEXT, t), 0.5 + 0.5 * t), (x - size // 2, bar_y - size // 2))
        if t > 0.3:
            lab = f_row.render(cname, True, _xq(_mix(BG, TEXT, t)))
            c.blit(lab, (x - lab.get_width() // 2, bar_y + big // 2 + 8))
    colx = int(round(ax + (cat_i - cx_f) * sp_x))
    y0 = bar_y + big // 2 + 8 + 26 + sp // 2 + 6
    for i, it in enumerate(items):
        d = i - vy
        if d < -1.0 or d > 7.0:
            continue
        y = y0 + d * sp + max(-1.0, min(1.0, d)) * gap
        if y > H - 40:
            continue
        sel_t = max(0.0, 1.0 - abs(d))
        sel_t = sel_t * sel_t * (3.0 - 2.0 * sel_t)
        al = (1.0 + min(0.0, d)) * fade * fade * (3.0 - 2.0 * fade)
        if d > 0:
            al *= max(0.0, min(1.0, (H - 44 - y) / 30.0))
        if al <= 0.02:
            continue
        al *= 0.80 + 0.20 * sel_t
        isz = int(round((34 + 14 * sel_t) / 2.0)) * 2
        yi = int(round(y))
        if sel_t > 0.05:
            pygame.draw.circle(c, xmb_tint(colx, y, 0.08 * sel_t * al), (colx, yi), int(isz * 0.62))
        c.blit(xmb_icon(it["icon"], isz, _mix(DIM, TEXT, sel_t), al), (colx - isz // 2, yi - isz // 2))
        tx = colx + 40
        lab = f_row.render(fit(f_row, it["label"], W - tx - 20), True, _xq(_mix(BG, _mix(DIM, TEXT, 0.40 + 0.60 * sel_t), al)))
        c.blit(lab, (tx, yi - lab.get_height() // 2 - int(round(10 * sel_t))))
        if sel_t > 0.2 and it.get("sub"):
            sub = f_small.render(fit(f_small, it["sub"], W - tx - 20), True, _xq(_mix(BG, DIM, al * sel_t)))
            c.blit(sub, (tx, yi + 3))


_XDD = [None, None]


def draw_xmb_dropdown(c, f_small, dd, opts):
    rh, top = 36, 150
    vis = max(1, min(len(opts), (H - 50 - top - 8) // rh))
    w, h = min(W - 60, 520), vis * rh + 12
    x, y = (W - w) // 2, min(top, H - 50 - h)
    first = min(max(0, dd["sel"] - vis // 2), len(opts) - vis)
    acc = tuple(ACCENT)[:3]
    key = (dd["sel"], dd["orig"], dd.get("kind"), first, vis, w, h, acc, tuple(TEXT), tuple(DIM), len(opts), f_small)
    if _XDD[0] == key:
        c.blit(_XDD[1], (x, y))
        return
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(panel, (0, 0, 0, 222), (0, 0, w, h), border_radius=12)
    pygame.draw.rect(panel, acc + (230,), (0, 0, w, h), 2, border_radius=12)
    for slot, ti in enumerate(range(first, first + vis)):
        ry, rsel = 6 + slot * rh, ti == dd["sel"]
        if rsel:
            pygame.draw.rect(panel, acc + (70,), (6, ry, w - 12, rh - 2), border_radius=8)
        oid, oname, oswatch, odesc = opts[ti]
        panel.blit(f_small.render(fit(f_small, oname + ("   (current)" if oid == dd["orig"] else ""), w - 180), True, TEXT if rsel else DIM), (18, ry + 8))
        if oswatch:
            for j, col in enumerate(oswatch):
                sx = w - 18 - (len(oswatch) - j) * 24
                pygame.draw.rect(panel, col, (sx, ry + 6, 20, 20), border_radius=5)
                pygame.draw.rect(panel, DIM, (sx, ry + 6, 20, 20), 1, border_radius=5)
        elif odesc:
            dt_ = f_small.render(fit(f_small, odesc, w - 200), True, DIM)
            panel.blit(dt_, (w - 18 - dt_.get_width(), ry + 8))
    if len(opts) > vis:
        if first > 0:
            pygame.draw.polygon(panel, acc, [(w - 8, 12), (w - 14, 18), (w - 2, 18)])
        if first + vis < len(opts):
            pygame.draw.polygon(panel, acc, [(w - 8, h - 12), (w - 14, h - 18), (w - 2, h - 18)])
    _XDD[0], _XDD[1] = key, panel
    c.blit(panel, (x, y))


FONT_PATH = [None]
FLOW_LEVELS = (1.0, 0.88, 0.77, 0.69, 0.62, 0.55, 0.50, 0.45)
FLOW_CACHE_CARDS = 20
FLOW_JUMP = 5  # the shoulder buttons move this many cards at once
_FLOW = {"fonts": {}, "cards": {}, "bg": (None, None), "bar": (None, None), "glow": {}, "shadow": {}, "S": 0, "warm": None,
         "jobs": {}, "op": 0.0}


def _lru_get(d, key):
    v = d.pop(key, None)
    if v is not None:
        d[key] = v
    return v


def _lru_put(d, key, val, cap):
    d[key] = val
    while len(d) > cap:
        d.pop(next(iter(d)))


def flow_level_width(S, li):
    return max(16, int(round(S * FLOW_LEVELS[li])))


def flow_level_index(tw, S):
    best = 0
    for li in range(len(FLOW_LEVELS)):
        if flow_level_width(S, li) >= tw - 0.5:
            best = li
        else:
            break
    return best


def _flow_font(size, bold=True):
    key = (int(size), bold)
    f = _FLOW["fonts"].get(key)
    if f is None:
        try:
            f = pygame.font.Font(FONT_PATH[0], int(size)) if FONT_PATH[0] else pygame.font.Font(None, int(size * 1.3))
        except Exception:
            f = pygame.font.Font(None, int(size * 1.3))
        f.set_bold(bold)
        f = _FLOW["fonts"][key] = CFont(f)
    return f


def flow_abbr(title):
    words = re.findall(r"[A-Za-z0-9]+", title)
    if len(words) > 1 and words[0].lower() in ("the", "a", "an"):
        words = words[1:]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (words[0][:2] if words else "?").upper()


def flow_hue(sid):
    return sum((i + 1) * ord(ch) for i, ch in enumerate(sid or "x")) * 47 % 360


def _flow_hsv(h, s, v):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _flow_gradient_card(hue, tag, abbr, S, icon=None):
    r = max(8, S // 10)
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    top, bot = _flow_hsv(hue, 0.42, 0.80), _flow_hsv(hue, 0.50, 0.50)
    for y in range(S):
        surf.fill(_mix(top, bot, y / max(1, S - 1)), (0, y, S, 1))
    mask = pygame.Surface((S, S), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, S, S), border_radius=r)
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    gl = pygame.Surface((S, S), pygame.SRCALPHA)
    for y in range(S):
        if y < S * 0.5:
            gl.fill((255, 255, 255, int(52 * (1 - y / (S * 0.5)) ** 1.5)), (0, y, S, 1))
        elif y > S * 0.72:
            gl.fill((0, 0, 0, int(60 * (y - S * 0.72) / (S * 0.28))), (0, y, S, 1))
    gl.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(gl, (0, 0))
    pygame.draw.rect(surf, (255, 255, 255, 80), (0, 0, S, S), max(2, S // 130), border_radius=r)
    if tag:
        ft = _flow_font(S * 0.066, False)
        tt = ft.render(tag, True, (240, 240, 250))
        px, py = int(S * 0.045), int(S * 0.02)
        cw, ch = tt.get_width() + 2 * px, tt.get_height() + 2 * py
        chip = pygame.Surface((cw, ch), pygame.SRCALPHA)
        pygame.draw.rect(chip, (30, 25, 60, 90), (0, 0, cw, ch), border_radius=max(4, ch // 4))
        surf.blit(chip, (int(S * 0.06), int(S * 0.06)))
        surf.blit(tt, (int(S * 0.06) + px, int(S * 0.06) + py))
    if icon:
        # A card with a short name (a system) lifts the icon and puts the name under it; the home cards have no name.
        lift = bool(abbr)
        dcy, dr, isz = (int(S * 0.44), int(S * 0.29), int(S * 0.42)) if lift else (S // 2, int(S * 0.34), int(S * 0.5))
        disc = pygame.Surface((S, S), pygame.SRCALPHA)
        pygame.draw.circle(disc, (255, 255, 255, 40), (S // 2, dcy), dr)
        pygame.draw.circle(disc, (255, 255, 255, 60), (S // 2, dcy), dr, max(2, S // 90))
        surf.blit(disc, (0, 0))
        surf.blit(xmb_icon(icon, isz, (242, 242, 250)), ((S - isz) // 2, dcy - isz // 2))
        if lift:
            at = _flow_font(S * 0.115).render(abbr, True, (242, 242, 250))
            surf.blit(at, ((S - at.get_width()) // 2, int(S * 0.84) - at.get_height() // 2))
    else:
        fa = _flow_font(S * (0.32 if len(abbr) <= 3 else 0.24))
        at = fa.render(abbr, True, (242, 242, 250))
        surf.blit(at, ((S - at.get_width()) // 2, int(S * 0.55) - at.get_height() // 2))
    return surf


def _flow_art_steps(path, S):
    """Square card made from a cover image: fitted whole, over a blurred copy of itself.

    A generator that yields after every heavy step (decode, each scale, blur), so flow_warm can spread a
    card over several frames instead of stalling one frame for the whole build. Returns the card, or None.
    """
    try:
        img = pygame.image.load(path)
        try:
            img = img.convert_alpha()
        except Exception:
            pass
        yield
        iw, ih = img.get_size()
        if iw < 2 or ih < 2:
            return None
        surf = pygame.Surface((S, S), pygame.SRCALPHA)
        if abs(iw / float(ih) - 1.0) < 0.06:
            surf.blit(pygame.transform.smoothscale(img, (S, S)), (0, 0))
            yield
        else:
            kc = max(S / float(iw), S / float(ih))
            cw, ch = max(S, int(iw * kc + 0.5)), max(S, int(ih * kc + 0.5))
            surf.blit(pygame.transform.smoothscale(img, (cw, ch)), ((S - cw) // 2, (S - ch) // 2))
            yield
            surf = _flow_blur(surf, 8)
            yield
            shade = pygame.Surface((S, S), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 110))
            surf.blit(shade, (0, 0))
            kf = min(S / float(iw), S / float(ih))
            fw, fh = max(1, int(iw * kf + 0.5)), max(1, int(ih * kf + 0.5))
            surf.blit(pygame.transform.smoothscale(img, (fw, fh)), ((S - fw) // 2, (S - fh) // 2))
            yield
        r = max(8, S // 10)
        mask = pygame.Surface((S, S), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, S, S), border_radius=r)
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pygame.draw.rect(surf, (255, 255, 255, 80), (0, 0, S, S), max(2, S // 130), border_radius=r)
        return surf
    except Exception as e:
        log("artwork: cannot use %s: %s" % (path, e))
        return None


def _flow_art_card(path, S):
    gen = _flow_art_steps(path, S)
    while True:
        try:
            next(gen)
        except StopIteration as e:
            return e.value

_DETAIL_ART = {}


DETAIL_SETTLE_S = 0.12  # the list's cover/details are only read from the card once the cursor rests this long


def _detail_cover(path, w, h, load=True):
    """Cover scaled to fit inside w x h (aspect kept) for the game list details panel, or None.

    Cached, because the panel is redrawn every frame; failures are cached too so a broken file is
    not decoded again on every frame. With load=False only an already cached cover is returned: the
    caller passes that while the cursor is moving, so scrolling never waits on an SD read + decode.
    """
    key = (path, w, h)
    hit = _lru_get(_DETAIL_ART, key)
    if hit is not None:
        return hit or None
    if not load:
        return None
    surf = False
    try:
        img = pygame.image.load(path)
        try:
            img = img.convert_alpha()
        except Exception:
            pass
        iw, ih = img.get_size()
        if iw >= 2 and ih >= 2:
            k = min(w / float(iw), h / float(ih))
            surf = pygame.transform.smoothscale(img, (max(1, int(iw * k + 0.5)), max(1, int(ih * k + 0.5))))
    except Exception as e:
        log("artwork: cannot use %s: %s" % (path, e))
    _lru_put(_DETAIL_ART, key, surf, 12)
    return surf or None


def _flow_key(hue, tag, abbr, S, icon=None, art=None):
    return (hue, tag, abbr, S, icon) + ((art,) if art else ())


def _flow_base(hue, tag, abbr, S, icon=None, art=None):
    key = _flow_key(hue, tag, abbr, S, icon, art)
    cards = _FLOW["cards"]
    lv = _lru_get(cards, key)
    if lv is None:
        surf = _flow_art_card(art, S) if art else None
        if surf is None:
            surf = _flow_gradient_card(hue, tag, abbr, S, icon)
        lv = [surf] + [None] * (len(FLOW_LEVELS) - 1)
        _lru_put(cards, key, lv, FLOW_CACHE_CARDS)
    return key, lv


def _flow_draw_base(hue, tag, abbr, S, icon=None, art=None):
    """Card for the draw loop. A cover that is not built yet shows the cheap gradient card for now.

    Decoding and scaling a cover inside the frame is what made scrolling stutter; flow_warm builds it
    over the next frames and the cover appears as soon as it is ready.
    """
    key = _flow_key(hue, tag, abbr, S, icon, art)
    lv = _lru_get(_FLOW["cards"], key)
    if lv is not None:
        return key, lv
    if art:
        return _flow_base(hue, tag, abbr, S, icon)
    return _flow_base(hue, tag, abbr, S, icon, art)


def _flow_art_advance(k, end):
    """Advance the build of cover card k until it is finished or time `end` passes; None while unfinished."""
    jobs = _FLOW["jobs"]
    job = jobs.get(k)
    if job is None:
        job = jobs[k] = _flow_art_steps(k[5], k[3])
    while True:
        try:
            next(job)
        except StopIteration as e:
            jobs.pop(k, None)
            surf = e.value
            if surf is None:
                surf = _flow_gradient_card(k[0], k[1], k[2], k[3], k[4])
            lv = [surf] + [None] * (len(FLOW_LEVELS) - 1)
            _lru_put(_FLOW["cards"], k, lv, FLOW_CACHE_CARDS)
            return lv
        if time.perf_counter() >= end:
            return None


def _flow_build_level(lv, S, li):
    if lv[li] is None:
        w, base = flow_level_width(S, li), lv[0]
        lv[li] = pygame.transform.smoothscale(base, (w, w)) if w != base.get_width() else base
    return lv[li]


def _flow_cover(lv, S, li):
    while li > 0 and lv[li] is None:
        li -= 1
    return lv[li]


def _flow_blur(base, k=5):
    sz = base.get_size()
    small = pygame.transform.smoothscale(base, (max(4, sz[0] // k), max(4, sz[1] // k)))
    return pygame.transform.smoothscale(small, sz)


def _flow_glow_level(S, li, build=True):
    w = flow_level_width(S, li)
    key = (w, tuple(ACCENT[:3]))
    glow = _FLOW["glow"]
    s = _lru_get(glow, key)
    if s is None and build:
        g = max(12, w // 6)
        base = pygame.Surface((w + 2 * g, w + 2 * g), pygame.SRCALPHA)
        pygame.draw.rect(base, tuple(ACCENT[:3]) + (150,), (g, g, w, w), border_radius=max(8, w // 8))
        s = _flow_blur(base)
        _lru_put(glow, key, s, 24)
    return s


def _flow_shadow(w):
    w = max(8, (w // 4) * 4)
    s = _lru_get(_FLOW["shadow"], w)
    if s is None:
        small = pygame.Surface((20, 5), pygame.SRCALPHA)
        pygame.draw.ellipse(small, (0, 0, 0, 170), (2, 0, 16, 5))
        s = pygame.transform.smoothscale(small, (max(8, int(w * 0.94)), max(6, int(w * 0.11))))
        _lru_put(_FLOW["shadow"], w, s, 64)
    return s


def _flow_title(title, compact):
    tsize = 34 if compact else 44
    while tsize > 20 and _flow_font(tsize).size(title)[0] > W - 40:
        tsize -= 2
    tf = _flow_font(tsize)
    ttxt = fit(tf, title, W - 40)
    tt = tf.render(ttxt, True, TEXT)
    ts = None
    if sum(BG) < 384:
        ts = tf.render(ttxt, True, (0, 0, 0))
        ts.set_alpha(130)
    return tt, ts


def flow_warm(cards, centre, budget, moving=False):
    """Build cards, glows and scaled levels near the centre, never running past `budget` seconds.

    While scrolling the budget is a few milliseconds, so an operation is only started when the measured
    cost of the last one still fits; the first one of a call always runs so warming cannot stall.

    With `moving` set (a glide is running or a button was just pressed) nothing heavy may run: no cover
    decoding, no glow or scaled levels, because one 20-50 ms operation in the middle of a glide is exactly
    the stutter. Only the cheap gradient cards the next few steps will need are built (one per call), so a
    shoulder-button jump of 5 never has to build them inside a frame; the rest waits until the glide ends.
    """
    n, S = len(cards), _FLOW["S"]
    if not n or S <= 0:
        return
    sig = (id(cards), centre % n if n >= 3 else centre, S, tuple(ACCENT[:3]))
    if _FLOW["warm"] == sig:
        return
    t0 = time.perf_counter()
    end = t0 + budget
    compact = H < 600
    order, seen = [], set()
    for dist in range(FLOW_JUMP + 3 if moving else 5):
        for sgn in ((0,) if dist == 0 else (1, -1)):
            i = centre + sgn * dist
            if n >= 3:
                i %= n
            elif not 0 <= i < n:
                continue
            if i not in seen:
                seen.add(i)
                order.append((dist, i))
    keys = [_flow_key(cards[i]["hue"], cards[i]["tag"], cards[i]["abbr"], S, cards[i].get("icon"), cards[i].get("art"))
            for _d, i in order]
    for k in [k for k in _FLOW["jobs"] if k not in keys]:
        del _FLOW["jobs"][k]  # scrolled far away: drop half-built covers
    levels, lkeys = [], []
    steam = _STEAM["on"]
    for (dist, i), k in zip(order, keys):
        g = cards[i]
        lv = _lru_get(_FLOW["cards"], k)
        if moving:
            # Cheap path: make sure the gradient card exists (a cover shows it until it is built at rest).
            if lv is None and _lru_get(_FLOW["cards"], k[:5]) is None:
                _flow_base(*k[:5])
                return
            continue
        if lv is None:
            if len(k) > 5:
                lv = _flow_art_advance(k, end)
                if lv is None:
                    return
            else:
                lv = _flow_base(*k)[1]
            if time.perf_counter() >= end:
                if dist <= 2:
                    levels.append(lv)
                    lkeys.append(k)
                return
        if dist <= 2:
            levels.append(lv)
            lkeys.append(k)
        if dist <= 3:
            _flow_title(g["title"], compact)

    if moving:
        return
    ops = [0]

    def room():
        """True if another scale operation may start now."""
        if ops[0] == 0:
            if budget >= 0.010 or _FLOW["op"] <= 2 * budget:
                return True
            _FLOW["skip"] = _FLOW.get("skip", 0) + 1
            return _FLOW["skip"] % 4 == 0  # an op too big for a scrolling frame still runs now and then
        return time.perf_counter() + _FLOW["op"] <= end

    def timed(fn, *a):
        t = time.perf_counter()
        r = fn(*a)
        dt = time.perf_counter() - t
        _FLOW["op"] = dt if dt > _FLOW["op"] else _FLOW["op"] * 0.9 + dt * 0.1
        ops[0] += 1
        return r

    if steam:
        # SteamOS draws only the focus size and the 80 % size and has no glow: build the hero for the focus first, then
        # the next and previous ones (so the next press already has its backdrop), then the resting-size covers.
        for lv in levels[:3]:
            if _steam_hero_peek(lv[0]) is None:
                if not room():
                    return
                timed(_steam_hero, lv[0])
        small = max(16, int(round(S * 0.8)))
        for lv, k in zip(levels, lkeys):
            if lv[1] is None:
                if not room():
                    return
                timed(_flow_build_level, lv, S, 1)
            if (k, small) not in _STEAM["covers"]:
                if not room():
                    return
                timed(_steam_cover, k, lv, S, small)
        _FLOW["warm"] = sig
        return
    for li in (0, 1):
        if _flow_glow_level(S, li, False) is None:
            if not room():
                return
            timed(_flow_glow_level, S, li)
    rest = (4, 7)
    for tier in (rest, [li for li in range(1, len(FLOW_LEVELS)) if li not in rest]):
        for lv in levels:
            for li in tier:
                if lv[li] is None:
                    if not room():
                        return
                    timed(_flow_build_level, lv, S, li)
    _FLOW["warm"] = sig


def flow_bg(c):
    key = (BG, ACCENT, W, H)
    if _FLOW["bg"][0] != key:
        dark = sum(BG) < 384
        top = _mix(BG, ACCENT, 0.22 if dark else 0.16)
        bot = _mix(BG, (0, 0, 0), 0.55) if dark else _mix(BG, ACCENT, 0.04)
        s = pygame.Surface((W, H))
        for y in range(H):
            s.fill(_mix(top, bot, (y / max(1, H - 1)) ** 0.8), (0, y, W, 1))
        lg = pygame.Surface((32, 18), pygame.SRCALPHA)
        pygame.draw.ellipse(lg, tuple(ACCENT[:3]) + (70 if dark else 40,), (3, 2, 26, 14))
        s.blit(pygame.transform.smoothscale(lg, (W, int(H * 0.8))), (0, int(H * 0.08)))
        _FLOW["bg"] = (key, s)
    c.blit(_FLOW["bg"][1], (0, 0))


def draw_flow_level(c, f_small, f_row, cards, fx, fade, crumb, hints, empty, clk, bat, scanning):
    _STEAM["on"] = False
    compact = H < 600
    arrows = bool(FONT_PATH[0])
    flow_bg(c)
    fl = _flow_font(26 if not compact else 22)
    x = 20
    for ch in "RG":
        t = fl.render(ch, True, _mix(ACCENT, TEXT, 0.35))
        c.blit(t, (x, 18)); x += t.get_width() + 5
    x += 10
    for ch in "OS":
        t = fl.render(ch, True, TEXT)
        c.blit(t, (x, 18)); x += t.get_width() + 5
    info = "Scanning..." if scanning else clk
    if bat and not scanning:
        info += "   %d%%%s" % (bat[0], "+" if bat[1].lower() == "charging" else "")
    it = f_small.render(info, True, (230, 70, 60) if bat and bat[0] <= 15 and bat[1].lower() != "charging" and not scanning else DIM)
    c.blit(it, (x + 6, 18 + (fl.get_height() - it.get_height()) // 2))
    left_end = x + 6 + it.get_width() + 14
    if crumb:
        cf = f_small if compact else f_row
        txt = fit(cf, crumb, max(60, W - 40 - left_end - 28))
        ct = cf.render(txt, True, BG)
        cw_, ch_h = ct.get_width() + 28, 28 if compact else 34
        cy_ = 14 if compact else 16
        pygame.draw.rect(c, _mix(BG, ACCENT, 0.75), (W - 20 - cw_, cy_, cw_, ch_h), border_radius=8)
        c.blit(ct, (W - 20 - cw_ + 14, cy_ + (ch_h - ct.get_height()) // 2))

    bar_h = 34 if compact else 38
    bar_y = H - bar_h - (12 if compact else 16)
    sub_cy = bar_y - (50 if compact else 76)
    title_cy = sub_cy - (36 if compact else 47)
    card_bot = title_cy - (30 if compact else 45)
    S = int(min(W * 0.466, card_bot - (78 if compact else 84)))
    _FLOW["S"] = S
    n = len(cards)
    if not n:
        t = _flow_font(26 if not compact else 22).render(empty[0], True, TEXT)
        c.blit(t, ((W - t.get_width()) // 2, H // 2 - 30))
        t2 = f_small.render(empty[1], True, DIM)
        c.blit(t2, ((W - t2.get_width()) // 2, H // 2 + 8))
    else:
        wrap_ = n >= 3
        base_i = int(round(fx))
        reach = 2 if n >= 5 else 1
        vis = []
        for i in range(base_i - reach, base_i + reach + 1):
            if not wrap_ and not 0 <= i < n:
                continue
            d = i - fx
            if abs(d) > reach + 0.6:
                continue
            vis.append((abs(d), i, d))
        for _ad, i, d in sorted(vis, reverse=True):
            g = cards[i % n]
            a = min(abs(d), 2.0)
            scale = 1 - 0.38 * min(a, 1.0) - 0.17 * max(0.0, a - 1.0)
            off = (1 if d > 0 else -1) * S * (0.745 * min(a, 1.0) + 0.42 * max(0.0, a - 1.0)) * (abs(d) / a if a else 0)
            alpha = 255 - 55 * min(a, 1.0) - 110 * max(0.0, a - 1.0) if a < 2 else 90
            tw_ = S * scale
            w = max(16, int(round(tw_)))
            key, lv = _flow_draw_base(g["hue"], g["tag"], g["abbr"], S, g.get("icon"), g.get("art"))
            li = flow_level_index(tw_, S)
            src = _flow_cover(lv, S, li)
            surf = src if src.get_width() == w else pygame.transform.scale(src, (w, w))
            surf.set_alpha(int(max(0, min(255, alpha * fade))))
            ccx, ccy = W // 2 + off, card_bot - S // 2
            x0_, y0_ = int(ccx - w / 2), int(ccy - w / 2)
            if abs(d) < 0.5:
                j = li
                gs = _flow_glow_level(S, j, False)
                while gs is None and j > 0:
                    j -= 1
                    gs = _flow_glow_level(S, j, False)
                if gs is None:
                    j, gs = 0, _flow_glow_level(S, 0)
                lw_ = flow_level_width(S, j)
                if lw_ != w:
                    gs = pygame.transform.scale(gs, (max(1, gs.get_width() * w // lw_), max(1, gs.get_height() * w // lw_)))
                gs.set_alpha(int(255 * fade * (1 - abs(d) * 2)))
                c.blit(gs, (x0_ - (gs.get_width() - w) // 2, y0_ - (gs.get_height() - w) // 2))
            sh = _flow_shadow(w)
            sh.set_alpha(int(210 * fade * (1 - 0.4 * min(a, 1.0))))
            c.blit(sh, (int(ccx - sh.get_width() / 2), y0_ + w - sh.get_height() // 3))
            c.blit(surf, (x0_, y0_))
        ci = int(round(fx))
        g = cards[ci % n] if wrap_ else cards[max(0, min(n - 1, ci))]
        tt, ts = _flow_title(g["title"], compact)
        star = f_row.render("\u2605" if arrows else "*", True, ACCENT) if g.get("fav") else None
        tw = tt.get_width() + (star.get_width() + 10 if star else 0)
        tx = (W - tw) // 2
        if ts:
            c.blit(ts, (tx + 2, title_cy - tt.get_height() // 2 + 2))
        c.blit(tt, (tx, title_cy - tt.get_height() // 2))
        if star:
            c.blit(star, (tx + tt.get_width() + 10, title_cy - star.get_height() // 2))
        pos = "%d / %d" % ((ci % n) + 1, n)
        sub = ("%s   \u2022   %s" if arrows else "%s  -  %s") % (g["sub"], pos) if g["sub"] else pos
        st = (f_small if compact else f_row).render(fit(f_small if compact else f_row, sub, W - 40), True, DIM)
        c.blit(st, ((W - st.get_width()) // 2, sub_cy - st.get_height() // 2))
        if 1 < n <= 12:
            dy = sub_cy + (23 if compact else 33)
            gap = 14
            dx = (W - (n - 1) * gap) // 2 - 0
            sel_i = ci % n if wrap_ else max(0, min(n - 1, ci))
            for k in range(n):
                if k == sel_i:
                    pygame.draw.rect(c, ACCENT, (dx + k * gap - 7, dy - 3, 14, 6), border_radius=3)
                else:
                    pygame.draw.circle(c, _mix(BG, TEXT, 0.35), (dx + k * gap, dy), 3)

    if _FLOW["bar"][0] != (BG, W, bar_h):
        bs = pygame.Surface((W - 40, bar_h), pygame.SRCALPHA)
        pygame.draw.rect(bs, (0, 0, 0, 90) if sum(BG) < 384 else (255, 255, 255, 110), (0, 0, W - 40, bar_h), border_radius=bar_h // 3)
        _FLOW["bar"] = ((BG, W, bar_h), bs)
    c.blit(_FLOW["bar"][1], (20, bar_y))
    hy = bar_y + bar_h // 2
    for k_, (key_, label) in enumerate(hints):
        key_ = key_.replace("<>", "\u25c0 \u25b6" if arrows else "L/R")
        fxp = (k_ + 0.5) / len(hints)
        hot = key_ in ("A",)
        kt = f_small.render(key_, True, BG if hot else TEXT)
        lt = f_row.render(label, True, DIM) if not compact else f_small.render(label, True, DIM)
        bw, bh = kt.get_width() + 14, kt.get_height() + 4
        tw = bw + 8 + lt.get_width()
        x0 = max(32, min(W - 32 - tw, int(W * fxp - tw / 2)))
        pygame.draw.rect(c, _mix(BG, ACCENT, 0.8) if hot else _mix(BG, TEXT, 0.2), (x0, hy - bh // 2, bw, bh), border_radius=bh // 2)
        c.blit(kt, (x0 + 7, hy - kt.get_height() // 2))
        c.blit(lt, (x0 + bw + 8, hy - lt.get_height() // 2))


# ---- SteamOS launcher (Steam Deck gaming-mode look) --------------------------------------------------------------
# Reuses the RG Flow plumbing (cards, scrolling, cover cache, input) and only changes how a level is drawn: a left-
# anchored capsule row with a pulsing focus ring, a title block with a green Play button, a crossfading hero backdrop,
# a Steam-button side menu (MENU) and a Deck-style prompt bar (MENU/X on the left, A/B/Y on the right). The palette is
# fixed (it is the look being cloned) and does not follow the RG OS theme.
FLOW_LIKE = ("flow", "steamos")
STEAM_BG, STEAM_BG2 = (14, 20, 27), (30, 45, 62)
STEAM_BLUE, STEAM_TEXT, STEAM_DIM, STEAM_YELLOW = (26, 159, 255), (199, 213, 224), (132, 146, 160), (232, 188, 48)
STEAM_GREEN, STEAM_GREEN2 = (112, 192, 52), (72, 128, 30)
STEAM_PANEL, STEAM_LINE, STEAM_SEL = (22, 29, 38), (44, 60, 80), (52, 74, 100)
STEAM_BTN = {"A": (91, 163, 43), "B": (214, 76, 62), "X": (26, 159, 255), "Y": (232, 188, 48)}
STEAM_FADE = 0.22
HERO_DIV = 4            # the hero is composed at 1/4 size and upscaled once; it is blurred and shaded anyway
HERO_CACHE = 6          # finished full-screen heroes kept (about 1.5 MB each)
COVER_CACHE = 48        # per-width scaled capsule covers kept
# the Steam-button menu: (target view, label); "home" and "power" are handled by the input code
STEAM_MENU = (("home", "Home"), ("games", "Library"), ("recents", "Recent Games"), ("favorites", "Favorites"),
              ("tools", "Tools"), ("settings", "Settings"), ("power", "Power"))
STEAM_UI = {"open": False, "slide": 0.0, "sel": 0, "wifi": None, "rest": True}
_STEAM = {"grad": (None, None), "shade": (None, None, None), "heroes": {}, "shown": None, "prev": None, "dim": (None, None),
          "covers": {}, "btn": {}, "on": False}


def steam_menu_index(view):
    return {"systems": 1, "games": 1, "recents": 2, "favorites": 3}.get(view, 0)


def steam_clock(clk):
    """24 h 'HH:MM' from the clock -> the Deck's default 12 h 'h:MM AM'."""
    try:
        h, m = clk.split(":")[:2]
        h = int(h)
    except ValueError:
        return clk
    return "%d:%s %s" % (h % 12 or 12, m[:2], "AM" if h < 12 else "PM")


def steam_heading(crumb):
    return {"": "Home", "Recents": "Recent Games"}.get(crumb, crumb)


def steam_hints(hints, is_game, menu_open):
    """Flow hints -> Deck prompts: A reads Play on a game and Select elsewhere, the MENU hint moves to the left side of
    the bar, and X (rescan) is always offered. While the side menu is open only A and B apply."""
    if menu_open:
        return [("A", "Select"), ("B", "Back")]
    out = [(k, ("Play" if is_game else "Select") if k == "A" else l) for k, l in hints if k != "MENU"]
    if not any(k == "X" for k, _l in out):
        out.append(("X", "Rescan"))
    return out


def _steam_layers(gk):
    """Small-size gradient and the two shade layers, built once per screen size."""
    if _STEAM["shade"][0] != gk:
        sw, sh = max(8, W // HERO_DIV), max(8, H // HERO_DIV)
        g = pygame.Surface((sw, sh), 0, 32)
        for y in range(sh):
            g.fill(_mix(STEAM_BG2, STEAM_BG, min(1.0, y / (sh * 0.8))), (0, y, sw, 1))
        left = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for x in range(sw):
            left.fill((8, 12, 18, int(185 * max(0.0, 1.0 - x / (sw * 0.8)))), (x, 0, 1, sh))
        low = pygame.Surface((sw, sh), pygame.SRCALPHA)
        y0 = int(sh * 0.42)
        for y in range(y0, sh):
            low.fill((8, 12, 18, int(215 * (y - y0) / float(max(1, sh - y0)))), (0, y, sw, 1))
        _STEAM["grad"] = (gk, g)
        _STEAM["shade"] = (gk, left, low, (sw, sh))
    return _STEAM["grad"][1], _STEAM["shade"]


def _steam_hero_peek(base):
    ent = _STEAM["heroes"].get(((W, H), id(base)))
    return ent[1] if ent is not None and ent[0] is base else None


def _steam_hero(base, ref=None):
    """Finished hero for a capsule: navy gradient, the art blurred across the screen, then shaded on the left and at the
    bottom so the title and prompts stay readable, all baked into ONE opaque surface. Showing it costs a single plain
    blit per frame (the old code alpha-blended two full-screen shade layers on top of the gradient every frame). The
    composing happens at 1/HERO_DIV size and is upscaled once, so building one is cheap enough to do at rest."""
    hit = _steam_hero_peek(base)
    if hit is not None:
        return hit
    gk = (W, H)
    grad, (_gk, left, low, (sw, sh)) = _steam_layers(gk)
    out = grad.copy()
    if base is not None:
        try:
            blur = pygame.transform.smoothscale(pygame.transform.smoothscale(base, (12, max(6, 12 * H // W))), (sw, sh))
            blur.set_alpha(150)
            out.blit(blur, (0, 0))
        except Exception:
            pass
    out.blit(left, (0, 0))
    out.blit(low, (0, 0))
    try:
        hero = pygame.transform.smoothscale(out, (W, H))
    except Exception:
        hero = pygame.transform.scale(out, (W, H))
    if ref is not None:
        try:
            hero = hero.convert(ref)  # same pixel format as the canvas: the per-frame blit is then a straight copy
        except Exception:
            pass
    _lru_put(_STEAM["heroes"], (gk, id(base)), (base, hero), HERO_CACHE)
    return hero


def _steam_backdrop(c, base, rest=True):
    """Draw the hero for the focused capsule. Moving to another capsule crossfades from the previous hero over
    STEAM_FADE seconds. While the cursor is still travelling (rest False) the current hero is kept, so a held d-pad
    never starts a crossfade per step and the backdrop changes once, when the cursor settles."""
    now = time.monotonic()
    shown = _STEAM["shown"]
    if shown is None:
        shown = _STEAM["shown"] = _steam_hero(base, c)
    elif rest:
        want = _steam_hero(base, c)
        if want is not shown:
            _STEAM["prev"] = (shown, now)
            shown = _STEAM["shown"] = want
    prev = _STEAM["prev"]
    if prev is not None and now - prev[1] < STEAM_FADE and prev[0] is not shown:
        c.blit(prev[0], (0, 0))
        shown.set_alpha(int(255 * (now - prev[1]) / STEAM_FADE))
        c.blit(shown, (0, 0))
        shown.set_alpha(255)
        _anim_clock[2] = True
    else:
        c.blit(shown, (0, 0))


def _steam_cover(key, lv, S, w):
    """Capsule cover at width w without scaling inside the frame. The width is snapped (exactly S, exactly the resting
    small size, else a multiple of 4) and the scaled surface cached, so a glide reuses surfaces instead of resizing
    every card on every frame. Returns (surface, snapped width)."""
    small = max(16, int(round(S * 0.8)))
    wq = S if w >= S - 2 else small if abs(w - small) <= 2 else max(16, w - w % 4)
    src = _flow_cover(lv, S, flow_level_index(wq, S))
    if src.get_width() == wq:
        return src, wq
    ck = (key, wq)
    ent = _lru_get(_STEAM["covers"], ck)
    if ent is None or ent[0] is not lv[0]:
        ent = (lv[0], pygame.transform.smoothscale(src, (wq, wq)))
        _lru_put(_STEAM["covers"], ck, ent, COVER_CACHE)
    return ent[1], wq


def _steam_prompt(c, f_small, x, cy, key_, label, arrows):
    """One button prompt: a coloured disc for A/B/X/Y, a dark pill for anything else. Returns the x it ends at."""
    key_ = key_.replace("<>", "\u25c0 \u25b6" if arrows else "L/R")
    kt = f_small.render(key_, True, (255, 255, 255))
    lt = f_small.render(label, True, STEAM_TEXT)
    col = STEAM_BTN.get(key_)
    gw = 24 if col else kt.get_width() + 16
    if col:
        pygame.draw.circle(c, col, (x + 12, cy), 12)
    else:
        pygame.draw.rect(c, STEAM_LINE, (x, cy - 12, gw, 24), border_radius=12)
    c.blit(kt, (x + (gw - kt.get_width()) // 2, cy - kt.get_height() // 2))
    c.blit(lt, (x + gw + 7, cy - lt.get_height() // 2))
    return x + gw + 7 + lt.get_width()


def _steam_prompt_width(f_small, key_, label, arrows=False):
    """Width _steam_prompt will draw; `arrows` must match what it is given or the bar lays out with the wrong gaps."""
    kw = 24 if key_ in STEAM_BTN else f_small.size(key_.replace("<>", "\u25c0 \u25b6" if arrows else "L/R"))[0] + 16
    return kw + 7 + f_small.size(label)[0]


def _steam_play_button(c, x, y, bw, bh, label, bf, focus):
    """Deck Play button: rounded green gradient with a play triangle, lighter outline while it is the focus. The shape is
    drawn once per (label, size, focus) and blitted afterwards; it is identical on every frame of a scroll."""
    m = 4  # margin around the button for the focus outline
    key = (label, bw, bh, focus)
    sf = _STEAM["btn"].get(key)
    if sf is None:
        if len(_STEAM["btn"]) > 12:
            _STEAM["btn"].clear()
        r = 6
        sf = pygame.Surface((bw + 2 * m, bh + 2 * m), pygame.SRCALPHA)
        pygame.draw.rect(sf, STEAM_GREEN2, (m, m, bw, bh), border_radius=r)
        pygame.draw.rect(sf, _mix(STEAM_GREEN, STEAM_GREEN2, 0.25), (m, m, bw, bh * 2 // 3), border_top_left_radius=r, border_top_right_radius=r)
        pygame.draw.rect(sf, STEAM_GREEN, (m + 2, m + 2, bw - 4, bh // 3), border_top_left_radius=r - 2, border_top_right_radius=r - 2)
        if focus:
            pygame.draw.rect(sf, (255, 255, 255), (m - 2, m - 2, bw + 4, bh + 4), 2, border_radius=r + 2)
        lt = bf.render(label, True, (255, 255, 255))
        ix, cy = m + 20, m + bh // 2
        tw = 12 if label == "Play" else 0
        if tw:
            pygame.draw.polygon(sf, (255, 255, 255), [(ix, cy - 8), (ix, cy + 8), (ix + tw + 2, cy)])
        sf.blit(lt, (m + (bw + (tw + 8 if tw else 0) - lt.get_width()) // 2 + (6 if tw else 0), cy - lt.get_height() // 2))
        _STEAM["btn"][key] = sf
    c.blit(sf, (x - m, y - m))


def _steam_wifi(c, right, cy, on):
    """Three arcs and a dot, white while a Wi-Fi link is up and grey while it is not. Returns the x it starts at."""
    col = (255, 255, 255) if on else (110, 122, 136)
    cx, by = right - 12, cy + 8
    for r in (6, 11, 16):
        pygame.draw.arc(c, col, (cx - r, by - r, 2 * r, 2 * r), math.pi * 0.25, math.pi * 0.75, 2)
    pygame.draw.circle(c, col, (cx, by), 2)
    return right - 26


def draw_steam_menu(c, f_small, f_row, bottom):
    """The Steam-button panel: slides in from the left over a dimmed screen, profile on top, then the menu rows."""
    s = STEAM_UI["slide"]
    if s <= 0.001:
        return
    e = 1 - (1 - min(1.0, s)) ** 3
    pw = max(250, int(W * 0.36))
    if _STEAM["dim"][0] != (W, bottom):
        d = pygame.Surface((W, bottom), pygame.SRCALPHA)
        d.fill((4, 8, 14, 170))
        _STEAM["dim"] = ((W, bottom), d)
    d = _STEAM["dim"][1]
    d.set_alpha(int(255 * e))
    c.blit(d, (0, 0))
    x = int(-pw * (1 - e))
    pygame.draw.rect(c, STEAM_PANEL, (x, 0, pw, bottom))
    pygame.draw.rect(c, STEAM_LINE, (x + pw - 1, 0, 1, bottom))
    compact = H < 600
    pad, r = 18, 18 if compact else 22
    head = 58 if compact else 70
    cy0 = head // 2 + 6
    pygame.draw.circle(c, STEAM_LINE, (x + pad + r, cy0), r)
    pygame.draw.circle(c, STEAM_TEXT, (x + pad + r, cy0), r, 2)
    rg = f_small.render("RG", True, (255, 255, 255))
    c.blit(rg, (x + pad + r - rg.get_width() // 2, cy0 - rg.get_height() // 2))
    tx = x + pad + 2 * r + 12
    nt = f_row.render("RG OS", True, (255, 255, 255))
    c.blit(nt, (tx, cy0 - nt.get_height() + 2))
    online = STEAM_UI["wifi"]
    pygame.draw.circle(c, STEAM_GREEN if online else (110, 122, 136), (tx + 4, cy0 + 12), 4)
    c.blit(f_small.render("Online" if online else "Offline", True, STEAM_DIM), (tx + 14, cy0 + 12 - f_small.get_height() // 2 + 1))
    y = head + 14
    pygame.draw.rect(c, STEAM_LINE, (x + pad, y - 8, pw - 2 * pad, 1))
    rh = max(30, min(46, (bottom - y - 8) // len(STEAM_MENU)))
    for i, (_k, label) in enumerate(STEAM_MENU):
        sel = i == STEAM_UI["sel"]
        ry = y + i * rh
        if sel:
            pygame.draw.rect(c, STEAM_SEL, (x + 10, ry, pw - 20, rh - 4), border_radius=6)
            pygame.draw.rect(c, STEAM_BLUE, (x + 10, ry + 4, 4, rh - 12), border_radius=2)
        t = f_row.render(fit(f_row, label, pw - 70), True, (255, 255, 255) if sel else STEAM_TEXT)
        c.blit(t, (x + 30, ry + (rh - 4 - t.get_height()) // 2))


def draw_steam_level(c, f_small, f_row, cards, fx, fade, crumb, hints, empty, clk, bat, scanning):
    compact = H < 600
    arrows = bool(FONT_PATH[0])
    n = len(cards)
    top_h, bar_h = (40, 44) if compact else (50, 52)
    head_h = 28 if compact else 34
    S = int(max(96, min(W * 0.30, (H - top_h - bar_h - head_h) * 0.46)))
    _FLOW["S"] = S
    ci = int(round(fx))
    cur = (cards[ci % n] if n >= 3 else cards[max(0, min(n - 1, ci))]) if n else None
    base0 = _flow_draw_base(cur["hue"], cur["tag"], cur["abbr"], S, cur.get("icon"), cur.get("art"))[1][0] if cur else None
    _STEAM["on"] = True
    _steam_backdrop(c, base0, STEAM_UI["rest"])

    # top bar: no panel, like gaming mode; clock, Wi-Fi and battery on the right, nothing on the left
    cy = top_h // 2 + 2
    right = W - 24
    if bat:
        pct, status = bat
        chg = status.lower() == "charging"
        col = (230, 70, 60) if pct <= 15 and not chg else STEAM_GREEN if chg else (255, 255, 255)
        pt = f_small.render("%d%%" % pct, True, col)
        right -= pt.get_width()
        c.blit(pt, (right, cy - pt.get_height() // 2))
        bx, by = right - 34, cy - 7
        pygame.draw.rect(c, col, (bx, by, 25, 14), 2, border_radius=2)
        pygame.draw.rect(c, col, (bx + 25, by + 4, 3, 6))
        pygame.draw.rect(c, col, (bx + 3, by + 3, max(2, 19 * pct // 100), 8))
        right = bx - 18
    if STEAM_UI["wifi"] is not None:
        right = _steam_wifi(c, right, cy, STEAM_UI["wifi"]) - 14
    info = _flow_font(20 if compact else 22).render("Scanning..." if scanning else steam_clock(clk), True, (255, 255, 255))
    c.blit(info, (right - info.get_width(), cy - info.get_height() // 2))

    # section heading above the row, like "Recent Games"
    hf = _flow_font(22 if compact else 26)
    ht = hf.render(fit(hf, steam_heading(crumb) or "Home", W - 56), True, (255, 255, 255))
    c.blit(ht, (28, top_h - 2))

    # capsule row, focus anchored on the left; the others follow at 80 % and dimmed
    if not n:
        t = _flow_font(26 if not compact else 22).render(empty[0], True, (255, 255, 255))
        c.blit(t, ((W - t.get_width()) // 2, H // 2 - 40))
        t2 = f_small.render(empty[1], True, STEAM_DIM)
        c.blit(t2, ((W - t2.get_width()) // 2, H // 2 - 2))
    else:
        gap, x0, row_top = 14, 28, top_h + head_h + (6 if compact else 10)
        mid, small = row_top + S // 2, int(S * 0.8)
        wrap_ = n >= 3
        lo = int(math.floor(fx)) - 1 if wrap_ else 0
        idxs = range(lo, lo + min(n, 6)) if wrap_ else range(n)
        pulse = round((0.5 + 0.5 * math.sin(time.time() * 2.6)) * 8) / 8.0  # 8 steps: an unchanged frame is not re-sent
        vis = []
        for i in idxs:
            d = i - fx
            left = x0 + (min(d, 1.0) * (S + gap) + max(0.0, d - 1.0) * (small + gap) if d >= 0 else d * (small + gap))
            w = max(16, int(round(S * (1 - 0.2 * min(abs(d), 1.0)))))
            if left < W and left + w > 0:
                vis.append((abs(d), i, d, int(left), w))
        for _ad, i, d, left, w in sorted(vis, reverse=True):
            g = cards[i % n]
            ck, lv = _flow_draw_base(g["hue"], g["tag"], g["abbr"], S, g.get("icon"), g.get("art"))
            surf, wq = _steam_cover(ck, lv, S, w)
            surf.set_alpha(int(max(0, min(255, (255 - 120 * min(abs(d), 1.0)) * fade))))
            left += (w - wq) // 2  # a snapped cover stays centred on where the exact one would be
            w = wq
            top = mid - w // 2
            sh = _flow_shadow(w)
            sh.set_alpha(int(190 * fade))
            c.blit(sh, (left + w // 2 - sh.get_width() // 2, top + w - sh.get_height() // 3))
            c.blit(surf, (left, top))
            if abs(d) < 0.5:
                pygame.draw.rect(c, _mix(STEAM_BG2, STEAM_BLUE, 0.55), (left - 9, top - 9, w + 18, w + 18), 2, border_radius=9)
                pygame.draw.rect(c, _mix(STEAM_BLUE, (255, 255, 255), 0.5 + 0.5 * pulse), (left - 5, top - 5, w + 10, w + 10), 3, border_radius=6)
            if g.get("fav"):
                pygame.draw.circle(c, STEAM_YELLOW, (left + w - 15, top + 15), 9)
                if arrows:
                    st = f_small.render("\u2605", True, (40, 30, 0))
                    c.blit(st, (left + w - 15 - st.get_width() // 2, top + 15 - st.get_height() // 2))

        # title block: big name, then Play + favourite buttons and Deck-style info columns
        y = row_top + S + (20 if compact else 30)
        tsize = 28 if compact else 36
        while tsize > 18 and _flow_font(tsize).size(cur["title"])[0] > W - 56:
            tsize -= 2
        tf = _flow_font(tsize)
        tt = tf.render(fit(tf, cur["title"], W - 56), True, (255, 255, 255))
        c.blit(tt, (28, y))
        y += tt.get_height() + (8 if compact else 14)
        label = "Play" if "game" in cur else "Shut down" if cur.get("id") == "power" else "Open"
        bf = _flow_font(20 if compact else 22)
        bw, bh = max(150, bf.size(label)[0] + 76), 38 if compact else 44
        _steam_play_button(c, 28, y, bw, bh, label, bf, not STEAM_UI["open"])
        nx = 28 + bw + 12
        if "game" in cur:
            fav = bool(cur.get("fav"))
            pygame.draw.rect(c, (36, 50, 66), (nx, y, bh, bh), border_radius=6)
            pygame.draw.circle(c, STEAM_YELLOW if fav else STEAM_BTN["Y"], (nx + bh // 2, y + bh // 2), bh // 4 + 2, 0 if fav else 2)
            yt = f_small.render("Y", True, (40, 30, 0) if fav else STEAM_YELLOW)
            c.blit(yt, (nx + (bh - yt.get_width()) // 2, y + (bh - yt.get_height()) // 2))
            nx += bh + 26
        else:
            nx += 14
        cols = [("SYSTEM", cur["sub"]), ("POSITION", "%d / %d" % ((ci % n) + 1, n))]
        for head, val in cols:
            if not val or nx >= W - 90:
                continue
            ht_ = f_small.render(head, True, STEAM_DIM)
            vt = f_row.render(fit(f_row, val, max(40, W - 28 - nx)), True, (255, 255, 255))
            c.blit(ht_, (nx, y - 4))
            c.blit(vt, (nx, max(y - 4 + ht_.get_height(), y + bh + 2 - vt.get_height())))
            nx += max(ht_.get_width(), vt.get_width()) + 34

    # bottom bar: MENU on the left like the Steam button, button prompts on the right
    by = H - bar_h
    cyb = by + bar_h // 2
    pygame.draw.rect(c, (40, 56, 74), (0, by, W, 1))
    left_end = 24 if STEAM_UI["open"] else _steam_prompt(c, f_small, 24, cyb, "MENU", "Menu", arrows) + 22
    prompts = steam_hints(hints, bool(cur and "game" in cur), STEAM_UI["open"])
    while len(prompts) > 2 and sum(_steam_prompt_width(f_small, k, l, arrows) for k, l in prompts) + 22 * (len(prompts) - 1) > W - 24 - left_end:
        prompts.pop(0)
    x = W - 24 - sum(_steam_prompt_width(f_small, k, l, arrows) for k, l in prompts) - 22 * (len(prompts) - 1)
    for key_, label in prompts:
        _steam_prompt(c, f_small, x, cyb, key_, label, arrows)
        x += _steam_prompt_width(f_small, key_, label, arrows) + 22
    draw_steam_menu(c, f_small, f_row, by)


def rd_file(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def card2_info():
    st = sdcard.status() if sdcard is not None else None
    if not st:
        return "none"
    u = sdcard.usage(st["mount"])
    return ("%.1f / %.1f GB free" % (u[0] / 1e9, u[1] / 1e9) if u else "mounted") + (" (read-only)" if st.get("ro") else "")


def _uptime_text():
    try:
        sec = int(float(rd_file("/proc/uptime").split()[0]))
    except (IndexError, ValueError):
        return "n/a"
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    return ("%dd " % d if d else "") + "%dh %02dm" % (h, rem // 60)


def _mem_text():
    kb = {}
    for l in rd_file("/proc/meminfo").splitlines():
        parts = l.replace(":", " ").split()
        if len(parts) >= 2 and parts[1].isdigit():
            kb[parts[0]] = int(parts[1])
    if "MemTotal" not in kb:
        return "n/a"
    free = kb.get("MemAvailable", kb.get("MemFree", 0))
    return "%d / %d MB free" % (free // 1024, kb["MemTotal"] // 1024)


def _cpu_text():
    n = os.cpu_count() or 1
    model = ""
    for l in rd_file("/proc/cpuinfo").splitlines():
        if l.lower().startswith(("model name", "hardware")) and ":" in l:
            model = l.split(":", 1)[1].strip()
            break
    return ("%s x%d" % (model, n)) if model else "%d core%s" % (n, "" if n == 1 else "s")


def _temp_text():
    for path in sorted(glob.glob("/sys/class/thermal/thermal_zone*/temp")):
        try:
            return "%.0f C" % (int(rd_file(path).strip()) / 1000.0)
        except ValueError:
            continue
    return "n/a"


def _load_text():
    p = rd_file("/proc/loadavg").split()
    return " ".join(p[:3]) if len(p) >= 3 else "n/a"


def _rootfs_text():
    try:
        st = os.statvfs("/")
        return "%.1f / %.1f GB free" % (st.f_bavail * st.f_frsize / 1e9, st.f_blocks * st.f_frsize / 1e9)
    except OSError:
        return "n/a"


def settings_info():
    build = "".join(l[9:] for l in rd_file("/etc/rgos-release").splitlines() if l.startswith("BUILD_ID="))
    try:
        st = os.statvfs(ROMS_ROOT)
        space = "%.1f / %.1f GB free" % (st.f_bavail * st.f_frsize / 1e9, st.f_blocks * st.f_frsize / 1e9)
    except OSError:
        space = "not mounted"
    vol, bat, bri = read_volume(), read_battery(), read_brightness()
    return [("RG OS build", build or "unknown"), ("Device", DEVICE_ID), ("Kernel", os.uname().release),
            ("ROMS partition", space), ("SD card 2", card2_info()), ("Volume", "%d%%" % vol[0] if vol else "n/a"),
            ("Battery", ("%d%% %s" % (max(0, min(100, bat[0])), bat[1].lower())) if bat else "n/a"),
            ("Brightness", "%d%%" % bri[0] if bri else "n/a"),
            ("Buttons", "mapped" if os.path.exists(BTN_MAP) else "default codes"),
            ("A/B buttons", "swapped" if swap_ab_on() else "normal"),
            ("DPAD to joystick", "on" if dpad_joy_on() else "off"),
            ("CPU", _cpu_text()), ("CPU temp", _temp_text()), ("Load average", _load_text()),
            ("Memory", _mem_text()), ("System storage", _rootfs_text()), ("Uptime", _uptime_text()),
            ("Resolution", "%dx%d" % (W, H))]


BTN_MAP = os.environ.get("RGOS_BTNMAP", "/var/lib/rgos/button-map.json")
SWAP_AB = os.environ.get("RGOS_SWAPAB", "/var/lib/rgos/swap-ab")
DPAD_JOY = os.environ.get("RGOS_DPADJOY", "/var/lib/rgos/dpad-joystick")


def restart_hub():
    if os.environ.get("RGOS_WINDOWED") == "1":
        return

    def hubs():
        found = []
        for d in os.listdir("/proc"):
            if d.isdigit() and int(d) != os.getpid():
                try:
                    with open("/proc/%s/cmdline" % d, "rb") as f:
                        cmd = f.read().split(b"\0")
                except OSError:
                    continue
                if any(c.endswith(b"rgos-input") for c in cmd[:3]) and b"reset-buttons" not in cmd:
                    found.append(int(d))
        return found
    for pid in hubs():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    t0 = time.time()
    while hubs() and time.time() - t0 < 4:
        time.sleep(0.1)
    for pid in hubs():
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        lg = open("/var/log/rgos-input.log", "a")
    except OSError:
        lg = subprocess.DEVNULL
    subprocess.Popen(["python3", "/opt/rgos/rgos-input"], stdin=subprocess.DEVNULL, stdout=lg, stderr=lg,
                     start_new_session=True)


def dpad_joy_on():
    return os.path.exists(DPAD_JOY)


def set_dpad_joy(on):
    """DPAD to joystick: the input hub watches this file, so no restart is needed."""
    try:
        if on:
            os.makedirs(os.path.dirname(DPAD_JOY), exist_ok=True)
            open(DPAD_JOY, "w").close()
        elif os.path.exists(DPAD_JOY):
            os.unlink(DPAD_JOY)
    except OSError:
        return False
    return True


def swap_ab_on():
    return os.path.exists(SWAP_AB)


def set_swap_ab(on):
    try:
        if on:
            os.makedirs(os.path.dirname(SWAP_AB), exist_ok=True)
            open(SWAP_AB, "w").close()
        elif os.path.exists(SWAP_AB):
            os.unlink(SWAP_AB)
    except OSError:
        return False
    return True


class ButtonMap:
    PROMPTS = [("A", 0x131, False), ("B", 0x130, False), ("X", 0x133, False), ("Y", 0x134, False),
               ("L", 0x136, False), ("R", 0x137, False), ("SELECT", 0x13a, False), ("START", 0x13b, False),
               ("D-pad UP", 0x220, False), ("D-pad DOWN", 0x221, False), ("D-pad LEFT", 0x222, False),
               ("D-pad RIGHT", 0x223, False), ("MENU (home) button", 0x13c, True), ("L2 / left trigger", 0x138, True),
               ("R2 / right trigger", 0x139, True), ("L3 (click left stick)", 0x13d, True), ("R3 (click right stick)", 0x13e, True)]
    STICK_BTNS = (0x13d, 0x13e)
    TIMEOUT, OPT_TIMEOUT, GAP = 25.0, 5.0, 0.5
    STICKS = [("LEFT stick", (0x00, 0x01)), ("RIGHT stick", (0x03, 0x04))]
    CENTER_SETTLE, CENTER_TIME = 0.6, 2.0
    STICK_IDLE, STICK_TIMEOUT = 8.0, 30.0
    REACH, MOVED = 0.5, 0.15
    MIN_SIDE = 0.3

    def __init__(self):
        self.flag, self.rawf = os.path.join(RUN_DIR, "keys.probe"), os.path.join(RUN_DIR, "keys.raw")
        try:
            os.makedirs(RUN_DIR, exist_ok=True)
            os.unlink(self.rawf)
        except OSError:
            pass
        try:
            os.unlink(os.path.join(RUN_DIR, "sticks.raw"))
        except OSError:
            pass
        try:
            open(self.flag, "w").close()
        except OSError:
            pass
        self.state, self.step, self.msg = "wait", 0, ""
        self.t0 = self.tstate = time.time()
        self.stamp, self.keys, self.used, self.last_name = None, {}, set(), ""
        self.skipped = []
        self.failed_in = ""
        self.sticksf = os.path.join(RUN_DIR, "sticks.raw")
        self.has_sticks = False
        self.sv = {}
        self.sticks = []
        self.cstick = 0
        self.center, self.cal = {}, {}
        self.csamples = {}
        self.ext, self.reached, self.tgrow, self.moved = {}, set(), 0.0, False

    def stop(self):
        for f in (self.flag, self.rawf, self.sticksf):
            try:
                os.unlink(f)
            except OSError:
                pass

    def _read(self):
        try:
            with open(self.rawf) as f:
                n, name, t, c, sg = f.read().rstrip("\n").split("\t")
            return n, name, int(t), int(c), int(sg)
        except (OSError, ValueError):
            return None

    def _fail(self, msg):
        self.failed_in = self.state
        self.state, self.msg = "fail", msg
        self.stop()

    def can_resume(self):
        return self.state == "fail" and self.failed_in in ("wait", "prompt", "apply")

    def resume(self, now=None):
        if not self.can_resume():
            return
        now = now or time.time()
        was = self.failed_in
        for f in (self.rawf, self.sticksf):
            try:
                os.unlink(f)
            except OSError:
                pass
        try:
            open(self.flag, "w").close()
        except OSError:
            pass
        self.msg, self.stamp, self.t0, self.tstate = "", None, now, now
        self.state = "apply" if was == "apply" else "wait"

    def total(self):
        return len(self.PROMPTS) - (0 if self.has_sticks else len(self.STICK_BTNS))

    def _next(self, now):
        self.step += 1
        while self.step < len(self.PROMPTS) and self.PROMPTS[self.step][1] in self.STICK_BTNS and not self.has_sticks:
            self.step += 1
        if self.step < len(self.PROMPTS):
            self.state, self.tstate = "prompt", now
        else:
            self._start_sticks(now)

    def _read_sticks(self):
        try:
            with open(self.sticksf) as f:
                ax = json.load(f).get("ax") or {}
            self.sv = {int(k): (int(v[0]), int(v[1]), int(v[2])) for k, v in ax.items()}
        except (OSError, ValueError, TypeError, IndexError, AttributeError):
            self.sv = {}
        return self.sv

    def _start_sticks(self, now):
        self._read_sticks()
        self.sticks = [i for i, (_, axes) in enumerate(self.STICKS) if all(a in self.sv for a in axes)]
        if not self.sticks:
            self.state, self.tstate = "apply", now
            return
        self.cstick, self.center, self.csamples, self.cal = 0, {}, {a: [] for i in self.sticks for a in self.STICKS[i][1]}, {}
        self.state, self.tstate = "scenter", now

    def _begin_roll(self, now):
        axes = self.STICKS[self.sticks[self.cstick]][1]
        self.ext = {a: [self.center[a], self.center[a]] for a in axes}
        self.reached, self.moved, self.tgrow = set(), False, now
        self.state, self.tstate = "sroll", now

    def _next_stick(self, now):
        self.cstick += 1
        if self.cstick < len(self.sticks):
            self._begin_roll(now)
        else:
            self.state, self.tstate = "apply", now

    def _half(self, a):
        _, lo, hi = self.sv[a]
        return max((hi - lo) / 2.0, 1.0)

    def _roll_update(self, now):
        name, axes = self.STICKS[self.sticks[self.cstick]]
        if any(a not in self.sv for a in axes):
            return
        for a in axes:
            v, c, half = self.sv[a][0], self.center[a], self._half(a)
            e = self.ext[a]
            if v < e[0] - 0.01 * half or v > e[1] + 0.01 * half:
                self.tgrow = now
            e[0], e[1] = min(e[0], v), max(e[1], v)
            for sign, key in ((-1, (a, -1)), (1, (a, 1))):
                if (v - c) * sign >= self.REACH * half:
                    self.reached.add(key)
            if abs(v - c) >= self.MOVED * half:
                self.moved = True
        dirs = sum(1 for a in axes for sg in (-1, 1) if (self.ext[a][1] - self.center[a] if sg > 0 else self.center[a] - self.ext[a][0]) >= self.MOVED * self._half(a))
        if self.moved and dirs >= 2 and now - self.tgrow >= (1.0 if len(self.reached) >= 4 else 3.0):
            for a in axes:
                c, half, (_, lo, hi) = self.center[a], self._half(a), self.sv[a]
                e_lo = self.ext[a][0] if c - self.ext[a][0] >= self.MIN_SIDE * half else lo
                e_hi = self.ext[a][1] if self.ext[a][1] - c >= self.MIN_SIDE * half else hi
                self.cal[a] = (c, e_lo, e_hi)
            return self._next_stick(now)
        idle = now - self.tstate
        if (not self.moved and idle > self.STICK_IDLE) or idle > self.STICK_TIMEOUT:
            self.skipped.append(name.split(" ")[0].lower() + " stick")
            self._next_stick(now)

    def stick_view(self):
        if self.state not in ("scenter", "sroll") or not self.sticks:
            return None
        name, axes = self.STICKS[self.sticks[min(self.cstick, len(self.sticks) - 1)]]
        if self.state == "scenter":
            name, axes = "both sticks", self.STICKS[self.sticks[0]][1]
        if any(a not in self.sv for a in axes):
            return name, 0.0, 0.0, set()
        def norm(a):
            v, lo, hi = self.sv[a]
            return max(-1.0, min(1.0, (v - (self.center.get(a, (lo + hi) / 2.0))) / self._half(a)))
        reached = {(axes.index(a), sg) for (a, sg) in self.reached if a in axes}
        return name, norm(axes[0]), norm(axes[1]), reached

    def update(self):
        now = time.time()
        if self.state in ("done", "fail"):
            return
        if self.state == "apply":
            try:
                os.makedirs(os.path.dirname(BTN_MAP), exist_ok=True)
                out = {"keys": self.keys}
                if self.cal:
                    out["sticks"] = {str(a): [round(v, 1) for v in cal] for a, cal in self.cal.items()}
                with open(BTN_MAP + ".tmp", "w") as f:
                    json.dump(out, f)
                os.replace(BTN_MAP + ".tmp", BTN_MAP)
                set_swap_ab(False)
                restart_hub()
            except Exception as e:
                return self._fail("Could not save: %s" % e)
            self.stop()
            self.state = "done"
            self.msg = "Saved %d buttons%s%s. Press buttons in the menu to test them." % (
                len(self.keys), (" and %d stick%s" % (len(self.cal) // 2, "" if len(self.cal) == 2 else "s")) if self.cal else "",
                (" (skipped: %s)" % ", ".join(self.skipped)) if self.skipped else "")
            return
        if self.state in ("scenter", "sroll"):
            self._read_sticks()
            if self.state == "scenter":
                if now - self.tstate >= self.CENTER_SETTLE:
                    for a, lst in self.csamples.items():
                        if a in self.sv:
                            lst.append(self.sv[a][0])
                if now - self.tstate >= self.CENTER_TIME:
                    for a, lst in self.csamples.items():
                        self.center[a] = sorted(lst)[len(lst) // 2] if lst else (self.sv[a][1] + self.sv[a][2]) / 2.0 if a in self.sv else 0
                    self._begin_roll(now)
            else:
                self._roll_update(now)
            return
        r = self._read()
        label, canon, optional = self.PROMPTS[min(self.step, len(self.PROMPTS) - 1)]
        if self.state == "wait":
            if now - self.t0 > 1.0:
                self.has_sticks = any(all(a in self._read_sticks() for a in axes) for _, axes in self.STICKS)
                self.state, self.tstate = "prompt", now
                if r:
                    self.stamp = r[0]
            return
        if self.state == "prompt":
            limit = self.OPT_TIMEOUT if optional else self.TIMEOUT
            if now - self.tstate > limit:
                if optional:
                    self.skipped.append(label.split(" ")[0])
                    return self._next(now)
                if r is None and now - self.t0 > 8:
                    return self._fail("The input hub is not running (no key events).")
                return self._fail("No button press detected for %s." % label)
            if r and r[0] != self.stamp and now - self.tstate > self.GAP:
                self.stamp = r[0]
                _, name, t, c, sg = r
                key = "%s|%d:%d:%d" % (name, t, c, sg)
                if key in self.used:
                    return
                self.used.add(key)
                self.keys[key] = canon
                self.last_name = name
                self._next(now)
            elif r and r[0] != self.stamp:
                self.stamp = r[0]

    def lines(self):
        if self.state == "wait":
            return ["Starting...", "Do not press anything yet"]
        if self.state == "prompt":
            label, _, optional = self.PROMPTS[self.step]
            return ["Press %s" % label, "(wait a few seconds to skip: this one is optional)" if optional else ""]
        if self.state == "scenter":
            return ["Let go of both sticks", "Leave them centred for a moment"]
        if self.state == "sroll":
            return ["Roll the %s around" % self.STICKS[self.sticks[self.cstick]][0], "Push it to the edge and go all the way round, slowly"]
        if self.state == "apply":
            return ["Applying...", ""]
        if self.state == "fail" and self.can_resume():
            return [self.msg, "Nothing is lost: only this step is asked again"]
        return [self.msg]


VOLUME_FILE = os.environ.get("RGOS_VOLUME_FILE", os.path.join(RUN_DIR, "volume"))


CALIB_DONE = os.environ.get("RGOS_CALIBDONE", "/var/lib/rgos/calibrated")


def calibration_needed():
    if os.path.exists(CALIB_DONE):
        return False
    if os.path.exists(BTN_MAP):
        mark_calibrated()
        return False
    return True


def mark_calibrated():
    try:
        os.makedirs(os.path.dirname(CALIB_DONE), exist_ok=True)
        open(CALIB_DONE, "w").close()
    except OSError as e:
        log("could not write %s: %r" % (CALIB_DONE, e))


def read_volume():
    try:
        with open(VOLUME_FILE) as f:
            v, stamp = f.read().split()[:2]
        return int(v), stamp
    except (OSError, ValueError):
        return None


BRIGHT_FILE = os.environ.get("RGOS_BRIGHT_FILE", os.path.join(RUN_DIR, "brightness"))
BATT_FILE = os.environ.get("RGOS_BATT_FILE", os.path.join(RUN_DIR, "battery"))
SCREENOFF_FILE = os.path.join(RUN_DIR, "screenoff")


def read_brightness():
    try:
        with open(BRIGHT_FILE) as f:
            v, stamp = f.read().split()[:2]
        return int(v), stamp
    except (OSError, ValueError):
        return None


def read_online():
    """True while a wireless interface reports its link up (the Deck's top-right Wi-Fi icon)."""
    try:
        for name in sorted(os.listdir("/sys/class/net")):
            if name.startswith(("wlan", "wlp", "wl")) and rd_file("/sys/class/net/%s/operstate" % name).strip() == "up":
                return True
    except OSError:
        pass
    return False


def read_battery():
    try:
        supplies = sorted(glob.glob("/sys/class/power_supply/*"))
        batteries = [p for p in supplies if rd_file(os.path.join(p, "type")).strip().lower() == "battery"]
        batteries.sort(key=lambda p: ("batt" not in os.path.basename(p).lower(), p))
        for node in batteries:
            raw = rd_file(os.path.join(node, "capacity")).strip().rstrip("%")
            if raw.lstrip("+-").isdigit():
                pct = max(0, min(100, int(raw)))
                status = rd_file(os.path.join(node, "status")).strip().replace("_", " ") or "Unknown"
                return pct, status
    except (OSError, ValueError):
        pass

    try:
        with open(BATT_FILE) as f:
            pct, status, stamp = f.read().split()[:3]
        if time.time() - int(float(stamp)) > 60:
            return None
        pct = max(0, min(100, int(pct.rstrip("%"))))
        status = status.replace("_", " ").strip() or "Unknown"
        return pct, status
    except (OSError, ValueError):
        return None


KB_LAYERS = [["1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm._@"],
             ["1234567890", "QWERTYUIOP", "ASDFGHJKL-", "ZXCVBNM._@"],
             ["!@#$%^&*()", "-_=+[]{};:", "'\",<>/?\\|`", "~.@"]]
KB_LAYER_NAMES = ["abc", "ABC", "#+="]
KB_BOTTOM = ["Layer", "Space", "Del", "OK", "Cancel"]


class Kbd:
    def __init__(self, field, title, text, secret):
        self.field, self.title, self.text, self.secret = field, title, text, secret
        self.show, self.layer, self.row, self.col = not secret, 0, 1, 0

    def keys(self, row=None):
        r = self.row if row is None else row
        return list(KB_LAYERS[self.layer][r]) if r < 4 else KB_BOTTOM

    def move(self, dr, dc):
        if dr:
            self.row = (self.row + dr) % 5
        if dc:
            self.col = (self.col + dc) % len(self.keys())
        self.col = min(self.col, len(self.keys()) - 1)

    def press(self):
        k = self.keys()[self.col]
        if self.row < 4:
            if len(self.text) < 64:
                self.text += k
        elif k == "Layer":
            self.layer = (self.layer + 1) % 3
        elif k == "Space":
            if len(self.text) < 64:
                self.text += " "
        elif k == "Del":
            self.text = self.text[:-1]
        elif k == "OK":
            return "ok"
        elif k == "Cancel":
            return "cancel"
        return None


_WRAPN = {}


def wrap_n(font, text, width, n):
    """Word-wrap to at most n lines. Memoised: the details panel re-wraps the same description every frame."""
    key = (font, text, width, n)
    hit = _WRAPN.get(key)
    if hit is None:
        if len(_WRAPN) > 500:
            _WRAPN.clear()
        hit = _WRAPN[key] = _wrap_n(font, text, width, n)
    return list(hit)


def _wrap_n(font, text, width, n):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if font.size(t)[0] <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > n:
        lines = lines[:n]
        lines[-1] = fit(font, lines[-1] + " ...", width)
    return lines


def tail_fit(font, text, width):
    while text and font.size(text)[0] > width:
        text = text[1:]
    return text


def art_shrink(path, max_side=480):
    """Downscale a freshly downloaded cover so cards load quickly. Returns the file to keep."""
    try:
        img = pygame.image.load(path)
        iw, ih = img.get_size()
        if max(iw, ih) <= max_side:
            return path
        k = max_side / float(max(iw, ih))
        img = img.convert_alpha()
        img = pygame.transform.smoothscale(img, (max(1, int(iw * k)), max(1, int(ih * k))))
        out = os.path.splitext(path)[0] + ".png"
        tmp = os.path.splitext(path)[0] + ".tmp.png"
        pygame.image.save(img, tmp)
        os.replace(tmp, out)
        if out != path:
            os.remove(path)
        return out
    except Exception:
        return path


def log(msg):
    sys.stderr.write("%s menu: %s\n" % (time.strftime("%H:%M:%S"), msg))
    sys.stderr.flush()


MUSIC_DIRS = (os.path.join(os.path.dirname(os.path.abspath(__file__)), "music"),
              os.path.join(ROMS_ROOT, "music"))
MUSIC_EXTS = (".mp3", ".ogg", ".oga", ".wav", ".flac", ".mod", ".xm", ".it", ".s3m")
_music_playlist = []
_music_last = None

_music_scan = [0.0, []]


def _music_tracks_cached():
    now = time.monotonic()
    if now - _music_scan[0] > 10.0:
        _music_scan[1] = _music_tracks()
        _music_scan[0] = time.monotonic()
    return _music_scan[1]


def _music_tracks():
    tracks = []
    for root in MUSIC_DIRS:
        if not os.path.isdir(root):
            continue
        for base, _dirs, names in os.walk(root):
            for name in names:
                if name.lower().endswith(MUSIC_EXTS):
                    path = os.path.join(base, name)
                    if path not in tracks:
                        tracks.append(path)
    return tracks

MUSIC_RETRY_S = 30.0
_music_retry_at = [0.0]


def _music_tick(now=None):
    """Per-frame check: start the next track once the current one has ended.

    When nothing can be played (a track SDL_mixer cannot decode, no audio device, ...) the
    attempt is not repeated every frame: each try walks the music folders, re-tries every
    track and logs, which made every menu crawl. It backs off for MUSIC_RETRY_S instead."""
    now = time.monotonic() if now is None else now
    if now < _music_retry_at[0]:
        return
    if pygame.mixer.get_init() and not pygame.mixer.music.get_busy() and (_music_playlist or _music_tracks_cached()):
        _music_retry_at[0] = 0.0 if _play_next_launcher_track() else now + MUSIC_RETRY_S


def _start_launcher_music():
    global _music_playlist, _music_last
    tracks = _music_tracks()
    if not tracks:
        return
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(22050, -16, 2, 2048)
        _music_playlist = tracks[:]
        import random
        random.shuffle(_music_playlist)
        if len(_music_playlist) > 1 and _music_playlist[0] == _music_last:
            _music_playlist.append(_music_playlist.pop(0))
        if not _play_next_launcher_track():
            _music_retry_at[0] = time.monotonic() + MUSIC_RETRY_S
        log("launcher music: %d track(s) found" % len(tracks))
    except Exception as e:
        log("launcher music unavailable: %s" % e)

def _play_next_launcher_track():
    global _music_playlist, _music_last
    while _music_playlist:
        path = _music_playlist.pop(0)
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.55)
            pygame.mixer.music.play()
            _music_last = path
            log("launcher music playing: %s" % path)
            return True
        except Exception as e:
            log("launcher music skipped %s: %s" % (path, e))
    tracks = _music_tracks()
    if tracks:
        import random
        _music_playlist = tracks[:]
        random.shuffle(_music_playlist)
        if len(_music_playlist) > 1 and _music_playlist[0] == _music_last:
            _music_playlist.append(_music_playlist.pop(0))
        while _music_playlist:
            path = _music_playlist.pop(0)
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(0.55)
                pygame.mixer.music.play()
                _music_last = path
                log("launcher music playing: %s" % path)
                return True
            except Exception as e:
                log("launcher music skipped %s: %s" % (path, e))
    return False


class FrameProfiler:
    """Opt-in frame timing (RGOS_PROFILE=1). Every `interval` seconds it logs the average frame cost
    and the slowest frame split into input/update, draw, present and background warm-up, so a laggy
    screen shows exactly which part is slow. The idle wait in clock.tick() is not counted."""
    SLOW_MS = 40.0

    def __init__(self, enabled, emit, interval=5.0, clock=time.monotonic):
        self.enabled, self.emit, self.interval, self.clock = enabled, emit, interval, clock
        self._reset(clock())

    def _reset(self, now):
        self.t0, self.n, self.total, self.slow, self.worst = now, 0, 0.0, 0, None

    def frame(self, update, draw, present, warm, label=""):
        """Phase durations in seconds for one frame."""
        if not self.enabled:
            return
        total = update + draw + present + warm
        self.n += 1
        self.total += total
        if total * 1000.0 >= self.SLOW_MS:
            self.slow += 1
        if self.worst is None or total > self.worst[0]:
            self.worst = (total, update, draw, present, warm, label)
        now = self.clock()
        if now - self.t0 >= self.interval and self.n:
            avg = self.total / self.n * 1000.0
            w = self.worst
            self.emit("perf: %d frames, avg %.1f ms/frame (work only), %d over %d ms; worst %.0f ms = "
                      "update %.0f + draw %.0f + present %.0f + warm %.0f [%s]"
                      % (self.n, avg, self.slow, self.SLOW_MS, w[0] * 1000, w[1] * 1000, w[2] * 1000,
                         w[3] * 1000, w[4] * 1000, w[5]))
            self._reset(now)


_BOOST = uiboost.UiBoost()
atexit.register(_BOOST.restore)


def _on_term(_sig, _frm):
    _BOOST.restore()
    sys.exit(0)


def main():
    windowed = os.environ.get("RGOS_WINDOWED") == "1"
    if not windowed:
        try:
            signal.signal(signal.SIGTERM, _on_term)  # SIGTERM would skip atexit and leave the clocks pinned
        except ValueError:
            pass
    ensure_folders()
    if not windowed and os.environ.get("RGOS_VIDEO") == "fb":
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    fb = None
    win = None
    if not windowed and os.environ.get("RGOS_VIDEO") != "fb":
        try:
            win = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            log("video: SDL %s %s" % (pygame.display.get_driver(), win.get_size()))
            win.fill((0, 0, 0))
            pygame.display.flip()
        except pygame.error as e:
            log("SDL video failed (%s); falling back to /dev/fb0" % e)
    elif windowed:
        win = pygame.display.set_mode((W, H))
    if win is None:
        pygame.display.quit()
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.display.init()
        win = pygame.display.set_mode((W, H))
        fb = fbout.FbOut()
        log("video: framebuffer " + fb.info)
    pygame.mouse.set_visible(False)
    if not windowed:
        fbout.set_graphics(True)
    canvas = pygame.Surface((W, H))
    fpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    FONT_PATH[0] = fpath if os.path.exists(fpath) else None
    if os.path.exists(fpath):
        mk = lambda s: CFont(pygame.font.Font(fpath, s))
    else:
        mk = lambda s: CFont(pygame.font.Font(None, int(s * 1.3)))
    f_logo, f_big, f_row, f_small, f_tiny = mk(30), mk(22), mk(19), mk(14), mk(11)
    TT_FONTS = (f_logo, f_big, f_row, f_small, f_tiny)
    PX_FONTS = tuple(PixelFont(px) for px in (30, 22, 18, 14, 11))

    classic_ui = ThemedClassic(W, H)
    inp = Input()
    all_games = scan_roms()
    rescan = Rescan()
    _gcache = [None, {}]

    def games_of(sid):
        if _gcache[0] is not all_games:
            by = {}
            for g in all_games:
                by.setdefault(g["sid"], []).append(g)
            _gcache[0], _gcache[1] = all_games, by
        return _gcache[1].get(sid, [])
    vsys = visible_systems(all_games)
    NO_SYSTEM = ("", "", "", (), "")
    state = load_state()
    theme_id = apply_theme(state.get("theme"))
    launcher_id = LAUNCHERS[launcher_index(state.get("launcher"))][0]

    _rcache = [None, None, []]

    def recent_games():
        rec = tuple(state.get("recent", []))
        if _rcache[0] is not all_games or _rcache[1] != rec:
            by_path = {g["path"]: g for g in all_games}
            _rcache[0], _rcache[1], _rcache[2] = all_games, rec, [by_path[p] for p in rec if p in by_path]
        return _rcache[2]

    favorite_paths = set(load_favorites())

    _fbp = [None, {}]
    _fav_c = [0.0, None, []]
    _fav_m = [None]

    def favorite_games():
        now = time.monotonic()
        if _fbp[0] is not all_games:
            _fbp[0], _fbp[1] = all_games, {g["path"]: g for g in all_games}
            _fav_c[0] = 0.0
        if now - _fav_c[0] >= 0.5 or _fav_c[0] > now:
            try:
                mt = os.stat(FAVORITES_FILE).st_mtime_ns
            except OSError:
                mt = None
            if _fav_c[0] == 0.0 or mt != _fav_m[0] or _fav_c[0] > now:
                by_path = _fbp[1]
                _fav_m[0] = mt
                _fav_c[2] = [by_path[p] for p in load_favorites() if p in by_path]
            _fav_c[0] = now
        return _fav_c[2]

    def fav_changed():
        _fav_c[0] = 0.0

    wifi_status = bg_cached(wifictl.status, 1.0)
    settings_info_c = bg_cached(settings_info, 1.0)

    def settings_text():
        wst = wifi_status()
        spl = {"on": "On: video and sound", "silent": "On: video only", "off": "Off"}[splash.mode_of(state)]
        return {"theme": ("Theme", "%s   (%d of %d)   A opens the list" % (THEMES[theme_index(theme_id)][1], theme_index(theme_id) + 1, len(THEMES))),
                "launcher": ("Launcher", "%s   (%d of %d)   A opens the list" % (LAUNCHERS[launcher_index(launcher_id)][1], launcher_index(launcher_id) + 1, len(LAUNCHERS))),
                "splash": ("Startup splash", spl + "   (plays once at power on)   X previews"),
                "emulators": ("Emulators", "Choose the RetroArch core used for each system"),
                "bios": ("Missing BIOS check", (bios_summary_text(bios_cache[1]) + "   A opens it") if bios_cache else "Find missing emulator BIOS files and where they go"),
                "artwork": ("Game artwork", art_text()),
                "bmap": ("Map buttons", "Teach RG OS which physical button is A, B, D-pad, ... (if buttons are wrong)"),
                "swapab": ("Swap A / B buttons", ("ON" if swap_ab_on() else "off") + "   A toggles it (use if A and B act the wrong way round)"),
                "dpadjoy": ("DPAD to joystick", ("ON" if dpad_joy_on() else "off") + "   A toggles it (D-pad moves the left stick in games; Menu+Select in a game turns it on, hold turns it off)"),
                "wifi": ("Wi-Fi", wifictl.status_text(wst)),
                "bluetooth": ("Bluetooth", {None: "Pair controllers, keyboards and headsets", True: "On   A opens the device list", False: "Off   A opens the device list"}[btm.on]),
                "ssh": ("SSH / file transfer", ("On: ssh or sftp root@%s" % wst["ip"] if wst["ip"] else "On: connect Wi-Fi to use it") if ssh_info()["running"] else "Off   A opens it"),
                "info": ("Information", "Build, kernel, storage, battery, volume and input status")}

    def _xmb_items(cat):
        if cat == "settings":
            txt = settings_text()
            return [{"label": txt[r][0], "sub": txt[r][1], "icon": r, "act": ("setting", i)} for i, r in enumerate(SETTINGS_ROWS)]
        if cat == "games":
            if not vsys:
                return [{"label": "No games found", "sub": "Copy ROMs to the ROMS card, then press X to rescan", "icon": "games", "act": None}]
            return [{"label": sy[4], "sub": "%d %s" % (len(games_of(sy[0])), "port" if sy[0] == "ports" else "game") + ("" if len(games_of(sy[0])) == 1 else "s"),
                     "icon": system_icon(sy[0]), "act": ("system", i)} for i, sy in enumerate(vsys)]
        if cat in ("recents", "favorites"):
            gl = recent_games() if cat == "recents" else favorite_games()
            if not gl:
                return [{"label": "No recent games" if cat == "recents" else "No favorites yet",
                         "sub": "Games you play show up here" if cat == "recents" else "Press Y on a game to add it", "icon": cat, "act": None}]
            return [{"label": g["title"], "sub": sysname.get(g["sid"], g["tag"]), "icon": system_icon(g["sid"]), "act": ("launch", g)} for g in gl]
        if cat == "tools":
            return [{"label": t[1], "sub": t[2], "icon": "files" if t[3] == "@view:files" else "tools", "act": ("tool", t[3])} for t in TOOLS]
        return [{"label": "Power Off", "sub": "Shut down RG OS", "icon": "power", "act": ("power",)}]

    _xic = {}

    def xmb_items(cat, fresh=False):
        key, now = (theme_id, launcher_id, id(all_games), id(vsys)), time.monotonic()
        hit = _xic.get(cat)
        if not fresh and hit is not None and hit[1] == key and (now - hit[0] < 1.0 or now - last_act < 0.6):
            return hit[2]
        items = _xic[cat] = (now, key, _xmb_items(cat))
        return items[2]

    view, home_idx, sys_idx, idx_by = "home", 0, 0, {}
    bmap = None
    set_idx, tool_idx, kb = 0, 0, None
    art_idx = 0
    art_index = artwork.ArtIndex(ROMS_ROOT)
    art = {"sc": None, "key": artwork.load_key(ROMS_ROOT), "msg": "", "until": 0.0, "ver": 0, "seen": 0, "seen_at": 0.0, "cnt": (0.0, 0, 0)}

    def art_on():
        return state.get("artwork", True) is not False

    meta_cache = {}

    def game_meta(g, settled=True):
        """Saved SteamGridDB/Wikipedia details for a game; re-read from the card at most every 3 s.
        While the cursor is moving (settled=False) nothing is read: the cached copy, or {}, is used."""
        now = time.monotonic()
        ent = meta_cache.get(g["path"])
        if ent is None or now - ent[0] > 3.0:
            if not settled:
                return ent[1] if ent else {}
            if len(meta_cache) > 200:
                meta_cache.clear()
            ent = meta_cache[g["path"]] = (now, artwork.load_meta(ROMS_ROOT, g["sid"], g["path"]))
        return ent[1]

    def art_note(msg):
        art["msg"], art["until"] = msg, time.time() + 5

    def art_scraper():
        sc = art["sc"]
        if sc is None or (not sc.running and sc.key != art["key"]):
            sc = art["sc"] = artwork.Scraper(ROMS_ROOT, art["key"], art_index, post=art_shrink)
        return sc

    def art_start(retry):
        sc = art_scraper()
        if sc.running:
            sc.stop()
        elif not artwork.valid_key(art["key"]):
            art_note("Set your SteamGridDB API key first")
        elif not all_games:
            art_note("No games found yet: copy ROMs to the ROMS card first")
        else:
            sc.start(all_games, retry)

    def art_counts():
        now = time.monotonic()
        if now - art["cnt"][0] > 2.0:
            art["cnt"] = (now, art_index.count(all_games), len(all_games))
        return art["cnt"][1], art["cnt"][2]

    def art_text():
        sc = art["sc"]
        s = sc.snapshot() if sc is not None else None
        if s and s["state"] == "running":
            return "Downloading %d of %d   A opens it" % (s["done"], s["total"])
        if not artwork.valid_key(art["key"]):
            return "Download covers from SteamGridDB   A opens it (free API key needed)"
        return "SteamGridDB covers are %s   A opens it" % ("shown" if art_on() else "hidden")
    dd = None
    xmb_cat, xmb_sel, xmb_cx, xmb_vy, xmb_fade = XMB_START, {}, float(XMB_START), 0.0, 1.0
    xmb_cv, xmb_vv = 0.0, 0.0
    xmb_ret = [False]
    pending_acts = []
    sysname = {sy[0]: sy[4] for sy in SYSTEMS}

    def back_to(parent):
        if xmb_ret[0]:
            xmb_ret[0] = False
            return "home"
        return parent

    def dd_set(kind, oid):
        nonlocal theme_id, launcher_id
        if kind == "theme":
            theme_id = apply_theme(oid)
        else:
            launcher_id = LAUNCHERS[launcher_index(oid)][0]
    fm, fm_pop = None, None
    emu_idx = 0
    bios_cache, bios_scroll, bios_pos, bios_all = None, 0, 0.0, False
    ci = coreinstall.Installer(coreinstall.core_dir(ROMS_ROOT), names=CORE_NAMES)
    ci_rows, ci_idx = [], 0
    info_scroll, info_pos = 0, 0.0
    wconf, wscan, wf_idx, wf_msg, wf_msg_until, wf_pending = wifictl.load_conf(), wifictl.Scanner(), 0, "", 0.0, ("", False)
    btm, bt_idx = btctl.Manager(), 0
    btm.refresh()
    ssh_cache, ssh_msg_until = (0.0, sshctl.info()), 0.0

    _ssh_busy = [False]

    def _ssh_refresh():
        nonlocal ssh_cache
        try:
            ssh_cache = (time.time(), sshctl.info())
        except Exception:
            pass
        _ssh_busy[0] = False

    def ssh_info():
        if time.time() - ssh_cache[0] > 1.0 and not _ssh_busy[0]:
            _ssh_busy[0] = True
            threading.Thread(target=_ssh_refresh, daemon=True).start()
        return ssh_cache[1]

    def ssh_toggle():
        nonlocal ssh_cache, ssh_msg_until
        ssh_msg_until = time.time() + 30
        def job_():
            nonlocal ssh_cache, ssh_msg_until
            sshctl.set_enabled(not sshctl.enabled())
            ssh_cache, ssh_msg_until = (0.0, ssh_cache[1]), 0.0
        threading.Thread(target=job_, daemon=True).start()

    def wf_do(fn, msg, *args):
        nonlocal wf_msg, wf_msg_until, wconf
        wf_msg, wf_msg_until = msg, time.time() + 4

        def job_():
            nonlocal wconf
            fn(*args)
            wconf = wifictl.load_conf()
        threading.Thread(target=job_, daemon=True).start()
    last = next((g for g in all_games if g["path"] == state.get("last")), None)
    if last:
        sys_idx = next(i for i, sy in enumerate(vsys) if sy[0] == last["sid"])
        idx_by[last["sid"]] = games_of(last["sid"]).index(last)
    flow_t, flow_fx, flow_fv, flow_fade, flow_pos, flow_key, flow_grid = 0, 0.0, 0.0, 1.0, {}, None, False
    FLOW_HOME = {"games": (200, "Browse your systems"), "recents": (30, "Recently played"), "favorites": (48, "Your starred games"),
                 "tools": (140, "File manager and more"), "settings": (265, "Theme, Wi-Fi, Bluetooth..."), "power": (350, "Shut down")}

    _fcm = [None, None, None]

    def flow_cards():
        if view == "home":
            key, keep = ("home",), HOME_ITEMS
        elif view == "systems":
            key, keep = ("systems", id(all_games)), vsys
        else:
            keep = recent_games() if view == "recents" else favorite_games() if view == "favorites" else games_of(vsys[sys_idx][0] if vsys else "")
            key = (view, id(keep), len(keep), frozenset(favorite_paths), art["ver"], art_on())
        if _fcm[0] == key and _fcm[1] is keep:
            return _fcm[2]
        if view == "home":
            out = [{"id": hid, "title": lbl, "sub": FLOW_HOME.get(hid, (0, ""))[1], "hue": FLOW_HOME.get(hid, (0, ""))[0], "tag": "",
                    "abbr": "", "icon": hid, "fav": False} for hid, lbl in HOME_ITEMS]
        elif view == "systems":
            out = [{"id": sy[0], "title": sy[4], "sub": "%d game%s" % (len(games_of(sy[0])), "" if len(games_of(sy[0])) == 1 else "s"),
                    "hue": flow_hue(sy[0]), "tag": "", "abbr": sy[1], "icon": system_icon(sy[0]), "fav": False} for sy in vsys]
        else:
            out = [{"game": g, "title": g["title"], "sub": sysname.get(g["sid"], g["tag"]), "hue": flow_hue(g["sid"]), "tag": g["tag"],
                    "abbr": flow_abbr(g["title"]), "icon": None, "fav": g["path"] in favorite_paths,
                    "art": art_index.lookup(g["sid"], g["path"]) if art_on() else None} for g in keep]
        _fcm[0], _fcm[1], _fcm[2] = key, keep, out
        return out

    def flow_cur_key():
        return ("g:" + (vsys[sys_idx][0] if vsys else "")) if view == "games" else view
    rows, list_x, list_w, top_y, row_h = 8 + DY // 44, 20, 450 + DX, 84, 44
    PH = 352 + DY
    clock = pygame.time.Clock()
    rd_bri, rd_bat, rd_net = throttled(read_brightness, 0.1), throttled(read_battery, 10.0), throttled(read_online, 5.0)
    last_act, clk_at, clk = time.monotonic(), 0, ""
    IDLE_VIEWS = ("home", "systems", "games", "recents", "tools", "settings")
    code = None
    bri_seen, bri_show_until, bri_pct = None, 0.0, 0
    _b = read_brightness()
    if _b:
        bri_seen = _b[1]

    def launch(target, game=None):
        os.makedirs(RUN_DIR, exist_ok=True)
        with open(os.path.join(RUN_DIR, "launch"), "w") as f:
            f.write(target)
        if game:
            state["last"] = game["path"]
            state["recent"] = [game["path"]] + [p for p in state.get("recent", []) if p != game["path"]][:RECENT_MAX - 1]
        save_state(state)
        return EXIT_LAUNCH

    def present():
        if fb is not None:
            fb.present(canvas)
        else:
            if (W, H) == win.get_size():
                win.blit(canvas, (0, 0))
            else:
                fx, fy, fw, fh = fbout.fit_rect((W, H), win.get_size())
                if (fw, fh) != win.get_size():
                    win.fill((0, 0, 0))
                win.blit(pygame.transform.smoothscale(canvas, (fw, fh)), (fx, fy))
            pygame.display.flip()

    def play_splash(mode):
        path = splash.find_splash(DEVICE_ID, ROMS_ROOT)
        if not path:
            log("splash: no video found")
            return
        with open(path, "rb") as f:
            data = f.read()
        frames, conf, snd = splash.split_mjpeg(data), splash.read_conf(path), None
        log("splash: %s, %d frames at %g fps" % (path, len(frames), conf["fps"]))
        if mode == "on" and conf["sound"]:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(22050, -16, 1, 1024)
                snd = pygame.mixer.Sound(conf["sound"])
                snd.play()
            except Exception as e:
                log("splash: no sound (%s)" % e)
                snd = None

        def decode(b):
            return pygame.image.load(io.BytesIO(b), "frame.jpg").convert()

        def show(img):
            iw, ih = img.get_size()
            if (iw, ih) == (W, H):
                canvas.blit(img, (0, 0))
            else:
                sc = min(W / iw, H / ih)
                sw, sh = max(1, int(iw * sc)), max(1, int(ih * sc))
                canvas.fill((0, 0, 0))
                canvas.blit(pygame.transform.smoothscale(img, (sw, sh)), ((W - sw) // 2, (H - sh) // 2))
            present()

        inp.poll()
        n = splash.play(data, frames, conf["fps"], decode, show, lambda: bool(inp.poll()))
        log("splash: %d of %d frames shown" % (n, len(frames)))
        if snd:
            snd.stop()
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        canvas.fill(BG)
        present()

    if os.environ.get("RGOS_SPLASH") == "always" or not os.path.exists(SPLASH_DONE):
        try:
            os.makedirs(RUN_DIR, exist_ok=True)
            open(SPLASH_DONE, "w").close()
        except OSError:
            pass
        if splash.mode_of(state) != "off":
            try:
                play_splash(splash.mode_of(state))
            except Exception as e:
                log("splash failed: %r" % (e,))

    _start_launcher_music()

    forced = calibration_needed()
    forced_fails, forced_t = 0, None
    if forced:
        bmap, view = ButtonMap(), "bmap"

    def forced_next():
        nonlocal forced, forced_fails, forced_t, view
        forced_fails, forced_t = 0, None
        forced, view = False, "home"
        mark_calibrated()

    blanked = False
    prof = FrameProfiler(os.environ.get("RGOS_PROFILE") == "1", log)
    while code is None:
        if os.path.exists(SCREENOFF_FILE):
            inp.poll()
            if not blanked:
                canvas.fill((0, 0, 0))
                present()
                blanked = True
            pygame.time.wait(120)
            continue
        blanked = False
        _pt0 = time.perf_counter()
        _music_tick()
        _asc = art["sc"]
        if _asc is not None:
            _now = time.monotonic()
            _sn = _asc.snapshot()
            if _sn["version"] != art["seen"] and (_now - art["seen_at"] >= 1.5 or _sn["state"] != "running"):
                art["seen"], art["seen_at"] = _sn["version"], _now
                art_index.invalidate()
                art["ver"] += 1
        if ci.take_changed():
            filter_systems()
            sysname.clear()
            sysname.update({sy[0]: sy[4] for sy in SYSTEMS})
            ensure_folders()
            ci_rows[:] = core_installer_rows()
            ci_idx = min(ci_idx, max(0, len(ci_rows) - 1))
            rescan.start()
        _scanned = rescan.take()
        if _scanned is not None:
            cur_sid = vsys[sys_idx][0] if vsys else None
            all_games = _scanned
            vsys = visible_systems(all_games)
            sys_idx = next((i for i, sy in enumerate(vsys) if sy[0] == cur_sid), min(sys_idx, max(0, len(vsys) - 1)))
            if view == "games" and not any(sy[0] == cur_sid for sy in vsys):
                view = "home" if launcher_id == "xmb" else "systems"
            elif view in ("games", "recents", "favorites"):
                _k = "\0" + view if view in ("recents", "favorites") else (vsys[sys_idx][0] if vsys else "")
                _n = len(recent_games() if view == "recents" else (favorite_games() if view == "favorites" else games_of(_k)))
                idx_by[_k] = min(idx_by.get(_k, 0), max(0, _n - 1))
        _acts = inp.poll()
        if pending_acts:
            _acts, pending_acts = pending_acts + list(_acts), []
        if _acts:
            last_act = time.monotonic()
            _BOOST.poke()
        if view == "home":
            xmb_ret[0] = False
        _acts = list(_acts)
        for _ai, a in enumerate(_acts):
            if forced:
                if a == "quit":
                    code = EXIT_POWER
                elif a == "menu" and forced_fails >= 3:
                    bmap.stop()
                    forced_next()
                continue
            if view in ("games", "recents", "favorites"):
                key = "\0" + view if view in ("recents", "favorites") else (vsys[sys_idx][0] if vsys else "")
                games = recent_games() if view == "recents" else (favorite_games() if view == "favorites" else games_of(vsys[sys_idx][0] if vsys else ""))
                n, idx = len(games), idx_by.get(key, 0)
            if a == "quit":
                code = EXIT_POWER
            elif dd is not None:
                opts = dd_options(dd["kind"])
                if a in ("up", "down"):
                    dd["sel"] = (dd["sel"] + (1 if a == "down" else -1)) % len(opts)
                    dd_set(dd["kind"], opts[dd["sel"]][0])
                elif a == "a":
                    dd_set(dd["kind"], opts[dd["sel"]][0])
                    state[dd["kind"]] = opts[dd["sel"]][0]
                    save_state(state)
                    dd = None
                elif a in ("b", "menu"):
                    dd_set(dd["kind"], dd["orig"])
                    dd = None
            elif launcher_id == "steamos" and STEAM_UI["open"] and view in ("home", "systems", "games", "recents", "favorites"):
                if a in ("up", "down"):
                    STEAM_UI["sel"] = (STEAM_UI["sel"] + (1 if a == "down" else -1)) % len(STEAM_MENU)
                elif a in ("b", "menu"):
                    STEAM_UI["open"] = False
                elif a == "a":
                    STEAM_UI["open"] = False
                    target = STEAM_MENU[STEAM_UI["sel"]][0]
                    if target == "power":
                        code = EXIT_POWER
                    elif target == "games":
                        view = "systems"
                        sys_idx = min(sys_idx, max(0, len(vsys) - 1))
                    else:
                        view = target
            elif a == "menu":
                if launcher_id == "steamos" and view in ("home", "systems", "games", "recents", "favorites"):
                    STEAM_UI["open"], STEAM_UI["sel"] = True, steam_menu_index(view)
                elif view == "home" and launcher_id in FLOW_LIKE:
                    flow_t = 0
                    flow_fade = 0.0
                elif view in ("systems", "games", "recents", "favorites") and launcher_id in FLOW_LIKE:
                    view = "home"
                elif view in ("systems", "games", "recents", "favorites", "tools", "settings", "wifi", "bt", "ssh", "info", "bios", "artwork", "files", "coreinstall"):
                    view = "home"
                elif view == "bmap" and bmap and bmap.state in ("done", "fail"):
                    view = "home"
            elif a == "x" and view in ("home", "systems", "games", "recents", "favorites"):
                rescan.start()
            elif launcher_id in FLOW_LIKE and view in ("home", "systems", "games", "recents", "favorites"):
                fc = flow_cards()
                fn_ = len(fc)
                cur_ = fc[flow_t % fn_ if fn_ >= 3 else max(0, min(fn_ - 1, flow_t))] if fn_ else None
                if a in ("left", "right", "l", "r", "up", "down") and fn_:
                    fwd = a in ("right", "r", "down")
                    step = (1 if fwd else -1) * (5 if a in ("l", "r") else 1)
                    flow_t = flow_t + step if fn_ >= 3 else max(0, min(fn_ - 1, flow_t + step))
                elif a == "b":
                    view = "systems" if view == "games" else "home" if view != "home" else view
                elif a == "y" and cur_ and "game" in cur_:
                    path = cur_["game"]["path"]
                    if path in favorite_paths:
                        favorite_paths.discard(path)
                    else:
                        favorite_paths.add(path)
                    if not save_favorites(favorite_paths):
                        favorite_paths = set(load_favorites())
                    fav_changed()
                elif a == "a" and cur_:
                    if view == "home":
                        hid = cur_["id"]
                        if hid == "power":
                            code = EXIT_POWER
                        elif hid == "games":
                            view = "systems"
                            sys_idx = min(sys_idx, max(0, len(vsys) - 1))
                        else:
                            view = hid
                    elif view == "systems":
                        sys_idx, view = next(i for i, sy in enumerate(vsys) if sy[0] == cur_["id"]), "games"
                    else:
                        code = launch(cur_["game"]["path"], cur_["game"])
            elif view == "home" and launcher_id == "xmb":
                cat = XMB_CATS[xmb_cat][0]
                nav = a in ("left", "right", "l", "r", "up", "down")
                items = xmb_items(cat, not nav)
                if not nav:
                    _xic.clear()
                cur = min(xmb_sel.get(cat, 0), len(items) - 1)
                if a in ("left", "right", "l", "r"):
                    new = max(0, min(len(XMB_CATS) - 1, xmb_cat + (1 if a in ("right", "r") else -1)))
                    if new != xmb_cat:
                        xmb_cat, xmb_fade = new, 0.0
                        xmb_vy, xmb_vv = float(xmb_sel.get(XMB_CATS[new][0], 0)), 0.0
                elif a in ("up", "down"):
                    xmb_sel[cat] = max(0, min(len(items) - 1, cur + (1 if a == "down" else -1)))
                elif a == "y" and items and items[cur]["act"] and items[cur]["act"][0] == "setting" and SETTINGS_ROWS[items[cur]["act"][1]] == "splash":
                    play_splash("silent" if splash.mode_of(state) == "silent" else "on")
                elif a == "a" and items and items[cur]["act"]:
                    act = items[cur]["act"]
                    if act[0] == "system":
                        sys_idx, view = act[1], "games"
                    elif act[0] == "launch":
                        code = launch(act[1]["path"], act[1])
                    elif act[0] == "tool":
                        if act[1] == "@view:files":
                            fm, fm_pop, view = make_file_manager(), None, "files"
                            xmb_ret[0] = True
                        elif act[1] == "@view:coreinstall":
                            ci_rows[:], ci_idx, view = core_installer_rows(), 0, "coreinstall"
                            xmb_ret[0] = True
                        else:
                            code = launch(act[1])
                    elif act[0] == "setting":
                        row = SETTINGS_ROWS[act[1]]
                        if row == "theme":
                            dd = {"kind": "theme", "sel": theme_index(theme_id), "orig": theme_id}
                        elif row == "launcher":
                            dd = {"kind": "launcher", "sel": launcher_index(launcher_id), "orig": launcher_id}
                        elif row == "splash":
                            state["splash"] = splash.MODES[(splash.MODES.index(splash.mode_of(state)) + 1) % len(splash.MODES)]
                            save_state(state)
                        elif row == "swapab":
                            set_swap_ab(not swap_ab_on())
                            restart_hub()
                        elif row == "dpadjoy":
                            set_dpad_joy(not dpad_joy_on())
                        else:
                            set_idx, view = act[1], "settings"
                            xmb_ret[0] = True
                            _acts.insert(_ai + 1, "a")
                    elif act[0] == "power":
                        code = EXIT_POWER
            elif view == "home":
                hc = 3 if launcher_id == "rgclassic" else HOME_COLS
                col, row = home_idx % hc, home_idx // hc
                nrows = (len(HOME_ITEMS) + hc - 1) // hc
                if a == "left":
                    home_idx = row * hc + (col - 1) % hc
                elif a == "right":
                    home_idx = row * hc + (col + 1) % hc
                elif a in ("up", "down"):
                    candidate = ((row + (1 if a == "down" else -1)) % nrows) * hc + col
                    home_idx = candidate if candidate < len(HOME_ITEMS) else home_idx
                elif a == "a":
                    view = HOME_ITEMS[home_idx][0]
                    if view == "power":
                        code = EXIT_POWER
                    elif view == "games":
                        view = "systems"
                        sys_idx = min(sys_idx, max(0, len(vsys) - 1))
            elif view == "systems":
                if vsys and a in ("down", "right"):
                    sys_idx = (sys_idx + 1) % len(vsys)
                elif vsys and a in ("up", "left"):
                    sys_idx = (sys_idx - 1) % len(vsys)
                elif a == "a" and vsys:
                    view = "games"
                elif a == "b":
                    view = "home"
            elif view in ("games", "recents", "favorites"):
                if a == "b":
                    view = "systems" if view == "games" and launcher_id != "xmb" else "home"
                elif n and a == "down":
                    idx_by[key] = (idx + 1) % n
                elif n and a == "up":
                    idx_by[key] = (idx - 1) % n
                elif n and a in ("r", "right"):
                    idx_by[key] = min(n - 1, idx + rows)
                elif n and a in ("l", "left"):
                    idx_by[key] = max(0, idx - rows)
                elif a == "y" and n and view == "games":
                    path = games[idx]["path"]
                    if path in favorite_paths:
                        favorite_paths.discard(path)
                        action = "Removed from favorites"
                    else:
                        favorite_paths.add(path)
                        action = "Added to favorites"
                    if save_favorites(favorite_paths):
                        log("%s: %s" % (action, path))
                    else:
                        favorite_paths = set(load_favorites())
                    fav_changed()
                elif a == "a" and n:
                    code = launch(games[idx]["path"], games[idx])
            elif view == "tools":
                if a in ("up", "down"):
                    tool_idx = (tool_idx + (1 if a == "down" else -1)) % len(TOOLS)
                elif a == "b":
                    view = "home"
                elif a == "a":
                    tgt = TOOLS[tool_idx][3]
                    if tgt == "@view:files":
                        fm, fm_pop, view = make_file_manager(), None, "files"
                    elif tgt == "@view:coreinstall":
                        ci_rows[:], ci_idx, view = core_installer_rows(), 0, "coreinstall"
                    else:
                        code = launch(tgt)
            elif view == "coreinstall":
                ci_vis = 7 + DY // 44
                ci_s = ci.snapshot()
                if a == "b":
                    if ci_s["busy"]:
                        ci.cancel()
                    else:
                        view = back_to("tools")
                elif a in ("up", "down") and ci_rows:
                    ci_idx = (ci_idx + (1 if a == "down" else -1)) % len(ci_rows)
                elif a in ("left", "l") and ci_rows:
                    ci_idx = max(0, ci_idx - ci_vis + 1)
                elif a in ("right", "r") and ci_rows:
                    ci_idx = min(len(ci_rows) - 1, ci_idx + ci_vis - 1)
                elif a == "a" and ci_rows and not ci_s["busy"]:
                    if not ci_rows[ci_idx]["installed"]:
                        ci.start([ci_rows[ci_idx]["core"]])
            elif view == "files":
                if fm.busy:
                    pass
                elif fm_pop:
                    kind = fm_pop["kind"]
                    if kind == "info":
                        if a in ("a", "b"):
                            fm_pop = None
                    elif kind == "confirm":
                        if a in ("left", "right", "up", "down"):
                            fm_pop["sel"] = 1 - fm_pop["sel"]
                        elif a == "b":
                            fm_pop = None
                        elif a == "a":
                            if fm_pop["sel"] == 0:
                                fm.delete()
                            fm_pop = None
                    else:
                        if a in ("up", "down"):
                            fm_pop["sel"] = (fm_pop["sel"] + (1 if a == "down" else -1)) % len(fm_pop["items"])
                        elif a == "b":
                            fm_pop = None
                        elif a == "a":
                            act = fm_pop["items"][fm_pop["sel"]][0]
                            fm_pop = None
                            if act == "copy":
                                fm.copy()
                            elif act == "cut":
                                fm.cut()
                            elif act == "paste":
                                fm.paste()
                            elif act == "rename":
                                kb, view = Kbd("fm_rename", "Rename", fm.current()["name"], False), "kbd"
                            elif act == "mkdir":
                                kb, view = Kbd("fm_mkdir", "New folder name", "", False), "kbd"
                            elif act == "delete":
                                fm_pop = {"kind": "confirm", "sel": 1, "n": len(fm.targets())}
                            elif act == "info":
                                fm_pop = {"kind": "info", "lines": fm.info()}
                else:
                    fm.msg = ""
                    if a in ("up", "down"):
                        fm.wrap_cursor(1 if a == "down" else -1)
                    elif a in ("l", "left"):
                        fm.move_cursor(-FM_ROWS)
                    elif a in ("r", "right"):
                        fm.move_cursor(FM_ROWS)
                    elif a == "a":
                        if not fm.open_current() and fm.current():
                            fm_pop = {"kind": "info", "lines": fm.info()}
                    elif a == "b":
                        if not fm.go_up():
                            view = back_to("tools")
                    elif a == "y":
                        fm.toggle_mark()
                    elif a == "x":
                        items = []
                        if fm.cwd is not None:
                            if fm.targets():
                                items += [("copy", "Copy"), ("cut", "Cut")]
                            if fm.can_paste():
                                items.append(("paste", "Paste here (%d)" % len(fm.clip)))
                            if fm.current() and not fm.marked:
                                items.append(("rename", "Rename"))
                            items.append(("mkdir", "New folder"))
                            if fm.targets():
                                items.append(("delete", "Delete" + (" (%d)" % len(fm.marked) if fm.marked else "")))
                        if fm.current():
                            items.append(("info", "Details"))
                        if items:
                            fm_pop = {"kind": "menu", "items": items, "sel": 0}
            elif view == "settings":
                if a in ("up", "down"):
                    set_idx = (set_idx + (1 if a == "down" else -1)) % len(SETTINGS_ROWS)
                elif a in ("left", "right") and SETTINGS_ROWS[set_idx] == "theme":
                    theme_id = apply_theme(THEMES[(theme_index(theme_id) + (1 if a == "right" else -1)) % len(THEMES)][0])
                    state["theme"] = theme_id
                    save_state(state)
                elif a in ("left", "right") and SETTINGS_ROWS[set_idx] == "launcher":
                    launcher_id = LAUNCHERS[(launcher_index(launcher_id) + (1 if a == "right" else -1)) % len(LAUNCHERS)][0]
                    state["launcher"] = launcher_id
                    save_state(state)
                elif a in ("left", "right") and SETTINGS_ROWS[set_idx] == "splash":
                    state["splash"] = splash.MODES[(splash.MODES.index(splash.mode_of(state)) + (1 if a == "right" else -1)) % len(splash.MODES)]
                    save_state(state)
                elif a == "x" and SETTINGS_ROWS[set_idx] == "splash":
                    play_splash("silent" if splash.mode_of(state) == "silent" else "on")
                elif a == "b":
                    view = "home"
                elif a == "a":
                    row = SETTINGS_ROWS[set_idx]
                    if row == "theme":
                        dd = {"kind": "theme", "sel": theme_index(theme_id), "orig": theme_id}
                    elif row == "launcher":
                        dd = {"kind": "launcher", "sel": launcher_index(launcher_id), "orig": launcher_id}
                    elif row == "splash":
                        state["splash"] = splash.MODES[(splash.MODES.index(splash.mode_of(state)) + 1) % len(splash.MODES)]
                        save_state(state)
                    elif row == "emulators":
                        emu_idx, view = 0, "emulators"
                    elif row == "bios":
                        bios_cache, bios_scroll, bios_pos, view = bios_scan(state), 0, 0.0, "bios"
                    elif row == "artwork":
                        art_idx, view = 0, "artwork"
                    elif row == "wifi":
                        wconf, wf_idx, wf_msg, wf_msg_until = wifictl.load_conf(), 0, "", 0.0
                        wscan.kick()
                        view = "wifi"
                    elif row == "bluetooth":
                        bt_idx, view = 0, "bt"
                        btm.refresh()
                    elif row == "ssh":
                        view = "ssh"
                    elif row == "info":
                        info_scroll, info_pos, view = 0, 0.0, "info"
                    elif row == "swapab":
                        set_swap_ab(not swap_ab_on())
                        restart_hub()
                    elif row == "dpadjoy":
                        set_dpad_joy(not dpad_joy_on())
                    else:
                        bmap, view = ButtonMap(), "bmap"
            elif view == "artwork":
                _sc = art["sc"]
                art_running = _sc is not None and _sc.running
                if a in ("up", "down"):
                    art_idx = (art_idx + (1 if a == "down" else -1)) % 4
                elif a == "b":
                    view = back_to("settings")
                elif a == "x" and art_running:
                    _sc.stop()
                elif a == "a":
                    if art_idx == 0:
                        if art_running:
                            art_note("Stop the download first (X)")
                        else:
                            kb, view = Kbd("sgdb_key", "SteamGridDB API key", "", False), "kbd"
                    elif art_idx in (1, 2):
                        art_start(art_idx == 2)
                    else:
                        state["artwork"] = not art_on()
                        save_state(state)
            elif view == "emulators":
                emu_systems = [sy for sy in SYSTEMS if sy[2] == "retroarch" and compatible_cores(sy[0])]
                if a in ("up", "down"):
                    emu_idx = (emu_idx + (1 if a == "down" else -1)) % max(1, len(emu_systems))
                elif a in ("left", "right") and emu_systems:
                    sid = emu_systems[emu_idx][0]
                    cores = compatible_cores(sid)
                    if cores:
                        current = state.get("emulators", {}).get(sid, default_core(sid))
                        if current not in cores:
                            current = default_core(sid) if default_core(sid) in cores else cores[0]
                        pos = cores.index(current)
                        state.setdefault("emulators", {})[sid] = cores[(pos + (1 if a == "right" else -1)) % len(cores)]
                        save_state(state)
                elif a == "b":
                    view = back_to("settings")
            elif view == "bios":
                bios_n = len(biosctl.build_lines(bios_cache[0], bios_all, "")) if bios_cache else 0
                bios_vis = max(1, (336 + DY - 56) // 34)
                if a == "b":
                    view = back_to("settings")
                elif a == "up":
                    bios_scroll = max(0, bios_scroll - 1)
                elif a == "down":
                    bios_scroll = min(max(0, bios_n - bios_vis), bios_scroll + 1)
                elif a in ("left", "l"):
                    bios_scroll = max(0, bios_scroll - bios_vis + 1)
                elif a in ("right", "r"):
                    bios_scroll = min(max(0, bios_n - bios_vis), bios_scroll + bios_vis - 1)
                elif a == "x":
                    bios_all, bios_scroll, bios_pos = not bios_all, 0, 0.0
                elif a == "a":
                    bios_cache = bios_scan(state)
            elif view == "info":
                if a == "b":
                    view = back_to("settings")
                elif a == "up":
                    info_scroll = max(0, info_scroll - 1)
                elif a == "down":
                    info_scroll += 1
                elif a in ("left", "l"):
                    info_scroll = max(0, info_scroll - 5)
                elif a in ("right", "r"):
                    info_scroll += 5
            elif view == "kbd":
                if a in ("up", "down", "left", "right"):
                    kb.move({"up": -1, "down": 1}.get(a, 0), {"left": -1, "right": 1}.get(a, 0))
                elif a == "b":
                    kb.text = kb.text[:-1]
                elif a == "x" and kb.secret:
                    kb.show = not kb.show
                elif a in ("a", "start"):
                    res = kb.press() if a == "a" else "ok"
                    if res and kb.field.startswith("fm_"):
                        if res == "cancel" or (kb.field == "fm_rename" and fm.rename(kb.text)) or (kb.field == "fm_mkdir" and fm.mkdir(kb.text)):
                            view = "files"
                        else:
                            view, kb = "files", None
                    elif res and kb.field.startswith("wifi"):
                        view = "wifi"
                        if res == "ok" and kb.field == "wifi_ssid":
                            if kb.text.strip():
                                wf_pending = (kb.text, True)
                                kb, view = Kbd("wifi_psk", "Password for %s (empty = open network)" % kb.text, "", True), "kbd"
                        elif res == "ok":
                            ssid_, hidden_ = wf_pending
                            if kb.text == "" and hidden_:
                                wf_do(wifictl.join, "Joining %s..." % ssid_, ssid_, None, True)
                            elif not wifictl.password_ok(kb.text):
                                wf_msg, wf_msg_until = "The password must be 8-63 characters", time.time() + 4
                            else:
                                wf_do(wifictl.join, "Joining %s..." % ssid_, ssid_, kb.text, hidden_)
                    elif res and kb.field == "sgdb_key":
                        view = "artwork"
                        if res == "ok":
                            _k = kb.text.strip()
                            if not artwork.valid_key(_k):
                                art_note("That is not an API key (16 to 64 letters and numbers)")
                            elif artwork.save_key(ROMS_ROOT, _k):
                                art["key"] = _k
                                art_note("API key saved")
                            else:
                                art_note("Could not save the key")
                    elif res:
                        view = "settings"
            elif view == "wifi":
                wrows = wscan.rows(wconf)
                wn = len(wrows) + 2
                if a == "down":
                    wf_idx = (wf_idx + 1) % wn
                elif a == "up":
                    wf_idx = (wf_idx - 1) % wn
                elif a == "b":
                    view = back_to("settings")
                elif a == "x":
                    wscan.kick()
                elif wf_idx == 0 and a == "a":
                    wifictl.set_enabled(not wconf["enabled"])
                    wconf = wifictl.load_conf()
                    if wconf["enabled"]:
                        wscan.kick()
                elif wf_idx == wn - 1 and a == "a":
                    kb, view = Kbd("wifi_ssid", "Hidden network name (SSID)", "", False), "kbd"
                elif 0 < wf_idx < wn - 1:
                    net = wrows[wf_idx - 1]
                    if a == "y" and net["saved"]:
                        wf_do(wifictl.forget_and_apply, "Forgot %s" % net["ssid"], net["ssid"])
                    elif a == "a":
                        if net["unsupported"]:
                            wf_msg, wf_msg_until = "WPA3-only and WEP networks are not supported", time.time() + 4
                        elif net["saved"]:
                            wf_do(wifictl.connect, "Connecting to %s..." % net["ssid"], net["ssid"])
                        elif net["secured"]:
                            wf_pending = (net["ssid"], False)
                            kb, view = Kbd("wifi_psk", "Password for %s" % net["ssid"], "", True), "kbd"
                        else:
                            wf_do(wifictl.join, "Joining %s..." % net["ssid"], net["ssid"], None, False)
            elif view == "bt":
                brows = list(btm.rows)
                bn = len(brows) + 1
                bt_idx = min(bt_idx, bn - 1)
                if a == "down":
                    bt_idx = (bt_idx + 1) % bn
                elif a == "up":
                    bt_idx = (bt_idx - 1) % bn
                elif a == "b":
                    view = back_to("settings")
                elif a == "x":
                    btm.scan_now()
                elif bt_idx == 0 and a == "a":
                    btm.toggle()
                elif bt_idx > 0 and a in ("a", "y"):
                    d = brows[bt_idx - 1]
                    if a == "y":
                        if d["paired"]:
                            btm.act(btctl.forget, d["mac"], "Forgetting " + d["name"])
                    elif d["connected"]:
                        btm.act(btctl.disconnect, d["mac"], "Disconnecting " + d["name"])
                    elif d["paired"]:
                        btm.act(btctl.connect, d["mac"], "Connecting to " + d["name"])
                    else:
                        btm.act(btctl.pair, d["mac"], "Pairing with " + d["name"])
            elif view == "ssh":
                if a == "b":
                    view = back_to("settings")
                elif a == "a":
                    ssh_toggle()
            elif view == "bmap":
                if bmap.state == "fail" and a == "a" and bmap.can_resume():
                    bmap.resume()
                elif bmap.state in ("done", "fail") and a in ("a", "b"):
                    view = back_to("settings")
        if view == "bmap" and bmap:
            bmap.update()
        if forced:
            wiz, now_f = bmap, time.time()
            if wiz.state == "done":
                forced_t = forced_t or now_f
                if now_f - forced_t >= 1.5:
                    forced_next()
            elif wiz.state == "fail":
                if forced_t is None:
                    forced_t, forced_fails = now_f, forced_fails + 1
                elif now_f - forced_t >= 3.0:
                    forced_t = None
                    if bmap.can_resume():
                        bmap.resume()
                    else:
                        bmap = ButtonMap()
        if {"start", "select"} <= inp.held:
            code = EXIT_POWER

        sid, stag, score, _ext, sname = vsys[sys_idx] if vsys else NO_SYSTEM
        if view == "recents":
            games, key = recent_games(), "\0recents"
        elif view == "favorites":
            games, key = favorite_games(), "\0favorites"
        else:
            games, key = games_of(sid), sid
        idx = min(idx_by.get(key, 0), max(0, len(games) - 1))
        _now = int(time.time())
        if _now != clk_at:
            clk_at, clk = _now, time.strftime("%H:%M")

        _pt1 = time.perf_counter()
        anim_moving = anim_tick()
        if anim_moving:
            _BOOST.poke()
        _BOOST.tick()
        XMB_UI[0] = launcher_id == "xmb"
        CLASSIC_UI[0], CLASSIC_UI[1] = launcher_id == "rgclassic", classic_unit()
        f_logo, f_big, f_row, f_small, f_tiny = PX_FONTS if CLASSIC_UI[0] else TT_FONTS
        flow_on = launcher_id in FLOW_LIKE and view in ("home", "systems", "games", "recents", "favorites")
        classic_on = launcher_id == "rgclassic" and view == "home"
        if flow_on or classic_on:
            pass
        elif launcher_id == "rgclassic":
            classic_ui.apply(BG, PANEL, SEL_BG, ACCENT, TEXT, DIM)
            if _CLASSIC_BG[0] != classic_ui._theme:
                _CLASSIC_BG[0], _CLASSIC_BG[1] = classic_ui._theme, pygame.transform.scale(classic_ui.bg, (W, H))
            canvas.blit(_CLASSIC_BG[1], (0, 0))
            draw_classic_header(canvas, f_logo)
        elif launcher_id == "xmb":
            xmb_bg(canvas, time.time(), anim_moving or time.monotonic() - last_act < XMB_BG_SETTLE)
        else:
            canvas.fill(BG)
            pygame.draw.rect(canvas, PANEL, (0, 0, W, 64))
            pygame.draw.rect(canvas, ACCENT, (0, 62, W, 2))
            rg = f_logo.render("RG", True, ACCENT)
            canvas.blit(rg, (20, 14))
            canvas.blit(f_logo.render("OS", True, TEXT), (20 + rg.get_width() + 4, 14))
        if view == "games":
            info = "%s   %d %s%s   %s" % (sname, len(games), "port" if sid == "ports" else "game", "" if len(games) == 1 else "s", clk)
        elif view == "systems":
            info = "Games   %s" % clk
        elif view == "recents":
            info = "Recents   %d game%s   %s" % (len(games), "" if len(games) == 1 else "s", clk)
        elif view == "favorites":
            info = "Favorites   %d game%s   %s" % (len(games), "" if len(games) == 1 else "s", clk)
        elif view == "tools":
            info = "Tools   %s" % clk
        elif view == "files" or (view == "kbd" and kb.field.startswith("fm_")):
            info = "Tools > Files   %s" % clk
        elif view == "coreinstall":
            info = "Tools > Core Installer   %s" % clk
        elif view in ("settings", "bmap"):
            info = "Settings   %s" % clk
        elif view == "info":
            info = "Settings > Information   %s" % clk
        elif view == "emulators":
            info = "Settings > Emulators   %s" % clk
        elif view == "bios":
            info = "Settings > Missing BIOS check   %s" % clk
        elif view == "artwork" or (view == "kbd" and kb.field.startswith("sgdb")):
            info = "Settings > Game artwork   %s" % clk
        elif view == "wifi" or (view == "kbd" and kb.field.startswith("wifi")):
            info = "Settings > Wi-Fi   %s" % clk
        elif view == "bt":
            info = "Settings > Bluetooth   %s" % clk
        elif view == "ssh":
            info = "Settings > SSH / file transfer   %s" % clk
        else:
            info = clk
        if forced:
            info = "First-time setup   %s" % clk
        if rescan.busy:
            info = "Scanning...   " + info
        if flow_on or classic_on:
            info = ""
        s = f_small.render(info, True, DIM)
        bat = None if flow_on or classic_on else rd_bat()
        right = W - 20
        if launcher_id == "xmb":
            pl = (W - 90 - 16 if bat else W - 20) - s.get_width() - 20
            pygame.draw.rect(canvas, xmb_tint(W - 40, 33, 0.10), (pl, 14, W - 8 - pl, 38), border_radius=19)
            pygame.draw.rect(canvas, xmb_tint(W - 40, 33, 0.24), (pl, 14, W - 8 - pl, 38), 1, border_radius=19)
        if bat:
            pct, status = bat
            low = pct <= 15 and status.lower() != "charging"
            col = (230, 70, 60) if low else ACCENT if status.lower() == "charging" else TEXT
            if CLASSIC_UI[0]:
                u_ = CLASSIC_UI[1]
                bx, by = W - 20 - 16 * u_, 30 - 7 * u_ // 2
                for r_ in ((0, 0, 15, 1), (0, 6, 15, 1), (0, 0, 1, 7), (14, 0, 1, 7), (15, 2, 1, 3),
                           (2, 2, max(1, min(11, 11 * pct // 100)), 3)):
                    pygame.draw.rect(canvas, col, (bx + r_[0] * u_, by + r_[1] * u_, r_[2] * u_, r_[3] * u_))
                pt = f_tiny.render("%d%%" % pct, True, col)
                canvas.blit(pt, (bx - 8 - pt.get_width(), 30 - pt.get_height() // 2))
                right = bx - 8 - pt.get_width() - 16
            else:
                bx, by = W - 90, 22
                pygame.draw.rect(canvas, col, (bx, by, 30, 16), 2, border_radius=3)
                pygame.draw.rect(canvas, col, (bx + 30, by + 4, 3, 8))
                fw = max(2, 24 * pct // 100)
                pygame.draw.rect(canvas, col, (bx + 3, by + 3, fw, 10))
                pt = f_tiny.render("%d%%" % pct + ("+" if status.lower() == "charging" else ""), True, col)
                canvas.blit(pt, (bx + 38, by + 2))
                right = bx - 16
        canvas.blit(s, (right - s.get_width(), 24))

        if flow_on:
            fk_ = flow_cur_key()
            if fk_ != flow_key:
                if flow_key is not None:
                    flow_pos[flow_key] = flow_t
                flow_key = fk_
                flow_t = flow_pos.get(fk_, 0)
                flow_fx, flow_fv, flow_fade = float(flow_t), 0.0, 0.0
            fcards = flow_cards()
            fn_ = len(fcards)
            if fn_ >= 3:
                kk = (flow_t // fn_) * fn_
                flow_t, flow_fx = flow_t - kk, flow_fx - kk
            elif fn_:
                flow_t = max(0, min(fn_ - 1, flow_t))
            fdt = _anim_clock[1]
            if launcher_id == "steamos":
                s_tgt = 1.0 if STEAM_UI["open"] else 0.0
                STEAM_UI["slide"] += (s_tgt - STEAM_UI["slide"]) * min(1.0, fdt * 14.0)
                if abs(s_tgt - STEAM_UI["slide"]) < 0.01:
                    STEAM_UI["slide"] = s_tgt
                else:
                    _anim_clock[2] = True
                STEAM_UI["wifi"] = rd_net()
            flow_fx, flow_fv = _smooth_damp(flow_fx, flow_fv, flow_t, fdt)
            flow_fade = min(1.0, flow_fade + fdt * 6.0)
            # the SteamOS backdrop only changes once the cursor settles (no input for a moment, or arrived)
            STEAM_UI["rest"] = flow_fx == flow_t or (time.monotonic() - last_act > 0.12 and abs(flow_fx - flow_t) < 0.6)
            if flow_fx != flow_t or flow_fade < 1.0:
                _anim_clock[2] = True
            if view == "home":
                crumb, hints, empty = "", [("<>", "Browse"), ("A", "Open"), ("MENU", "First")], ("", "")
            elif view == "systems":
                crumb, hints = "Games", [("<>", "Browse"), ("A", "Open"), ("B", "Back")]
                empty = ("No games found", "Copy ROMs to the SD card, then press X to rescan")
            else:
                crumb = {"recents": "Recents", "favorites": "Favorites"}.get(view) or (sysname.get(vsys[sys_idx][0], "") if vsys else "")
                hints = [("<>", "Browse"), ("A", "Play"), ("Y", "Favorite"), ("B", "Back")]
                empty = ("Nothing here yet", "Play or star some games first") if view != "games" else ("No games found", "Press X to rescan")
            (draw_steam_level if launcher_id == "steamos" else draw_flow_level)(canvas, f_small, f_row, fcards, flow_fx, flow_fade, crumb, hints, empty, clk, rd_bat(), rescan.busy)
            hint = ""
        elif view == "home" and launcher_id == "xmb":
            xcat = XMB_CATS[xmb_cat][0]
            xitems = xmb_items(xcat)
            xmb_sel[xcat] = max(0, min(xmb_sel.get(xcat, 0), len(xitems) - 1))
            xdt = _anim_clock[1]
            xmb_cx, xmb_cv = _smooth_damp(xmb_cx, xmb_cv, xmb_cat, xdt)
            xmb_vy, xmb_vv = _smooth_damp(xmb_vy, xmb_vv, xmb_sel[xcat], xdt)
            xmb_fade = min(1.0, xmb_fade + xdt * 6.0)
            if xmb_cx != xmb_cat or xmb_vy != xmb_sel[xcat] or xmb_fade < 1.0:
                _anim_clock[2] = True
            draw_xmb_home(canvas, f_row, f_small, xmb_cx, xmb_cat, xitems, xmb_vy, xmb_fade)
            hint = "Left/Right Category   Up/Down Item   A Open   X Rescan"
            if dd is not None:
                draw_xmb_dropdown(canvas, f_small, dd, dd_options(dd["kind"]))
                hint = "Up/Down Browse   A Select   B Cancel"
        elif classic_on:
            cdescs = {"games": "%d games" % len(all_games),
                      "recents": "%d recent" % len(recent_games()),
                      "favorites": "%d favorites" % len(favorite_games()),
                      "tools": "Files, ports, RetroArch",
                      "settings": "Theme, Wi-Fi, info, controls",
                      "power": "Shut down RG OS"}
            classic_ui.apply(BG, PANEL, SEL_BG, ACCENT, TEXT, DIM)
            classic_ui.draw(canvas, HOME_ITEMS, cdescs, home_idx, clk, rd_bat(),
                            [("A", "Open"), ("X", "Rescan")], 3)
            hint = ""
            if dd is not None:
                draw_xmb_dropdown(canvas, f_small, dd, dd_options(dd["kind"]))
                hint = "Up/Down Browse   A Select   B Cancel"
        elif view == "home":
            gap = 14
            nrows_h = (len(HOME_ITEMS) + HOME_COLS - 1) // HOME_COLS
            bw, bh = (W - 40 - (HOME_COLS - 1) * gap) // HOME_COLS, (H - top_y - 48 - (nrows_h - 1) * gap) // nrows_h
            x0 = (W - (HOME_COLS * bw + (HOME_COLS - 1) * gap)) // 2
            vo = (bh - 148) // 2
            subs = {"games": "%d games" % len(all_games),
                    "recents": "%d recent" % len(recent_games()),
                    "favorites": "%d favorites" % len(favorite_games()),
                    "tools": "Files, ports, RetroArch",
                    "settings": "Theme, Wi-Fi, info, controls",
                    "power": "Shut down RG OS"}
            for i, (hid, hname) in enumerate(HOME_ITEMS):
                bx, by, sel = x0 + (i % HOME_COLS) * (bw + gap), top_y + (i // HOME_COLS) * (bh + gap), i == home_idx
                hl, lift = draw_button(canvas, (bx, by, bw, bh), SEL_BG if sel else PANEL, 18, 6, sel)
                by -= lift
                if bh < 130:
                    icx, tx = bx + 62, bx + 128
                    ICONS[hid](canvas, icx, by + bh // 2, _mix(DIM, ACCENT, hl), _mix(PANEL, SEL_BG, hl))
                    title = f_row.render(fit(f_row, hname, bw - (tx - bx) - 14), True, _mix(DIM, TEXT, hl))
                    sub_lines = wrap(f_small, subs[hid], bw - (tx - bx) - 14)[:2]
                    th_, lh_ = title.get_height(), f_small.get_linesize() + 1
                    ty0 = by + (bh - (th_ + 4 + lh_ * len(sub_lines))) // 2
                    canvas.blit(title, (tx, ty0))
                    for li, ln in enumerate(sub_lines):
                        canvas.blit(f_small.render(ln, True, DIM), (tx, ty0 + th_ + 4 + li * lh_))
                    continue
                cx = bx + bw // 2
                ICONS[hid](canvas, cx, by + 44 + vo, _mix(DIM, ACCENT, hl), _mix(PANEL, SEL_BG, hl))
                title = f_row.render(hname, True, _mix(DIM, TEXT, hl))
                canvas.blit(title, (cx - title.get_width() // 2, by + 84 + vo))
                sub = f_small.render(fit(f_small, subs[hid], bw - 24), True, DIM)
                canvas.blit(sub, (cx - sub.get_width() // 2, by + 114 + vo))
            hint = "A Open   X Rescan   START+SELECT Power off"
            if dd is not None:
                draw_xmb_dropdown(canvas, f_small, dd, dd_options(dd["kind"]))
                hint = "Up/Down Browse   A Select   B Cancel"
        elif view == "tools":
            for i, (_tid, tname, tdesc, _tgt) in enumerate(TOOLS):
                by, sel = top_y + i * 90, i == tool_idx
                draw_button(canvas, (list_x, by, W - 2 * list_x, 82), SEL_BG if sel else PANEL, 12, 3, sel)
                canvas.blit(f_row.render(tname, True, TEXT if sel else DIM), (list_x + 24, by + 16))
                canvas.blit(f_small.render(fit(f_small, tdesc, W - 2 * list_x - 48), True, DIM), (list_x + 24, by + 46))
            hint = "A Open   B Back   START+SELECT Power off"
        elif view == "files":
            canvas.blit(f_small.render(tail_fit(f_small, fm.title(), W - 2 * list_x), True, ACCENT), (list_x, 68))
            n_fm = len(fm.entries)
            first_fm = min(max(0, fm.idx - FM_ROWS // 2), max(0, n_fm - FM_ROWS))
            if not n_fm:
                canvas.blit(f_row.render("Empty folder   (X for options)", True, DIM), (list_x + 10, 110))
            fw_ = W - 2 * list_x - 14
            for slot, e in enumerate(fm.entries[first_fm:first_fm + FM_ROWS]):
                i = first_fm + slot
                by, sel = 92 + slot * 44, i == fm.idx
                draw_button(canvas, (list_x, by, fw_, 40), SEL_BG if sel else PANEL, 10, 3, sel)
                ck = (list_x + 12, by + 12, 16, 16)
                pygame.draw.rect(canvas, ACCENT if sel else DIM, ck, 2, border_radius=3)
                if e["path"] in fm.marked:
                    pygame.draw.rect(canvas, ACCENT, (ck[0] + 4, ck[1] + 4, 8, 8), border_radius=2)
                ic = ACCENT if e["dir"] else DIM
                if e["dir"]:
                    pygame.draw.rect(canvas, ic, (list_x + 40, by + 11, 10, 5), border_radius=2)
                    pygame.draw.rect(canvas, ic, (list_x + 40, by + 15, 22, 14), border_radius=3)
                else:
                    pygame.draw.rect(canvas, ic, (list_x + 44, by + 11, 15, 18), 2, border_radius=2)
                size_s = "" if e["dir"] else filemanager.human_size(e["size"])
                sz = f_small.render(size_s, True, DIM)
                canvas.blit(sz, (list_x + fw_ - 16 - sz.get_width(), by + 12))
                canvas.blit(f_row.render(fit(f_row, e["name"], fw_ - 80 - 16 - sz.get_width() - 16), True, TEXT if sel else DIM),
                            (list_x + 72, by + 7))
            if n_fm > FM_ROWS:
                bar_h = FM_ROWS * 44 - 4
                th = max(24, int(bar_h * FM_ROWS / n_fm))
                ty = 92 + int((bar_h - th) * first_fm / max(1, n_fm - FM_ROWS))
                ui_rect(canvas, PANEL, (W - list_x - 6, 92, 6, bar_h), 3)
                pygame.draw.rect(canvas, ACCENT, (W - list_x - 6, ty, 6, th), border_radius=3)
            status = fm.busy or fm.msg or ("%d marked" % len(fm.marked) if fm.marked else
                                           ("Clipboard: %d item%s to %s" % (len(fm.clip), "" if len(fm.clip) == 1 else "s", "move" if fm.clip_cut else "copy")) if fm.clip else "")
            canvas.blit(f_small.render(fit(f_small, status, W - 2 * list_x), True, ACCENT), (list_x, 420 + DY))
            if fm.busy:
                bx, by, bw, bh = W // 2 - 150, H // 2 - 30, 300, 60
                pygame.draw.rect(canvas, PANEL, (bx, by, bw, bh), border_radius=12)
                pygame.draw.rect(canvas, ACCENT, (bx, by, bw, bh), 2, border_radius=12)
                t = f_row.render(fm.busy, True, TEXT)
                canvas.blit(t, (bx + (bw - t.get_width()) // 2, by + 18))
            elif fm_pop:
                if fm_pop["kind"] == "menu":
                    its = fm_pop["items"]
                    bw, bh = 280, 24 + 40 * len(its)
                    bx, by = (W - bw) // 2, max(70, (H - bh) // 2)
                    pygame.draw.rect(canvas, PANEL, (bx, by, bw, bh), border_radius=12)
                    pygame.draw.rect(canvas, ACCENT, (bx, by, bw, bh), 2, border_radius=12)
                    for k, (_id, label) in enumerate(its):
                        ry, rs = by + 12 + k * 40, k == fm_pop["sel"]
                        if rs:
                            pygame.draw.rect(canvas, SEL_BG, (bx + 8, ry, bw - 16, 36), border_radius=8)
                        canvas.blit(f_row.render(label, True, TEXT if rs else DIM), (bx + 24, ry + 6))
                elif fm_pop["kind"] == "confirm":
                    bw, bh = 340, 130
                    bx, by = (W - bw) // 2, (H - bh) // 2
                    pygame.draw.rect(canvas, PANEL, (bx, by, bw, bh), border_radius=12)
                    pygame.draw.rect(canvas, ACCENT, (bx, by, bw, bh), 2, border_radius=12)
                    q = "Delete %d item%s?" % (fm_pop["n"], "" if fm_pop["n"] == 1 else "s")
                    t = f_row.render(q, True, TEXT)
                    canvas.blit(t, (bx + (bw - t.get_width()) // 2, by + 18))
                    for k, label in enumerate(("Yes", "No")):
                        rx, rs = bx + 30 + k * 150, k == fm_pop["sel"]
                        draw_button(canvas, (rx, by + 70, 130, 38), SEL_BG if rs else BG, 10, 3, rs)
                        t = f_row.render(label, True, TEXT if rs else DIM)
                        canvas.blit(t, (rx + (130 - t.get_width()) // 2, by + 77))
                else:
                    lines = fm_pop["lines"]
                    bw, bh = 400, 28 + 26 * len(lines)
                    bx, by = (W - bw) // 2, (H - bh) // 2
                    pygame.draw.rect(canvas, PANEL, (bx, by, bw, bh), border_radius=12)
                    pygame.draw.rect(canvas, ACCENT, (bx, by, bw, bh), 2, border_radius=12)
                    for k, ln in enumerate(lines):
                        canvas.blit((f_row if k == 0 else f_small).render(fit(f_row if k == 0 else f_small, ln, bw - 40), True, TEXT if k == 0 else DIM),
                                    (bx + 20, by + 14 + k * 26))
            hint = ("A Select   B Cancel" if fm_pop else "A Open   B Up   Y Mark   X Options   L/R Page")
        elif view == "settings":
            srows = settings_text()
            set_vis = max(1, PH // 86)
            set_first = min(max(0, set_idx - set_vis // 2), max(0, len(SETTINGS_ROWS) - set_vis))
            for i, (nm, sub) in enumerate(srows[r] for r in SETTINGS_ROWS):
                if not set_first <= i < set_first + set_vis:
                    continue
                by, sel = top_y + (i - set_first) * 86, i == set_idx
                draw_button(canvas, (list_x, by, W - 2 * list_x, 78), SEL_BG if sel else PANEL, 12, 3, sel)
                canvas.blit(f_row.render(nm, True, TEXT if sel else DIM), (list_x + 24, by + 14))
                sub_w = W - 2 * list_x - 48
                if SETTINGS_ROWS[i] == "theme":
                    sw = [THEMES[theme_index(theme_id)][2][k] for k in ("BG", "PANEL", "SEL_BG", "ACCENT", "TEXT")]
                    sx = W - list_x - 24 - len(sw) * 24
                    for j, col in enumerate(sw):
                        pygame.draw.rect(canvas, col, (sx + j * 24, by + 29, 20, 20), border_radius=5)
                        pygame.draw.rect(canvas, DIM, (sx + j * 24, by + 29, 20, 20), 1, border_radius=5)
                    sub_w = sx - (list_x + 24) - 12
                canvas.blit(f_small.render(fit(f_small, sub, sub_w), True, DIM), (list_x + 24, by + 46))
            if len(SETTINGS_ROWS) > set_vis:
                tr_h = set_vis * 86 - 8
                th_h = max(24, tr_h * set_vis // len(SETTINGS_ROWS))
                th_y = top_y + (tr_h - th_h) * set_first // max(1, len(SETTINGS_ROWS) - set_vis)
                ui_rect(canvas, PANEL, (W - 12, top_y, 6, tr_h), 3)
                pygame.draw.rect(canvas, ACCENT, (W - 12, th_y, 6, th_h), border_radius=3)
            if dd is not None:
                opts = dd_options(dd["kind"])
                dd_rh = 36
                dd_vis = max(1, min(len(opts), (H - 50 - top_y - 8) // dd_rh))
                row_by = top_y + (SETTINGS_ROWS.index(dd["kind"]) - set_first) * 86
                dd_w, dd_h = W - 2 * list_x - 48, dd_vis * dd_rh + 12
                dd_x, dd_y = list_x + 24, min(row_by + 80, H - 50 - dd_h)
                dd_first = min(max(0, dd["sel"] - dd_vis // 2), len(opts) - dd_vis)
                pygame.draw.rect(canvas, PANEL, (dd_x, dd_y, dd_w, dd_h), border_radius=10)
                pygame.draw.rect(canvas, ACCENT, (dd_x, dd_y, dd_w, dd_h), 2, border_radius=10)
                for slot, ti in enumerate(range(dd_first, dd_first + dd_vis)):
                    ry, rsel = dd_y + 6 + slot * dd_rh, ti == dd["sel"]
                    if rsel:
                        pygame.draw.rect(canvas, SEL_BG, (dd_x + 6, ry, dd_w - 12, dd_rh - 2), border_radius=8)
                    oid, oname, oswatch, odesc = opts[ti]
                    canvas.blit(f_small.render(fit(f_small, oname + ("   (current)" if oid == dd["orig"] else ""), dd_w - 180), True, TEXT if rsel else DIM),
                                (dd_x + 18, ry + 8))
                    if oswatch:
                        for j, col in enumerate(oswatch):
                            sx = dd_x + dd_w - 18 - (len(oswatch) - j) * 24
                            pygame.draw.rect(canvas, col, (sx, ry + 6, 20, 20), border_radius=5)
                            pygame.draw.rect(canvas, DIM, (sx, ry + 6, 20, 20), 1, border_radius=5)
                    elif odesc:
                        dt_ = f_small.render(fit(f_small, odesc, dd_w - 200), True, DIM)
                        canvas.blit(dt_, (dd_x + dd_w - 18 - dt_.get_width(), ry + 8))
                if len(opts) > dd_vis:
                    if dd_first > 0:
                        pygame.draw.polygon(canvas, ACCENT, [(dd_x + dd_w - 8, dd_y + 12), (dd_x + dd_w - 14, dd_y + 18), (dd_x + dd_w - 2, dd_y + 18)])
                    if dd_first + dd_vis < len(opts):
                        pygame.draw.polygon(canvas, ACCENT, [(dd_x + dd_w - 8, dd_y + dd_h - 12), (dd_x + dd_w - 14, dd_y + dd_h - 18), (dd_x + dd_w - 2, dd_y + dd_h - 18)])
            hint = ("Up/Down Browse   A Select   B Cancel   " if dd is not None else
                    "A Pick theme   " if SETTINGS_ROWS[set_idx] == "theme" else
                    "A Pick launcher   " if SETTINGS_ROWS[set_idx] == "launcher" else
                    "A Change   X Preview   " if SETTINGS_ROWS[set_idx] == "splash" else
                    "A Toggle   " if SETTINGS_ROWS[set_idx] in ("swapab", "dpadjoy") else "A Open   ") + ("" if dd is not None else "B Back   START+SELECT Power off")
        elif view == "artwork":
            _sc = art["sc"]
            _s = _sc.snapshot() if _sc is not None else {"state": "idle", "total": 0, "done": 0, "found": 0, "missed": 0, "failed": 0, "current": "", "msg": ""}
            _run = _s["state"] == "running"
            _have, _all = art_counts()
            _rows = [("SteamGridDB API key", ("Set: " + artwork.key_hint(art["key"]) + "   A changes it") if artwork.valid_key(art["key"]) else "Not set   A types it (free key: steamgriddb.com, Preferences, API)"),
                     ("Download missing artwork + details", ("Downloading...   A stops" if _run else "%d of %d games have artwork   A starts" % (_have, _all))),
                     ("Retry games with no match", "Ask SteamGridDB again about games it could not find   A starts"),
                     ("Show artwork on game cards", ("On" if art_on() else "Off") + "   A toggles")]
            for i, (nm, sub) in enumerate(_rows):
                by, sel = top_y + i * 64, i == art_idx
                draw_button(canvas, (list_x, by, W - 2 * list_x, 58), SEL_BG if sel else PANEL, 12, 3, sel)
                canvas.blit(f_row.render(nm, True, TEXT if sel else DIM), (list_x + 24, by + 8))
                canvas.blit(f_small.render(fit(f_small, sub, W - 2 * list_x - 48), True, DIM), (list_x + 24, by + 34))
            py = top_y + 4 * 64 + 4
            if _run or _s["state"] in ("done", "stopped", "error"):
                if _s["total"]:
                    ui_rect(canvas, PANEL, (list_x, py, W - 2 * list_x, 10), 5)
                    pygame.draw.rect(canvas, ACCENT, (list_x, py, int((W - 2 * list_x) * min(1.0, _s["done"] / float(_s["total"]))), 10), border_radius=5)
                _line = ("Now: " + _s["current"]) if _run else _s["msg"]
                canvas.blit(f_small.render(fit(f_small, _line, W - 2 * list_x), True, (230, 70, 60) if _s["state"] == "error" else TEXT), (list_x, py + 16))
                canvas.blit(f_small.render("Found %d   No match %d   Failed %d   (%d of %d)" % (_s["found"], _s["missed"], _s["failed"], _s["done"], _s["total"]), True, DIM), (list_x, py + 38))
            else:
                canvas.blit(f_small.render(fit(f_small, "Your own images work too: ROMS/artwork/<system>/<game file name>.png", W - 2 * list_x), True, DIM), (list_x, py + 16))
            if time.time() < art["until"]:
                canvas.blit(f_small.render(fit(f_small, art["msg"], W - 2 * list_x), True, ACCENT), (list_x, py + 60))
            hint = "A Select   " + ("X Stop   " if _run else "") + "B Back"
        elif view == "coreinstall":
            ci_s = ci.snapshot()
            px, py, pw, ph = list_x, top_y, W - 2 * list_x, 336 + DY
            ui_rect(canvas, PANEL, (px, py, pw, ph), 10)
            n_missing = sum(1 for r in ci_rows if not r["installed"])
            if ci_s["busy"]:
                _anim_clock[2] = True
                cname = CORE_NAMES.get(ci_s["core"]) or ci_s["core"].replace("_", " ")
                head = "Downloading %s   %d%%" % (cname, ci_s["pct"]) + ("   (%d of %d)" % (ci_s["index"], ci_s["total"]) if ci_s["total"] > 1 else "")
                hcol = ACCENT
            elif ci_s["msg"]:
                head, hcol = ci_s["msg"], (BIOS_BAD if ci_s["failed"] and not ci_s["ok"] else BIOS_GOOD if ci_s["ok"] else TEXT)
            elif n_missing:
                head, hcol = "%d core%s available to install" % (n_missing, "" if n_missing == 1 else "s") + ("" if rd_net() else "   (not on Wi-Fi)"), TEXT
            else:
                head, hcol = "All compatible cores are installed", ACCENT
            canvas.blit(f_row.render(fit(f_row, head, pw - 48), True, hcol), (px + 24, py + 10))
            if ci_s["busy"]:
                pygame.draw.rect(canvas, DIM, (px + 24, py + 44, pw - 48, 6), 1, border_radius=3)
                pygame.draw.rect(canvas, ACCENT, (px + 24, py + 44, max(0, (pw - 48) * ci_s["pct"] // 100), 6), 0, border_radius=3)
            top_c = py + 58
            ci_vis = 7 + DY // 44 - 1
            first_ci = min(max(0, ci_idx - ci_vis // 2), max(0, len(ci_rows) - ci_vis))
            for slot, r in enumerate(ci_rows[first_ci:first_ci + ci_vis]):
                i = first_ci + slot
                y, sel = top_c + slot * 44, i == ci_idx
                if sel:
                    ui_rect(canvas, SEL_BG, (px + 8, y, pw - 16, 40), 8)
                    pygame.draw.rect(canvas, ACCENT, (px + 8, y, pw - 16, 40), 2, border_radius=8)
                canvas.blit(f_small.render(fit(f_small, r["name"], 200), True, TEXT if sel else DIM), (px + 20, y + 10))
                canvas.blit(f_small.render(fit(f_small, ", ".join(r["systems"]), pw - 20 - 220 - 130), True, DIM), (px + 232, y + 10))
                if r["installed"]:
                    tag, tcol = "Installed", BIOS_GOOD
                elif ci_s["busy"] and ci_s["core"] == r["core"]:
                    tag, tcol = "%d%%" % ci_s["pct"], ACCENT
                else:
                    tag, tcol = "A Install" if sel else "Not installed", ACCENT if sel else DIM
                canvas.blit(f_small.render(tag, True, tcol), (px + pw - 24 - f_small.size(tag)[0], y + 10))
            if not ci_rows:
                canvas.blit(f_row.render("No RetroArch systems on this device", True, TEXT), (px + 24, top_c + 10))
            hint = "B Cancel download" if ci_s["busy"] else "Up/Down Select   A Install   B Back"
        elif view == "emulators":
            emu_systems = [sy for sy in SYSTEMS if sy[2] == "retroarch" and compatible_cores(sy[0])]
            ui_rect(canvas, PANEL, (list_x, top_y, W - 2 * list_x, 336 + DY), 10)
            emu_vis = 7 + DY // 44
            first_emu = min(max(0, emu_idx - emu_vis // 2), max(0, len(emu_systems) - emu_vis))
            for slot, sy in enumerate(emu_systems[first_emu:first_emu + emu_vis]):
                i = first_emu + slot
                sid, _tag, _runner, _ext, fullname = sy
                cores = compatible_cores(sid)
                chosen = state.get("emulators", {}).get(sid, default_core(sid))
                if chosen not in cores:
                    chosen = default_core(sid) if default_core(sid) in cores else (cores[0] if cores else "No compatible core")
                y = top_y + 8 + slot * 44
                sel = i == emu_idx
                if sel:
                    ui_rect(canvas, SEL_BG, (list_x + 8, y, W - 2 * list_x - 16, 40), 8)
                    pygame.draw.rect(canvas, ACCENT, (list_x + 8, y, W - 2 * list_x - 16, 40), 2, border_radius=8)
                canvas.blit(f_small.render(fit(f_small, fullname, 300), True, TEXT if sel else DIM), (list_x + 20, y + 3))
                core_txt = chosen.replace("_", " ")
                canvas.blit(f_small.render(fit(f_small, "< " + core_txt + " >", 190), True, ACCENT if sel else TEXT), (W - list_x - 205, y + 14))
            if not any(compatible_cores(sy[0]) for sy in emu_systems):
                canvas.blit(f_row.render("No installed compatible RetroArch cores found", True, TEXT), (list_x + 24, top_y + 20))
            hint = "Up/Down System   Left/Right Change compatible core   B Back"
        elif view == "bios":
            ROW_H = 34
            px, py, pw, ph = list_x, top_y, W - 2 * list_x, 336 + DY
            ui_rect(canvas, PANEL, (px, py, pw, ph), 10)
            brows, bsumm = bios_cache if bios_cache else ([], {"systems": 0, "missing": 0, "optional": 0, "ok": 0})
            canvas.blit(f_row.render(fit(f_row, bios_summary_text(bsumm), pw - 48), True,
                                     BIOS_BAD if bsumm["missing"] else (ACCENT if bsumm["systems"] else DIM)), (px + 24, py + 10))
            where = biosctl.display_dir(bios_dirs()[0], ROMS_ROOT)
            blines = biosctl.build_lines(brows, bios_all, where)
            if not blines:
                blines = [("none", "Nothing to check: no installed emulator uses BIOS files", "")]
            top_b = py + 46
            vis = max(1, (ph - 56) // ROW_H)
            max_scroll = max(0, len(blines) - vis)
            bios_scroll = min(max(0, bios_scroll), max_scroll)
            target = bios_scroll * ROW_H
            if abs(target - bios_pos) < 0.5:
                bios_pos = float(target)
            else:
                bios_pos += (target - bios_pos) * min(1.0, _anim_clock[1] * 18.0)
                _anim_clock[2] = True
            pygame.draw.line(canvas, DIM, (px + 16, top_b - 4), (px + pw - 16, top_b - 4), 1)
            canvas.set_clip(pygame.Rect(px, top_b, pw, ph - 56))
            for i, (kind, left, right) in enumerate(blines):
                y = int(top_b + i * ROW_H - bios_pos)
                if y < top_b - ROW_H or y > py + ph:
                    continue
                rcol = {"miss": BIOS_BAD, "opt": BIOS_WARN, "diff": BIOS_WARN, "case": BIOS_WARN, "ok": BIOS_GOOD, "head": DIM}.get(kind, DIM)
                if kind == "head":
                    canvas.blit(f_row.render(fit(f_row, left, pw - 48 - 190), True, ACCENT), (px + 24, y + 4))
                    canvas.blit(f_small.render(right, True, rcol), (px + pw - 30 - f_small.size(right)[0], y + 8))
                elif kind == "path":
                    canvas.blit(f_small.render(fit(f_small, left, pw - 96), True, DIM), (px + 56, y + 6))
                elif kind == "none":
                    canvas.blit(f_row.render(fit(f_row, left, pw - 48), True, TEXT), (px + 24, y + 4))
                else:
                    canvas.blit(f_small.render(fit(f_small, left, pw - 60 - 130), True, TEXT), (px + 40, y + 6))
                    canvas.blit(f_small.render(right, True, rcol), (px + pw - 30 - f_small.size(right)[0], y + 6))
            canvas.set_clip(None)
            if max_scroll > 0:
                track_h = ph - 64
                bar_h = max(24, int(track_h * vis / len(blines)))
                bar_y = top_b + int((track_h - bar_h) * (bios_pos / (max_scroll * ROW_H)))
                pygame.draw.rect(canvas, DIM, (px + pw - 10, top_b, 4, track_h), 1, border_radius=2)
                pygame.draw.rect(canvas, ACCENT, (px + pw - 10, bar_y, 4, bar_h), 0, border_radius=2)
            hint = "Up/Down Scroll   L/R Page   X %s   A Recheck   B Back" % ("Only problems" if bios_all else "Show all")
        elif view == "info":
            ROW_H = 42
            px, py, pw, ph = list_x, top_y, W - 2 * list_x, 336 + DY
            ui_rect(canvas, PANEL, (px, py, pw, ph), 10)
            info_rows = settings_info_c()
            vis = max(1, (ph - 20) // ROW_H)
            max_scroll = max(0, len(info_rows) - vis)
            info_scroll = min(max(0, info_scroll), max_scroll)
            target = info_scroll * ROW_H
            dt_ = _anim_clock[1]
            if abs(target - info_pos) < 0.5:
                info_pos = float(target)
            else:
                info_pos += (target - info_pos) * min(1.0, dt_ * 18.0)
                _anim_clock[2] = True
            canvas.set_clip(pygame.Rect(px, py + 4, pw, ph - 8))
            for i, (k, v) in enumerate(info_rows):
                y = int(py + 14 + i * ROW_H - info_pos)
                if y < py - ROW_H or y > py + ph:
                    continue
                canvas.blit(f_row.render(k, True, DIM), (px + 24, y))
                canvas.blit(f_row.render(fit(f_row, v, pw - 48 - 190 - 14), True, TEXT), (px + 214, y))
            canvas.set_clip(None)
            if max_scroll > 0:
                track_h = ph - 24
                bar_h = max(24, int(track_h * vis / len(info_rows)))
                bar_y = py + 12 + int((track_h - bar_h) * (info_pos / (max_scroll * ROW_H)))
                pygame.draw.rect(canvas, DIM, (px + pw - 10, py + 12, 4, track_h), 1, border_radius=2)
                pygame.draw.rect(canvas, ACCENT, (px + pw - 10, bar_y, 4, bar_h), 0, border_radius=2)
                if info_scroll < max_scroll:
                    canvas.blit(f_tiny.render("v more", True, DIM), (px + pw - 70, py + ph - 18))
                if info_scroll > 0:
                    canvas.blit(f_tiny.render("^ more", True, DIM), (px + pw - 70, py + 6))
            hint = "Up/Down Scroll   L/R Page   B Back   START+SELECT Power off"
        elif view == "wifi":
            wst, wrows = wifi_status(), wscan.rows(wconf)
            wn = len(wrows) + 2
            ui_rect(canvas, PANEL, (list_x, top_y, W - 2 * list_x, 336 + DY), 10)
            head = wifictl.status_text(wst) if wconf["enabled"] else "Wi-Fi is off"
            canvas.blit(f_row.render(fit(f_row, head, W - 2 * list_x - 56), True, ACCENT), (list_x + 28, top_y + 8))
            if wst["state"] == "connected" and wst["rssi"] is not None:
                canvas.blit(f_small.render("%d dBm" % wst["rssi"], True, DIM), (W - list_x - 90, top_y + 12))
            vis = 7 + DY // 40
            first = min(max(0, wf_idx - vis // 2), max(0, wn - vis))
            for slot in range(min(vis, wn)):
                i = first + slot
                y, sel = top_y + 44 + slot * 40, i == wf_idx
                if sel:
                    ui_rect(canvas, SEL_BG, (list_x + 6, y, W - 2 * list_x - 12, 38), 8)
                    pygame.draw.rect(canvas, ACCENT, (list_x + 6, y, 5, 38), border_radius=3)
                col = TEXT if sel else DIM
                if i == 0:
                    on = wconf["enabled"]
                    pygame.draw.rect(canvas, ACCENT if on else DIM, (list_x + 28, y + 11, 16, 16), 0 if on else 2, border_radius=3)
                    canvas.blit(f_row.render("Wi-Fi", True, col), (list_x + 56, y + 8))
                    t = f_small.render("On" if on else "Off", True, DIM)
                    canvas.blit(t, (W - list_x - 28 - t.get_width(), y + 12))
                elif i == wn - 1:
                    canvas.blit(f_row.render("Join hidden network...", True, col), (list_x + 56, y + 8))
                else:
                    net = wrows[i - 1]
                    label = net["ssid"] + ("  (saved)" if net["saved"] else "") + ("  (not supported)" if net["unsupported"] else "")
                    canvas.blit(f_row.render(fit(f_row, label, W - 2 * list_x - 200), True, col), (list_x + 56, y + 8))
                    lock = f_tiny.render("WPA" if net["secured"] else "open", True, DIM)
                    canvas.blit(lock, (W - list_x - 100 - lock.get_width(), y + 14))
                    for b in range(4):
                        pygame.draw.rect(canvas, ACCENT if b < wifictl.bars(net["rssi"]) else PANEL if sel else BG,
                                         (W - list_x - 70 + b * 12, y + 26 - b * 5 - 4, 8, 6 + b * 5))
            if time.time() < wf_msg_until:
                note = wf_msg
            elif wscan.busy:
                note = "Scanning..."
            elif wscan.err:
                note = wscan.err
            elif not wconf["enabled"]:
                note = "Turn Wi-Fi on to scan"
            elif wscan.seen and not wrows:
                note = "No networks found - X to scan again"
            else:
                note = ""
            if note:
                canvas.blit(f_small.render(fit(f_small, note, W - 2 * list_x - 56), True, TEXT), (list_x + 28, top_y + 310 + DY))
            hint = "A Connect   X Scan   Y Forget   B Back"
        elif view == "bt":
            brows = list(btm.rows)
            bn = len(brows) + 1
            bt_idx = min(bt_idx, bn - 1)
            ui_rect(canvas, PANEL, (list_x, top_y, W - 2 * list_x, 336 + DY), 10)
            head = ("No Bluetooth adapter found (see rgos-logs.txt)" if btm.on is None and not btctl.adapter() else
                    "Starting Bluetooth..." if btm.on is None else "Bluetooth is on" if btm.on else "Bluetooth is off")
            canvas.blit(f_row.render(fit(f_row, head, W - 2 * list_x - 56), True, ACCENT), (list_x + 28, top_y + 8))
            vis = 7 + DY // 40
            first = min(max(0, bt_idx - vis // 2), max(0, bn - vis))
            for slot in range(min(vis, bn)):
                i = first + slot
                y, sel = top_y + 44 + slot * 40, i == bt_idx
                if sel:
                    ui_rect(canvas, SEL_BG, (list_x + 6, y, W - 2 * list_x - 12, 38), 8)
                    pygame.draw.rect(canvas, ACCENT, (list_x + 6, y, 5, 38), border_radius=3)
                col = TEXT if sel else DIM
                if i == 0:
                    on = bool(btm.on)
                    pygame.draw.rect(canvas, ACCENT if on else DIM, (list_x + 28, y + 11, 16, 16), 0 if on else 2, border_radius=3)
                    canvas.blit(f_row.render("Bluetooth", True, col), (list_x + 56, y + 8))
                    t = f_small.render("On" if on else "Off", True, DIM)
                    canvas.blit(t, (W - list_x - 28 - t.get_width(), y + 12))
                else:
                    d = brows[i - 1]
                    canvas.blit(f_row.render(fit(f_row, d["name"], W - 2 * list_x - 230), True, col), (list_x + 56, y + 8))
                    tag = "connected" if d["connected"] else "paired" if d["paired"] else ""
                    t = f_small.render(tag, True, ACCENT if d["connected"] else DIM)
                    canvas.blit(t, (W - list_x - 28 - t.get_width(), y + 12))
            if time.time() < btm.msg_until:
                note = btm.msg
            elif btm.scanning:
                note = "Scanning... put your device in pairing mode"
            elif btm.on and not brows:
                note = "No devices - put the device in pairing mode, then press X to scan"
            else:
                note = ""
            if note:
                canvas.blit(f_small.render(fit(f_small, note, W - 2 * list_x - 56), True, TEXT), (list_x + 28, top_y + 310 + DY))
            hint = "A Pair/Connect/Disconnect   X Scan   Y Forget   B Back"
        elif view == "ssh":
            si = ssh_info()
            wst_ = wifi_status()
            ip_ = wst_["ip"] or "(connect Wi-Fi first)"
            ui_rect(canvas, PANEL, (list_x, top_y, W - 2 * list_x, 336 + DY), 10)
            canvas.blit(f_row.render("SSH / file transfer is " + ("ON" if si["running"] else "off"), True, ACCENT), (list_x + 28, top_y + 14))
            lines_ = [("Address", ip_), ("Port", str(si["port"])), ("User", si["user"]), ("Password", si["password"]),
                      ("Files", "sftp://root@%s   (WinSCP, FileZilla, scp)" % (wst_["ip"] or "<ip>")),
                      ("Folders", "/media/roms = ROMS partition,  /boot = boot partition")]
            for k, (kk, vv) in enumerate(lines_):
                canvas.blit(f_row.render(kk, True, DIM), (list_x + 28, top_y + 62 + k * 40))
                canvas.blit(f_row.render(fit(f_row, vv, W - 2 * list_x - 56 - 150), True, TEXT), (list_x + 178, top_y + 62 + k * 40))
            canvas.blit(f_small.render(fit(f_small, "Change the password: put ssh-password.txt on the boot partition. Use a key: authorized_keys.", W - 2 * list_x - 56), True, DIM),
                        (list_x + 28, top_y + 310 + DY))
            hint = "A Turn " + ("off" if si["running"] else "on") + "   B Back"
        elif view == "kbd":
            KW = 636 + DX
            KX = (W - KW) // 2
            canvas.blit(f_small.render(kb.title, True, DIM), (KX, top_y - 4))
            ui_rect(canvas, PANEL, (KX, top_y + 16, KW, 52), 8)
            pygame.draw.rect(canvas, ACCENT, (KX, top_y + 16, KW, 52), 2, border_radius=8)
            shown = kb.text if kb.show else "*" * len(kb.text)
            canvas.blit(f_row.render(tail_fit(f_row, shown, 590 + DX) + ("_" if int(time.time() * 2) % 2 == 0 else ""), True, TEXT),
                        (KX + 14, top_y + 31))
            for r in range(5):
                keys = kb.keys(r)
                ky = top_y + 92 + r * 80 + (8 if r == 4 else 0)
                kw = (KW - 9 * 4) // 10 if r < 4 else (KW - 4 * 4) // 5
                for c, k in enumerate(keys):
                    kx = KX + c * (kw + 4)
                    sel = (r == kb.row and c == kb.col)
                    draw_button(canvas, (kx, ky, kw, 70), SEL_BG if sel else PANEL, 8, 4, sel)
                    label = KB_LAYER_NAMES[(kb.layer + 1) % 3] if k == "Layer" else k
                    t = f_row.render(label, True, ACCENT if (sel and r == 4) else (TEXT if sel else DIM))
                    canvas.blit(t, (kx + (kw - t.get_width()) // 2, ky + (70 - t.get_height()) // 2))
            hint = "A Type   B Delete   START Done" + ("   X Show/hide" if kb.secret else "")
        elif view == "bmap":
            ui_rect(canvas, PANEL, (list_x, top_y, W - 2 * list_x, 330 + DY), 14)
            sview = bmap.stick_view()
            canvas.blit(f_big.render("Stick calibration" if sview else "Button mapping", True, ACCENT), (list_x + 28, top_y + 22))
            if sview:
                canvas.blit(f_small.render("Stick %d of %d" % (min(bmap.cstick + 1, len(bmap.sticks)) if bmap.state == "sroll" else 1, len(bmap.sticks)),
                                           True, DIM), (list_x + 28, top_y + 58))
            elif bmap.state in ("prompt", "apply"):
                n = min(bmap.step + 1, bmap.total())
                canvas.blit(f_small.render("Button %d of %d" % (n, bmap.total()), True, DIM), (list_x + 28, top_y + 58))
            text_w = W - 2 * list_x - 60 - (170 if sview else 0)
            for i, line in enumerate(bmap.lines()):
                for j, wl in enumerate(wrap(f_big if i == 0 else f_row, line, text_w)):
                    canvas.blit((f_big if i == 0 else f_row).render(wl, True, TEXT if i == 0 else DIM),
                                (list_x + 28, top_y + 110 + i * 56 + j * 26))
            if sview:
                _, sx, sy, sreach = sview
                gcx, gcy, gr = W - list_x - 28 - 70, top_y + 165 + DY // 2, 62
                pygame.draw.circle(canvas, BG, (gcx, gcy), gr)
                pygame.draw.circle(canvas, DIM, (gcx, gcy), gr, 2)
                pygame.draw.line(canvas, DIM, (gcx - gr, gcy), (gcx + gr, gcy), 1)
                pygame.draw.line(canvas, DIM, (gcx, gcy - gr), (gcx, gcy + gr), 1)
                for (ai, sg) in ((0, -1), (0, 1), (1, -1), (1, 1)):
                    mx, my = gcx + (sg * gr if ai == 0 else 0), gcy + (sg * gr if ai == 1 else 0)
                    pygame.draw.circle(canvas, ACCENT if (ai, sg) in sreach else PANEL, (mx, my), 8)
                    pygame.draw.circle(canvas, DIM, (mx, my), 8, 1)
                pygame.draw.circle(canvas, TEXT, (gcx + int(sx * (gr - 10)), gcy + int(sy * (gr - 10))), 8)
            hint = (("A Retry this step   B Back" if bmap.can_resume() and not forced else "A/B Back") if bmap.state in ("done", "fail") else
                    "Move the stick as shown (a stick that is not moved is skipped)" if sview else
                    "Press the button shown (wizard stops by itself if idle)")
            if forced:
                hint = "Required first-time setup" + ("   MENU Skip" if forced_fails >= 3 else "")
        elif view == "systems":
            if not vsys:
                for i, m in enumerate(["No games found.",
                                       "Put GBA ROMs in roms/gba/, NES ROMs in roms/nes/",
                                       "Mega Drive ROMs in roms/genesis/ (MD, GEN, SMD, BIN).",
                                       "or launcher scripts in roms/ports/, then press X (B = back)."]):
                    canvas.blit((f_big if i == 0 else f_row).render(m, True, TEXT if i == 0 else DIM),
                                (40, 150 + i * 34))
            sys_rows = 6 + DY // 56
            sys_first = max(0, min(sys_idx - sys_rows // 2, len(vsys) - sys_rows))
            for r, (xid, xtag, xcore, _e, xname) in enumerate(vsys):
                if not sys_first <= r < sys_first + sys_rows:
                    continue
                y, sel, cnt = top_y + (r - sys_first) * 56, r == sys_idx, len(games_of(xid))
                if sel:
                    ui_rect(canvas, SEL_BG, (list_x, y, list_w, 52), 8)
                    pygame.draw.rect(canvas, ACCENT, (list_x, y, 5, 52), border_radius=3)
                ui_rect(canvas, PANEL if not sel else BG, (list_x + 18, y + 6, 64, 40), 6)
                t = f_big.render(xtag, True, ACCENT if sel else DIM)
                canvas.blit(t, (list_x + 50 - t.get_width() // 2, y + 13))
                canvas.blit(f_row.render(fit(f_row, xname, list_w - 220), True, TEXT if sel else DIM),
                            (list_x + 98, y + 4))
                canvas.blit(f_small.render("%d %s%s" % (cnt, "port" if xid == "ports" else "game",
                                                         "" if cnt == 1 else "s"), True, DIM),
                            (list_x + 98, y + 28))
            px, cnt = 500 + DX, len(games)
            if vsys:
                ui_rect(canvas, PANEL, (px, top_y, 200, PH), 10)
                ui_rect(canvas, SEL_BG, (px + 20, top_y + 20, 160, 110 + DY // 2), 8)
                ini = f_logo.render(stag, True, ACCENT)
                canvas.blit(ini, (px + 100 - ini.get_width() // 2, top_y + 52 + DY // 4))
                for i, line in enumerate(wrap(f_row, sname, 170)):
                    canvas.blit(f_row.render(line, True, TEXT), (px + 15, top_y + 148 + DY // 2 + i * 26))
                canvas.blit(f_small.render("%d %s%s" % (cnt, "port" if sid == "ports" else "game", "" if cnt == 1 else "s"), True, DIM),
                            (px + 15, top_y + 300 + DY))
                canvas.blit(f_small.render("Native Linux games" if score == "native" else "RetroArch + " + core_label(sid, state), True, DIM), (px + 15, top_y + 322 + DY))
            if not os.path.isdir(ROMS_DIR):
                canvas.blit(f_small.render("ROMS partition not found.", True, ACCENT), (list_x + 18, H - 52))
            hint = "A Open   B Back   X Rescan   START+SELECT Power off"
        elif not games:
            if view == "recents":
                msg = ["No recent games yet.",
                       "Games you run show up here, newest first.",
                       "(B = back)"]
            elif view == "favorites":
                msg = ["No favorite games yet.",
                       "In a game's list, highlight a game and press Y.",
                       "Favorites are saved to favorites.txt."]
            else:
                msg = ["No games found.",
                       "Put GBA ROMs in roms/gba/, NES ROMs in roms/nes/",
                       "Mega Drive ROMs in roms/genesis/ (MD, GEN, SMD, BIN).",
                       "or launcher scripts in roms/ports/, then X (B = back)."]
            for i, m in enumerate(msg):
                canvas.blit((f_big if i == 0 else f_row).render(m, True, TEXT if i == 0 else DIM),
                            (40, 150 + i * 34))
            hint = "B Back   X Rescan   START+SELECT Power off"
        else:
            first = max(0, min(idx - rows // 2, len(games) - rows))
            for r in range(rows):
                gi = first + r
                if gi >= len(games):
                    break
                y = top_y + r * row_h
                if gi == idx:
                    ui_rect(canvas, SEL_BG, (list_x, y, list_w, row_h - 4), 8)
                    pygame.draw.rect(canvas, ACCENT, (list_x, y, 5, row_h - 4), border_radius=3)
                badges = []
                if games[gi]["path"] in favorite_paths:
                    badges.append("★")
                if games[gi].get("card", 1) == 2:
                    badges.append("SD2")
                suffix = "  ".join(badges)
                canvas.blit(f_row.render(fit(f_row, games[gi]["title"], list_w - 40 - (len(suffix) * 10 if suffix else 0)),
                                         True, TEXT if gi == idx else DIM), (list_x + 18, y + 9))
                if suffix:
                    bt = f_tiny.render(suffix, True, ACCENT)
                    canvas.blit(bt, (list_x + list_w - 14 - bt.get_width(), y + 14))
            if len(games) > rows:
                bar_h = H - 64 - top_y
                th = max(24, int(bar_h * rows / len(games)))
                ty = top_y + int((bar_h - th) * first / max(1, len(games) - rows))
                ui_rect(canvas, PANEL, (list_x + list_w + 6, top_y, 6, bar_h), 3)
                pygame.draw.rect(canvas, ACCENT, (list_x + list_w + 6, ty, 6, th), border_radius=3)

            g = games[idx]
            px = 500 + DX
            ui_rect(canvas, PANEL, (px, top_y, 200, PH), 10)
            tile_w, tile_h = 160, 130 + DY // 2
            ui_rect(canvas, SEL_BG, (px + 20, top_y + 14, tile_w, tile_h), 8)
            cover = None
            _settled = time.monotonic() - last_act >= DETAIL_SETTLE_S
            if art_on():
                _ap = art_index.lookup(g["sid"], g["path"])
                cover = _detail_cover(_ap, tile_w - 8, tile_h - 8, _settled) if _ap else None
            if cover is not None:
                canvas.blit(cover, (px + 20 + (tile_w - cover.get_width()) // 2, top_y + 14 + (tile_h - cover.get_height()) // 2))
            else:
                ini = f_logo.render(g["title"][:1].upper(), True, ACCENT)
                canvas.blit(ini, (px + 100 - ini.get_width() // 2, top_y + 62 + DY // 4))
            ty_ = top_y + 152 + DY // 2
            for line in wrap_n(f_row, g["title"], 170, 2):
                canvas.blit(f_row.render(line, True, TEXT), (px + 15, ty_))
                ty_ += 24
            _gm = game_meta(g, _settled) if art_on() else {}
            _yr = _gm.get("year") or ""
            canvas.blit(f_small.render("%.1f MB%s" % (g["size"] / 1048576, ("   %s" % _yr) if _yr else ""), True, DIM),
                        (px + 15, top_y + 300 + DY))
            canvas.blit(f_small.render(fit(f_small, game_runner_text(g, state), 175), True, DIM), (px + 15, top_y + 322 + DY))
            _desc = _gm.get("description")
            if _desc:
                _lh = f_small.get_linesize()
                _n = max(0, (top_y + 296 + DY - ty_) // _lh)
                for _line in (wrap_n(f_small, _desc, 170, min(_n, 6)) if _n else []):
                    canvas.blit(f_small.render(_line, True, DIM), (px + 15, ty_ + 2))
                    ty_ += _lh
            hint = ("A Run   Y Favorite/unfavorite   B Back   L/R Page   X Rescan   START+SELECT Power off"
                    if view == "games" else "A Run   B Back   L/R Page   X Rescan   START+SELECT Power off")

        if inp.conf.get("debug") and inp.last_raw:
            hint += "   [" + inp.last_raw + "]"
        if CLASSIC_UI[0]:
            if hint:
                draw_classic_footer(canvas, f_tiny, hint)
        else:
            canvas.blit(f_small.render(hint, True, DIM), (20, H - 28))

        bri = rd_bri()
        if bri and bri[1] != bri_seen:
            if bri_seen is not None:
                bri_pct, bri_show_until = bri[0], time.time() + 1.5
            bri_seen = bri[1]
        if time.time() < bri_show_until:
            bx, by, bw, bh = W // 2 - 130, H - 152, 260, 44
            pygame.draw.rect(canvas, PANEL, (bx, by, bw, bh), border_radius=10)
            pygame.draw.rect(canvas, ACCENT, (bx, by, bw, bh), 2, border_radius=10)
            canvas.blit(f_small.render("LIGHT", True, TEXT), (bx + 12, by + 14))
            pygame.draw.rect(canvas, BG, (bx + 66, by + 17, 130, 10), border_radius=5)
            pygame.draw.rect(canvas, ACCENT, (bx + 66, by + 17, max(6, 130 * bri_pct // 100), 10), border_radius=5)
            canvas.blit(f_small.render("%d%%" % bri_pct, True, TEXT), (bx + 208, by + 14))

        _pt2 = time.perf_counter()
        present()
        _pt3 = time.perf_counter()
        if flow_on:
            fmoving = (anim_moving or flow_fx != flow_t or flow_fv != 0.0 or time.monotonic() - last_act < 0.35)
            flow_warm(fcards, flow_t, 0.004 if fmoving else 0.012, fmoving)
        if prof.enabled:
            prof.frame(_pt1 - _pt0, _pt2 - _pt1, _pt3 - _pt2, time.perf_counter() - _pt3, "%s/%s" % (launcher_id, view))
        idle = (view in IDLE_VIEWS and not forced and time.monotonic() - last_act > 3.0
                and time.time() >= bri_show_until)
        clock.tick(60 if anim_moving or (time.monotonic() - last_act < 0.5) else (15 if idle else 30))

    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass
    _BOOST.restore()  # a game launch records the current governors to restore them later
    if not windowed:
        fbout.set_graphics(False)
    pygame.quit()
    sys.exit(code)


def run():
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        log("CRASH\n" + traceback.format_exc())
        fbout.set_graphics(False)
        sys.exit(1)


if __name__ == "__main__":
    run()
