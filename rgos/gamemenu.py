#!/usr/bin/env python3
"""RG OS in-game menu: tap the Menu button while a game runs and a panel slides in from the right.

    gamemenu.py daemon      run the watcher (started by rgos-session next to rgos-overlay)

What happens:
  * rgos-launch writes /run/rgos/ingame (JSON: kind "retroarch"|"native", title, pid) while a game runs.
  * The daemon watches the hub pad ("RG OS Gamepad") without grabbing it. A *tap* of Menu (Mode) opens the panel;
    holding Menu, or pressing anything else while it is down, is left alone so RetroArch hotkey combos still work.
  * On open the pad is grabbed (the game stops seeing buttons), the game is paused (RetroArch: PAUSE_TOGGLE over its
    network command port; native ports: SIGSTOP to the port's process group) and the panel slides in over the
    framebuffer, exactly like rgos-overlay paints the volume bar (the pixels under it are saved and put back).
  * Resume / Restart / Save State / Load State / Exit Game. Restart and Exit ask first. Save/Load are RetroArch only.
    Up/Down move, A selects, B or Menu goes back / resumes.
  * Restart of a native port: the port is stopped and rgos-launch starts it again (it sees /run/rgos/restart).

  * RetroArch gets the same panel as native ports, on a hardware overlay plane above the game (drmplane.py). If the display
    has no plane to give, a Menu tap opens RetroArch's own menu (RGUI, MENU_TOGGLE) instead, since a framebuffer panel
    would sit behind the game. RGOS_GAMEMENU_RGUI=1 always uses RGUI for RetroArch.

Environment: RGOS_RUN (/run/rgos), RGOS_GAME_FLAG, RGOS_RA_PORT (55355), RGOS_SYS_INPUT, RGOS_DEV_INPUT, plus the
framebuffer variables of rgos-overlay (RGOS_FB_DEV, RGOS_FB_ROTATE).
"""
import fcntl, glob, importlib.machinery, importlib.util, json, os, select, signal, socket, struct, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_DIR = os.environ.get("RGOS_RUN", "/run/rgos")
GAME_FLAG = os.environ.get("RGOS_GAME_FLAG", os.path.join(RUN_DIR, "ingame"))
COMBO_FLAG = os.environ.get("RGOS_COMBO_FLAG", os.path.join(RUN_DIR, "combo-swallow"))
SYS_INPUT = os.environ.get("RGOS_SYS_INPUT", "/sys/class/input")
DEV_INPUT = os.environ.get("RGOS_DEV_INPUT", "/dev/input")
HUB_NAME = "RG OS Gamepad"
RA_ADDR = ("127.0.0.1", int(os.environ.get("RGOS_RA_PORT", "55355") or 55355))
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

EVFMT = struct.Struct("llHHi")
EV_KEY, EV_ABS = 1, 3
BTN_A, BTN_B, BTN_START, BTN_MODE = 0x130, 0x131, 0x13B, 0x13C
DPAD_UP, DPAD_DOWN, ABS_HAT0Y = 0x220, 0x221, 0x11
ABS_Y, STICK_ON = 0x01, 16384        # "DPAD to joystick" turns D-pad presses into left-stick Y: past half = up / down
EVIOCGRAB = 0x40044590

BASE_W = 720                 # canvas width the sizes below were designed for (same as rgos-overlay)
PANEL_W, SHADOW = 300, 18    # panel and soft edge shadow, in BASE_W pixels
SLIDE_S, FPS = 0.28, 30.0    # slide duration and frame rate
TAP_MAX_S = 0.8              # a Menu press longer than this is a hold, not a tap
COMBO_QUIET_S = TAP_MAX_S + 1.0   # a Menu tap this soon after the hub swallowed Menu+Select belongs to that combo
GRACE_S = 3.0                # SIGTERM -> SIGKILL grace when stopping a game
DEFAULT_THEME = {"BG": (13, 15, 26), "PANEL": (24, 28, 46), "ACCENT": (255, 99, 71), "TEXT": (232, 235, 245)}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---- pure helpers -------------------------------------------------------------------------------------------------

def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(p):
    return 1.0 - (1.0 - clamp(p)) ** 3


def open_curve(p):
    """Panel position (0 off screen .. 1 fully in) while sliding in; p is linear time 0..1."""
    return ease_out(p)


def close_curve(p):
    """Panel position while sliding out; accelerates away."""
    return 1.0 - clamp(p) ** 2


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def fit(text, maxw, measure, size, bold=False):
    if measure(text, size, bold) <= maxw:
        return text
    while len(text) > 1 and measure(text + "...", size, bold) > maxw:
        text = text[:-1]
    return text.rstrip() + "..."


def parse_events(data):
    """Raw evdev bytes -> [(type, code, value)]."""
    out = []
    for off in range(0, len(data) - EVFMT.size + 1, EVFMT.size):
        _, _, etype, code, value = EVFMT.unpack_from(data, off)
        out.append((etype, code, value))
    return out


def translate(etype, code, value):
    """One pad event -> menu input name ('up' 'down' 'ok' 'back' 'close') or None."""
    if etype == EV_KEY and value in (1, 2):
        if code == DPAD_UP:
            return "up"
        if code == DPAD_DOWN:
            return "down"
        if value == 1:
            if code in (BTN_A, BTN_START):
                return "ok"
            if code == BTN_B:
                return "back"
            if code == BTN_MODE:
                return "close"
    elif etype == EV_ABS and code == ABS_HAT0Y:
        return {-1: "up", 1: "down"}.get(value)
    return None


class TapDetector:
    """True when Menu is pressed and released on its own, quickly (so hotkey combos are not stolen)."""

    def __init__(self, max_hold=TAP_MAX_S):
        self.max_hold, self.down, self.other = max_hold, None, False

    def feed(self, etype, code, value, now):
        if etype == EV_KEY and code == BTN_MODE:
            if value == 1:
                self.down, self.other = now, False
            elif value == 0 and self.down is not None:
                ok = not self.other and now - self.down <= self.max_hold
                self.down = None
                return ok
        elif self.down is not None and ((etype == EV_KEY and value == 1) or (etype == EV_ABS and value != 0)):
            self.other = True
        return False


def combo_recent(path=None, now=None):
    """True when the input hub swallowed a Menu+Select press a moment ago (DPAD to joystick combo).

    The hub hides Select from the game while Menu is down, so TapDetector never sees "another button" and would
    take the Menu release for a tap.
    """
    try:
        age = (time.time() if now is None else now) - os.path.getmtime(path or COMBO_FLAG)
    except OSError:
        return False
    return age < COMBO_QUIET_S


# ---- the menu model -----------------------------------------------------------------------------------------------

class MenuModel:
    """Items, selection and the confirm step. press() returns an action id or None."""

    def __init__(self, kind="retroarch", title=""):
        self.kind, self.title = kind, (title or "Game")
        self.sel, self.confirm = 0, None
        self.status, self.status_until = "", 0.0

    def items(self):
        if self.confirm:
            return [("cancel", "Cancel"), (self.confirm + "!", "Yes, " + self.confirm)]
        its = [("resume", "Resume"), ("restart", "Restart")]
        if self.kind == "retroarch":
            its += [("save", "Save State"), ("load", "Load State")]
        its.append(("exit", "Exit Game"))
        return its

    def header(self):
        """(small label, big title)."""
        if self.confirm:
            return "ARE YOU SURE?", "%s game?" % self.confirm.capitalize()
        return "PAUSED", self.title

    def say(self, text, until):
        self.status, self.status_until = text, until

    def status_now(self, now):
        return self.status if self.status and now < self.status_until else ""

    def press(self, name):
        its = self.items()
        if name == "up":
            self.sel = (self.sel - 1) % len(its)
        elif name == "down":
            self.sel = (self.sel + 1) % len(its)
        elif name == "back" or name == "close":
            if self.confirm:
                return self._cancel()
            return "resume"
        elif name == "ok":
            ident = its[self.sel][0]
            if ident == "cancel":
                return self._cancel()
            if ident in ("restart", "exit"):
                self.confirm, self.sel = ident, 0
                return None
            if ident.endswith("!"):
                self.confirm = None
                return ident[:-1]
            return ident
        return None

    def _cancel(self):
        ident, self.confirm = self.confirm, None
        self.sel = [i for i, it in enumerate(self.items()) if it[0] == ident][0]
        return None


# ---- drawing: layout is a list of backend-neutral ops, so the device (pygame) and the demo (PIL) draw the same menu --

def icon_ops(kind, cx, cy, r, col, s):
    lw = max(2, int(2 * s))
    if kind == "resume":
        return [("poly", [(cx - r * .5, cy - r * .75), (cx - r * .5, cy + r * .75), (cx + r * .8, cy)], col)]
    if kind == "restart":
        return [("circle", (cx, cy), r * .72, col, lw),
                ("poly", [(cx + r * .05, cy - r * 1.15), (cx + r * 1.0, cy - r * .7), (cx + r * .15, cy - r * .2)], col)]
    if kind == "save":
        return [("frame", (cx - r * .85, cy - r * .85, r * 1.7, r * 1.7), col, lw, 3),
                ("rect", (cx - r * .45, cy - r * .85, r * .9, r * .55), col),
                ("rect", (cx - r * .5, cy + r * .1, r, r * .75), col)]
    if kind == "load":
        return [("frame", (cx - r * .85, cy - r * .85, r * 1.7, r * 1.7), col, lw, 3),
                ("poly", [(cx, cy - r * .55), (cx - r * .5, cy + r * .05), (cx + r * .5, cy + r * .05)], col),
                ("rect", (cx - r * .18, cy, r * .36, r * .5), col)]
    if kind == "cancel":
        return [("poly", [(cx + r * .6, cy - r * .75), (cx + r * .6, cy + r * .75), (cx - r * .8, cy)], col)]
    if kind.endswith("!"):
        return [("line", (cx - r * .8, cy), (cx - r * .25, cy + r * .6), col, lw + 1),
                ("line", (cx - r * .25, cy + r * .6), (cx + r * .85, cy - r * .6), col, lw + 1)]
    return [("line", (cx - r * .7, cy - r * .7), (cx + r * .7, cy + r * .7), col, lw + 1),   # exit: a cross
            ("line", (cx - r * .7, cy + r * .7), (cx + r * .7, cy - r * .7), col, lw + 1)]


def layout(model, w, h, s, theme, measure, pos=1.0, now=0.0):
    """Ops for the panel layer (w x h, panel-local pixels). The left `shadow` pixels are the edge shadow."""
    BG, PANEL, ACCENT, TEXT = theme["BG"], theme["PANEL"], theme["ACCENT"], theme["TEXT"]
    sh = int(SHADOW * s)
    pw = w - sh
    ops = []
    steps = max(4, sh // 3)
    for i in range(steps):
        x0, x1 = i * sh // steps, (i + 1) * sh // steps
        ops.append(("rect", (x0, 0, max(1, x1 - x0), h), (0, 0, 0, int(80 * ((i + 1) / float(steps)) ** 2))))
    ops.append(("rect", (sh, 0, pw, h), tuple(PANEL) + (238,)))
    ops.append(("rect", (sh, 0, max(2, int(3 * s)), h), tuple(ACCENT)))
    pad = int(28 * s)
    x = sh + pad
    inner = pw - pad - int(20 * s)
    label, title = model.header()
    ops.append(("text", (x, int(26 * s)), label, ACCENT, int(12 * s), True))
    ops.append(("text", (x, int(44 * s)), fit(title, inner, measure, int(21 * s), True), TEXT, int(21 * s), True))
    ops.append(("rect", (x, int(86 * s), inner, max(1, int(s))), mix(PANEL, TEXT, .2)))
    row_h, gap, y = int(46 * s), int(6 * s), int(106 * s)
    dim = mix(TEXT, PANEL, .38)
    for i, (ident, text) in enumerate(model.items()):
        e = ease_out((pos - 0.2 - 0.08 * i) / 0.5)          # rows glide in one after another while the panel opens
        dx = int((1.0 - e) * 44 * s)
        rx, rw = x - int(12 * s) + dx, inner + int(12 * s)
        on = i == model.sel
        if on:
            ops.append(("rrect", (rx, y, rw, row_h), mix(PANEL, ACCENT, .22) + (244,), int(10 * s)))   # opaque mix: draw ops set pixels, they do not blend
            ops.append(("rrect", (rx, y + int(row_h * .2), max(3, int(4 * s)), int(row_h * .6)), tuple(ACCENT), 2))
        col = TEXT if on else dim
        ops += icon_ops(ident, rx + int(28 * s), y + row_h // 2, int(9 * s), ACCENT if on else dim, s)
        ops.append(("text", (rx + int(54 * s), y + (row_h - int(18 * s)) // 2 - 1), text, col, int(18 * s), on))
        y += row_h + gap
    msg = model.status_now(now)
    if msg:
        ops.append(("text", (x, h - int(78 * s)), msg, ACCENT, int(14 * s), True))
    hy, fs = h - int(40 * s), int(12 * s)
    bx = x
    for letter, word in (("A", "Select"), ("B", "Back")):
        r = int(10 * s)
        ops.append(("circle", (bx + r, hy + r), r, mix(PANEL, TEXT, .22), 0))
        ops.append(("text", (bx + r - measure(letter, fs, True) // 2, hy + r - int(8 * s)), letter, TEXT, fs, True))
        ops.append(("text", (bx + 2 * r + int(8 * s), hy + r - int(8 * s)), word, dim, fs, False))
        bx += 2 * r + int(8 * s) + measure(word, fs, False) + int(22 * s)
    return ops


class PygameCanvas:
    """Draws layout ops with pygame (the device)."""

    def __init__(self, pg):
        self.pg, self.fonts = pg, {}

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            path = FONT_BOLD if bold else FONT_PATH
            try:
                self.fonts[key] = self.pg.font.Font(path, size) if os.path.exists(path) else self.pg.font.Font(None, int(size * 1.3))
            except Exception:
                self.fonts[key] = self.pg.font.Font(None, int(size * 1.3))
        return self.fonts[key]

    def measure(self, text, size, bold=False):
        return self.font(size, bold).size(text)[0]

    def render(self, ops, w, h):
        pg = self.pg
        sf = pg.Surface((w, h), pg.SRCALPHA)
        for op in ops:
            k = op[0]
            if k == "rect":
                sf.fill(op[2], pg.Rect([int(v) for v in op[1]]))
            elif k == "rrect":
                pg.draw.rect(sf, op[2], [int(v) for v in op[1]], border_radius=op[3])
            elif k == "frame":
                pg.draw.rect(sf, op[2], [int(v) for v in op[1]], op[3], border_radius=op[4])
            elif k == "circle":
                pg.draw.circle(sf, op[3], (int(op[1][0]), int(op[1][1])), max(1, int(op[2])), op[4])
            elif k == "poly":
                pg.draw.polygon(sf, op[2], [(int(a), int(b)) for a, b in op[1]])
            elif k == "line":
                pg.draw.line(sf, op[3], (int(op[1][0]), int(op[1][1])), (int(op[2][0]), int(op[2][1])), op[4])
            elif k == "text":
                sf.blit(self.font(op[4], op[5]).render(op[2], True, op[3][:3]), (int(op[1][0]), int(op[1][1])))
        return sf


# ---- controlling the game -----------------------------------------------------------------------------------------

def read_game(path=None):
    """The ingame flag as a dict, or None when no game is running."""
    path = path or GAME_FLAG
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def find_pids(names, proc="/proc"):
    out = []
    for d in glob.glob(os.path.join(proc, "[0-9]*")):
        try:
            with open(os.path.join(d, "comm")) as f:
                if f.read().strip() in names:
                    out.append(int(os.path.basename(d)))
        except (OSError, ValueError):
            pass
    return out


def udp_cmd(cmd, wait=False, timeout=0.3, addr=None):
    """Send a RetroArch network command; with wait, return the reply text (or None)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(timeout)
        s.sendto(cmd.encode(), addr or RA_ADDR)
        if wait:
            return s.recvfrom(1024)[0].decode("ascii", "replace")
    except (OSError, socket.timeout):
        pass
    finally:
        s.close()
    return None


class GameControl:
    """Pause / resume / restart / exit / save / load for the running game. Everything the OS offers is injected."""

    def __init__(self, info, alive, udp=udp_cmd, killpg=os.killpg, kill=os.kill, pids=find_pids,
                 sleep=time.sleep, clock=time.monotonic, restart_flag=None, reaper=True):
        self.info, self.alive, self.udp, self.killpg, self.kill = info, alive, udp, killpg, kill
        self.pids, self.sleep, self.clock, self.reaper = pids, sleep, clock, reaper
        self.restart_flag = restart_flag or os.path.join(RUN_DIR, "restart")
        kind = info.get("kind")
        self.kind = kind if kind in ("retroarch", "native") else ("retroarch" if pids(("retroarch",)) else "native")
        self.we_paused = False

    # pause / resume
    def pause(self):
        if self.kind == "retroarch":
            reply = self.udp("GET_STATUS", True) or ""
            if "PAUSED" in reply.upper().split("CONTENTLESS")[0]:
                self.we_paused = False        # the user had it paused already: leave it that way
            else:
                self.udp("PAUSE_TOGGLE")
                self.we_paused = True
        else:
            self.we_paused = self._signal(signal.SIGSTOP)

    def resume(self):
        if not self.we_paused:
            return
        self.we_paused = False
        if self.kind == "retroarch":
            self.udp("PAUSE_TOGGLE")
        else:
            self._signal(signal.SIGCONT)

    def _signal(self, sig):
        pid = self.info.get("pid")
        if not pid:
            return False
        try:
            self.killpg(int(pid), sig)
            return True
        except OSError:
            return False

    # actions
    def perform(self, action):
        if action == "resume":
            self.resume()
        elif action == "restart":
            self.restart()
        elif action == "exit":
            self.exit()
        elif action == "load":
            self.load()
            self.resume()

    def save(self):
        if self.kind != "retroarch":
            return ""
        self.udp("SAVE_STATE")
        return "State saved"

    def load(self):
        if self.kind == "retroarch":
            self.udp("LOAD_STATE")

    def restart(self):
        if self.kind == "retroarch":
            self.udp("RESET")
            self.resume()
        else:
            try:
                os.makedirs(os.path.dirname(self.restart_flag), exist_ok=True)
                open(self.restart_flag, "w").close()
            except OSError as e:
                log("cannot write the restart flag: %r" % e)
            self.terminate()

    def exit(self):
        if self.kind == "retroarch":
            self.resume()
            self.udp("QUIT")
            self._reap(retroarch=True)
        else:
            self.terminate()

    def terminate(self):
        self._signal(signal.SIGCONT)
        self._signal(signal.SIGTERM)
        self.we_paused = False
        self._reap()

    def _reap(self, retroarch=False):
        """SIGKILL whatever is still there after the grace period."""
        def run():
            end = self.clock() + GRACE_S
            while self.alive() and self.clock() < end:
                self.sleep(0.1)
            if self.alive():
                log("game ignored the stop request; killing it")
                if retroarch:
                    for pid in self.pids(("retroarch",)):
                        try:
                            self.kill(pid, signal.SIGKILL)
                        except OSError:
                            pass
                else:
                    self._signal(signal.SIGKILL)
        if self.reaper:
            threading.Thread(target=run, daemon=True).start()
        else:
            run()


# ---- one open/close cycle ------------------------------------------------------------------------------------------

class RetroArchMenu:
    """Fallback in-game menu for RetroArch: its own menu (RGUI), opened and closed with the MENU_TOGGLE command.

    Used when the RG OS panel cannot go on an overlay plane (or RGOS_GAMEMENU_RGUI=1): a panel painted into /dev/fb0 is
    never visible over a DRM/KMS game. RGUI is drawn by RetroArch itself (above the picture, game paused) and has Resume /
    Save State / Load State / Restart / Close Content in its Quick Menu. The pad is not grabbed, so RetroArch reads it.
    """

    def __init__(self, udp=udp_cmd):
        self.udp, self.open = udp, False

    def toggle(self):
        self.udp("MENU_TOGGLE")
        self.open = not self.open
        return self.open

    def reset(self):
        self.open = False


class MenuSession:
    """Slide in, handle input, slide out, then act. `screen` needs: rw rh s canvas theme() open() draw(layer, x)
    repainted() rebase() close(). `read_events(dt)` returns menu input names (blocking up to dt)."""

    def __init__(self, screen, control, model, read_events, clock=time.monotonic, sleep=time.sleep, alive=None):
        self.screen, self.control, self.model = screen, control, model
        self.read_events, self.clock, self.sleep = read_events, clock, sleep
        self.alive = alive or (lambda: True)

    def frame(self, slide, stagger):
        sc = self.screen
        ops = layout(self.model, sc.rw, sc.rh, sc.s, sc.theme(), sc.canvas.measure, stagger, self.clock())
        sc.draw(sc.canvas.render(ops, sc.rw, sc.rh), sc.rw - int(round(sc.rw * slide)))

    def animate(self, opening):
        t0 = self.clock()
        while True:
            p = clamp((self.clock() - t0) / SLIDE_S)
            pos = open_curve(p) if opening else close_curve(p)
            self.frame(pos, pos if opening else 1.0)
            if p >= 1.0:
                return
            self.sleep(1.0 / FPS)

    def interact(self):
        dirty, last = False, self.clock()
        while True:
            if not self.alive():
                return "gone"
            for name in self.read_events(1.0 / FPS):
                act = self.model.press(name)
                dirty = True
                if act in ("resume", "restart", "exit", "load"):
                    return act
                if act == "save":
                    self.model.say(self.control.save(), self.clock() + 1.6)
            now = self.clock()
            if self.model.status and now >= self.model.status_until:
                self.model.status, dirty = "", True
            if dirty:
                self.frame(1.0, 1.0)
                dirty = False
            elif now - last > 0.15:
                last = now
                if self.screen.repainted():       # the program painted over us (a paused RetroArch redraws now and then)
                    self.screen.rebase()
                    dirty = True

    def run(self):
        self.control.pause()
        self.sleep(0.08)                          # let the frame the game was drawing finish
        self.screen.open()
        result = "resume"
        try:
            self.animate(True)
            self.frame(1.0, 1.0)
            result = self.interact()
            if result != "gone":
                self.animate(False)
        finally:
            self.screen.close()
            if result != "gone":
                self.control.perform(result)
            else:
                self.control.resume()
        return result


# ---- the real framebuffer (reuses rgos-overlay's framebuffer access) -----------------------------------------------

def load_overlay():
    loader = importlib.machinery.SourceFileLoader("rgos_overlay", os.path.join(HERE, "rgos-overlay"))
    spec = importlib.util.spec_from_loader("rgos_overlay", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class FbMenuScreen:
    def __init__(self, ov=None):
        self.ov = ov or load_overlay()
        fb = self.fb = self.ov.FbScreen()
        self.s = fb.scale
        self.rw = int(PANEL_W * self.s) + int(SHADOW * self.s)
        self.rh = fb.lh
        fb.rect = self.ov.to_fb_rect((fb.lw - self.rw, 0, self.rw, fb.lh), fb.lw, fb.lh, fb.rotate)
        self.canvas = PygameCanvas(fb.pg)
        self.saved = self.drawn = self.key = self.base = None

    def theme(self):
        return self.ov.read_theme()

    def _size(self):
        return (self.rh, self.rw) if self.fb.rotate in (90, 270) else (self.rw, self.rh)

    def _rebuild(self):
        w, h = self._size()
        sf = self.fb._surface_from(self.saved, w, h)
        self.base = self.fb.pg.transform.rotate(sf, self.fb.rotate) if self.fb.rotate else sf

    def open(self):
        self.saved, self.key, self.drawn = self.fb.read(), self.fb.position(), None
        self._rebuild()

    def draw(self, layer, x):
        pg, fb = self.fb.pg, self.fb
        frame = self.base.copy()
        frame.blit(layer, (x, 0))
        out = pg.transform.rotate(frame, -fb.rotate) if fb.rotate else frame
        w, h = self._size()
        self.drawn = fb._rows_of(out, w, h)
        fb.write(self.drawn)

    def repainted(self):
        return self.drawn is not None and (self.fb.position() != self.key or self.fb.read() != self.drawn)

    def rebase(self):
        self.saved, self.key = self.fb.read(), self.fb.position()
        self._rebuild()

    def close(self):
        try:
            if self.saved is not None and self.drawn is not None:
                self.fb.write(self.saved)
        except OSError as e:
            log("restore failed: %r" % e)
        self.saved = self.drawn = self.base = None


class DrmMenuScreen(FbMenuScreen):
    """Same panel, but on a hardware overlay plane: it is composited above a DRM/KMS game, which /dev/fb0 never is."""

    def __init__(self, ov=None):
        super().__init__(ov)
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import drmplane
        self.drm = drmplane.DrmOverlay()
        self.rect = self.fb.rect                      # panel rectangle in panel pixels (set by FbMenuScreen)

    def open(self):
        pass

    def draw(self, layer, x):
        pg, fb = self.fb.pg, self.fb
        frame = pg.Surface(layer.get_size(), pg.SRCALPHA, 32)
        frame.blit(layer, (x, 0))
        if self.drm.premultiplied() and hasattr(frame, "premul_alpha"):
            frame = frame.premul_alpha()
        if fb.rotate:
            frame = pg.transform.rotate(frame, -fb.rotate)
        self.drm.show(self.rect, pg.image.tostring(frame, "BGRA"))

    def repainted(self):
        return False

    def rebase(self):
        pass

    def close(self):
        self.drm.close()
        try:
            os.close(self.fb.fd)
        except OSError:
            pass


class NoPlane(Exception):
    """RetroArch needs an overlay plane for the panel; there is none (the framebuffer would be behind the game)."""


def make_screen(kind):
    """Games render through DRM/KMS: put the panel on an overlay plane above them. A native port may fall back to the
    framebuffer if that is not possible; RetroArch may not (it would not be seen), so NoPlane is raised for it."""
    if os.environ.get("RGOS_GAMEMENU_DRM", "1") != "0":
        try:
            return DrmMenuScreen()
        except Exception as e:
            log("overlay plane not available (%r)" % e)
    if kind == "retroarch":
        raise NoPlane("no overlay plane")
    return FbMenuScreen()


def use_rgui(kind, plane_bad):
    """True when a Menu tap should open RetroArch's own menu instead of the RG OS panel."""
    return kind == "retroarch" and (plane_bad or bool(os.environ.get("RGOS_GAMEMENU_RGUI")))


# ---- daemon --------------------------------------------------------------------------------------------------------

def open_pads():
    import portexit
    return portexit.open_events(portexit.find_pad_events(SYS_INPUT, DEV_INPUT, HUB_NAME))


def read_pad(fd):
    """Raw bytes from one pad fd: b"" when nothing is pending, None when the device is gone.

    A removed evdev node (the input hub restarted) stays readable forever: read() raises ENODEV,
    or returns EOF. Treating that as "nothing yet" made the daemon spin on select() at 100% CPU
    and never reopen the pad, so the Menu button stayed dead until the game ended.
    """
    try:
        data = os.read(fd, EVFMT.size * 64)
    except BlockingIOError:
        return b""
    except OSError:
        return None
    return data if data else None


class PadEvents:
    def __init__(self, fds):
        self.fds = fds
        self.ydir = 0

    def grab(self, on):
        for fd in self.fds:
            try:
                fcntl.ioctl(fd, EVIOCGRAB, 1 if on else 0)
            except OSError as e:
                log("pad grab %s failed: %r" % ("on" if on else "off", e))

    def read(self, dt):
        names = []
        try:
            ready, _, _ = select.select(self.fds, [], [], dt)
        except (OSError, ValueError):
            time.sleep(dt)
            return names
        for fd in ready:
            data = read_pad(fd)
            if data is None:                      # pad vanished while the menu is open
                try:
                    os.close(fd)
                except OSError:
                    pass
                self.fds.remove(fd)               # in place: the daemon shares this list and will reopen the hub
                continue
            for etype, code, value in parse_events(data):
                if etype == EV_ABS and code == ABS_Y:
                    # D-pad presses arrive as left-stick Y while DPAD to joystick is on: one step per push
                    d = -1 if value < -STICK_ON else (1 if value > STICK_ON else 0)
                    if d != self.ydir:
                        self.ydir = d
                        if d:
                            names.append("up" if d < 0 else "down")
                    continue
                n = translate(etype, code, value)
                if n:
                    names.append(n)
        if not self.fds:
            # No pad left means no way to close the menu: the game would stay paused behind it. "close" twice
            # backs out of a confirm step, then resumes.
            return ["close", "close"]
        return names


def open_menu(info, pads, screen):
    control = GameControl(info, alive=lambda: read_game() is not None)
    model = MenuModel(control.kind, info.get("title", ""))
    pe = PadEvents(pads)
    pe.grab(True)
    pe.read(0)                                    # drop what was buffered before the grab
    session = MenuSession(screen, control, model, pe.read, alive=lambda: read_game() is not None)
    try:
        log("menu open (%s: %s)" % (control.kind, model.title))
        log("menu closed: %s" % session.run())
    except Exception:
        control.resume()
        raise
    finally:
        pe.grab(False)


def daemon():
    log("in-game menu started")
    pads, screen, tap, ra_menu, plane_bad = [], None, TapDetector(), RetroArchMenu(), False
    while True:
        info = read_game()
        if info is None:
            for fd in pads:
                try:
                    os.close(fd)
                except OSError:
                    pass
            pads = []
            ra_menu.reset()
            plane_bad = False                     # try the plane again for the next game
            time.sleep(0.5)
            continue
        if not pads:
            pads = open_pads()
            if not pads:
                time.sleep(1.0)
                continue
        try:
            ready, _, _ = select.select(pads, [], [], 0.5)
        except (OSError, ValueError):
            pads = []
            continue
        for fd in ready:
            data = read_pad(fd)
            if data is None:                      # pad vanished: drop it so the next pass reopens the hub
                try:
                    os.close(fd)
                except OSError:
                    pass
                pads = [f for f in pads if f != fd]
                continue
            for etype, code, value in parse_events(data):
                if tap.feed(etype, code, value, time.monotonic()) and not combo_recent():
                    if use_rgui(info.get("kind"), plane_bad):
                        log("retroarch menu %s" % ("opened" if ra_menu.toggle() else "closed"))
                        break
                    try:
                        screen = screen or make_screen(info.get("kind"))
                        open_menu(info, pads, screen)
                        screen = None             # the plane is released after every menu; open it fresh next time
                    except NoPlane:
                        plane_bad = True          # no plane for RetroArch: this tap (and the rest of the game) opens RGUI
                        screen = None
                        log("retroarch menu %s (no overlay plane)" % ("opened" if ra_menu.toggle() else "closed"))
                    except Exception as e:
                        log("menu error: %r" % e)
                        screen = None
                        time.sleep(1.0)
                    break


def main(argv):
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        sys.stdout.write(__doc__)
        return 0
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sys.path.insert(0, HERE)
    daemon()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
