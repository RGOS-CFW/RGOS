"""Keep the CPU and GPU clocks up while the launcher is being used.

The launcher is a single-threaded software renderer. On the default governor the clocks sit low while nothing happens and
only ramp up after the first slow frames of a scroll, which is felt as the first moves of every scroll stuttering. While
the person is interacting (and for a few seconds afterwards) the governors are switched to `performance`; once the
launcher has been idle for a while the previous governors are put back, so an idle launcher costs no extra battery.

Everything is best effort: a missing or read-only node, or a governor that does not exist, is skipped silently.
RGOS_UI_BOOST=0 turns it off. The original governors are always restored before the launcher exits (a game launch
records the current governors to restore them after the game, so leaving `performance` behind would stick).
"""
import glob
import os
import time

SYS_ROOT = os.environ.get("RGOS_SYSFS", "/sys")
HOLD_S = 4.0  # stay boosted this long after the last input


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def nodes(root=None):
    root = root or SYS_ROOT
    return sorted(glob.glob(os.path.join(root, "devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor"))
                  + glob.glob(os.path.join(root, "class/devfreq/*/governor")))


class UiBoost:
    def __init__(self, enabled=None, root=None, hold=HOLD_S, clock=time.monotonic):
        if enabled is None:
            enabled = os.environ.get("RGOS_UI_BOOST", "1") != "0" and os.environ.get("RGOS_WINDOWED") != "1"
        self.enabled, self.root, self.hold, self.clock = enabled, root, hold, clock
        self.saved = {}      # node -> governor to put back
        self.until = 0.0
        self.nodes = None    # discovered on first use

    @property
    def active(self):
        return bool(self.saved)

    def _discover(self):
        out = []
        for node in nodes(self.root):
            d, base = os.path.split(node)
            avail = _read(os.path.join(d, "scaling_available_governors" if base == "scaling_governor" else "available_governors"))
            if "performance" in avail.split() and os.access(node, os.W_OK):
                out.append(node)
        return out

    def poke(self):
        """Call on input / animation. Switches the governors to performance if they are not already."""
        if not self.enabled:
            return
        self.until = self.clock() + self.hold
        if self.saved:
            return
        if self.nodes is None:
            self.nodes = self._discover()
        for node in self.nodes:
            prev = _read(node)
            if not prev or prev == "performance":
                continue
            try:
                with open(node, "w") as f:
                    f.write("performance")
                self.saved[node] = prev
            except OSError:
                continue

    def tick(self):
        """Call once per frame: puts the governors back once the hold time has passed."""
        if self.saved and self.clock() >= self.until:
            self.restore()

    def restore(self):
        saved, self.saved = self.saved, {}
        for node, prev in saved.items():
            try:
                with open(node, "w") as f:
                    f.write(prev)
            except OSError:
                pass
