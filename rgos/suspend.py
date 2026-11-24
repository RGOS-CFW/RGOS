"""Power button: short press suspends, next short press resumes.

Real suspend ("mem") is used when the kernel offers it and the power key can wake the SoC.
Otherwise a soft sleep runs: screen off, radios and LEDs off, CPU at minimum, game frozen,
input swallowed, until the next power press. Override in hw json: {"suspend": {"mode": "auto|mem|soft"}}.
"""
import fcntl, glob, os, signal, struct, time

import hwctl

KEY_POWER = 116
EVFMT = struct.Struct("llHHi")
EVIOCGBIT_KEY = (2 << 30) | (96 << 16) | (ord("E") << 8) | (0x20 + 1)
WAKE_GUARD_S = 1.0          # presses this soon after a resume are the wake press itself, not a new sleep


class PowerKeys:
    def __init__(self, sys_root="/sys", dev_root="/dev/input"):
        self.sys, self.dev = sys_root, dev_root
        self.fds = {}       # fd -> sysfs path of the event node

    def scan(self):
        for p in sorted(glob.glob(os.path.join(self.sys, "class/input/event*"))):
            path = os.path.join(self.dev, os.path.basename(p))
            if path in self.fds.values():
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            except OSError:
                continue
            try:
                buf = bytearray(96)
                fcntl.ioctl(fd, EVIOCGBIT_KEY, buf)
                has = buf[KEY_POWER >> 3] >> (KEY_POWER & 7) & 1
            except OSError:
                has = 0
            if has:
                self.fds[fd] = (path, p)
            else:
                os.close(fd)

    def poll(self, ready):
        """True when a power key press (value 1) is in the events of the ready fds."""
        pressed = False
        for fd in list(self.fds):
            if fd not in ready:
                continue
            try:
                data = os.read(fd, EVFMT.size * 32)
            except BlockingIOError:
                continue
            except OSError:
                os.close(fd)
                del self.fds[fd]
                continue
            for off in range(0, len(data) - EVFMT.size + 1, EVFMT.size):
                _, _, t, c, v = EVFMT.unpack_from(data, off)
                if t == 1 and c == KEY_POWER and v == 1:
                    pressed = True
        return pressed

    def can_wake(self):
        """True if the power key's device chain is a wakeup source (gpio-keys wakeup-source)."""
        for _, sysnode in self.fds.values():
            d = os.path.realpath(os.path.join(sysnode, "device"))
            for _ in range(6):
                if hwctl.rd(os.path.join(d, "power/wakeup")) == "enabled":
                    return True
                d = os.path.dirname(d)
        return False

    def close(self):
        for fd in self.fds:
            try:
                os.close(fd)
            except OSError:
                pass
        self.fds = {}


class SleepManager:
    def __init__(self, conf=None, sys_root="/sys", run_dir="/run/rgos", power_keys=None):
        c = (conf or {}).get("suspend", {}) if isinstance(conf, dict) else {}
        self.mode = c.get("mode", "auto") if isinstance(c, dict) else "auto"
        self.sys = sys_root
        self.lp = hwctl.LowPower(conf, sys_root, run_dir)
        self.bl = hwctl.Backlight(conf, sys_root)
        self.keys = power_keys
        self.game_flag = os.path.join(run_dir, "ingame")
        self.asleep = False
        self.guard_until = 0.0
        self.saved_bl = None
        self.frozen = None

    def _state(self):
        return os.path.join(self.sys, "power/state")

    def real_suspend_ok(self):
        if self.mode == "soft" or "mem" not in hwctl.rd(self._state()).split():
            return False
        return self.mode == "mem" or bool(self.keys and self.keys.can_wake())

    def _freeze_game(self, sig):
        try:
            if sig == signal.SIGSTOP:
                pid = int(hwctl.rd(self.game_flag) or 0)
                if pid > 1:
                    os.kill(pid, sig)
                    self.frozen = pid
            elif self.frozen:
                os.kill(self.frozen, sig)
                self.frozen = None
        except (OSError, ValueError):
            self.frozen = None

    def toggle(self, now=None):
        now = time.monotonic() if now is None else now
        if now < self.guard_until:
            return "ignored"
        return self.wake(now) if self.asleep else self.sleep(now)

    def sleep(self, now=None):
        self.asleep = True
        self.saved_bl = self.bl.get() if self.bl.available else None
        self._freeze_game(signal.SIGSTOP)
        self.lp.enter(full=False)
        if self.bl.available:
            self.bl.set(0)
        try:
            os.sync()
        except OSError:
            pass
        if self.real_suspend_ok():
            self.lp.prefer_deep_sleep()
            if hwctl.wr(self._state(), "mem"):          # blocks until the wake press; returns on resume
                return self.wake(time.monotonic())
        self.lp.enter(full=True)
        return "soft"

    def wake(self, now=None):
        self.lp.leave()
        if self.bl.available:
            self.bl.set(self.saved_bl or 100)
        self._freeze_game(signal.SIGCONT)
        self.asleep = False
        self.guard_until = (time.monotonic() if now is None else now) + WAKE_GUARD_S
        return "awake"
