"""Select+Start hold to quit a native Linux port.

Native ports are started with no RetroArch around them, so a hung or menu-less port would
otherwise trap the user until the power button. While a port runs, a watcher reads the hub
pad ("RG OS Gamepad") without grabbing it, and if Select and Start stay down together for
HOLD_S seconds it stops the port's whole process group: SIGTERM first, SIGKILL after GRACE_S.
"""
import glob, os, select, signal, struct, threading, time

HUB_NAME = "RG OS Gamepad"
EVFMT = struct.Struct("llHHi")
EV_KEY = 1
BTN_SELECT, BTN_START = 0x13A, 0x13B
HOLD_S = 2.0
GRACE_S = 3.0


def find_pad_events(sys_input="/sys/class/input", dev_input="/dev/input", name=HUB_NAME):
    out = []
    for d in sorted(glob.glob(os.path.join(sys_input, "event[0-9]*"))):
        try:
            with open(os.path.join(d, "device", "name")) as f:
                if f.read().strip() != name:
                    continue
        except OSError:
            continue
        out.append(os.path.join(dev_input, os.path.basename(d)))
    return out


def open_events(paths):
    fds = []
    for p in paths:
        try:
            fds.append(os.open(p, os.O_RDONLY | os.O_NONBLOCK))
        except OSError:
            pass
    return fds


class ExitWatcher(threading.Thread):
    """Owns (and closes) fds; stops the process group pgid when the combo is held. alive() says if it still runs."""

    def __init__(self, fds, pgid, alive, hold=HOLD_S, grace=GRACE_S, clock=time.monotonic, log=None):
        super().__init__(daemon=True)
        self.fds, self.pgid, self.alive = list(fds), pgid, alive
        self.hold, self.grace, self.clock = hold, grace, clock
        self.log = log or (lambda *a: None)
        self.fired = False
        self._stop_evt = threading.Event()

    def stop(self):
        self._stop_evt.set()

    def _killpg(self, sig):
        try:
            os.killpg(self.pgid, sig)
        except OSError:
            pass

    def _terminate(self):
        self.fired = True
        self.log("Select+Start held: stopping the port")
        self._killpg(signal.SIGTERM)
        deadline = self.clock() + self.grace
        while self.alive() and self.clock() < deadline:
            time.sleep(0.05)
        if self.alive():
            self.log("port ignored SIGTERM; sending SIGKILL")
        self._killpg(signal.SIGKILL)

    def run(self):
        down, since = set(), None
        try:
            while not self._stop_evt.is_set() and self.fds:
                try:
                    ready, _, _ = select.select(self.fds, [], [], 0.1 if down >= {BTN_SELECT, BTN_START} else 0.5)
                except (OSError, ValueError):
                    break
                for fd in ready:
                    try:
                        data = os.read(fd, EVFMT.size * 64)
                    except BlockingIOError:
                        continue
                    except OSError:
                        data = b""
                    if not data:
                        self.fds.remove(fd)
                        os.close(fd)
                        continue
                    for off in range(0, len(data) - EVFMT.size + 1, EVFMT.size):
                        _, _, etype, code, value = EVFMT.unpack_from(data, off)
                        if etype == EV_KEY and code in (BTN_SELECT, BTN_START):
                            (down.add if value else down.discard)(code)
                if down >= {BTN_SELECT, BTN_START}:
                    since = since if since is not None else self.clock()
                    if self.clock() - since >= self.hold:
                        self._terminate()
                        return
                else:
                    since = None
        finally:
            for fd in self.fds:
                try:
                    os.close(fd)
                except OSError:
                    pass
            self.fds = []
