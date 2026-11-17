import glob, json, os, re, subprocess, time

DEVFILE = "/etc/rgos-device"
USER_CONF = "/var/lib/rgos/hw.json"
SYSFS_GPIO = "/sys/class/gpio"


def device():
    try:
        return open(DEVFILE).read().strip() or "rg-rotate"
    except OSError:
        return "rg-rotate"


def _merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_conf(path=None, user=USER_CONF):
    path = path or "/etc/rgos/hw-%s.json" % device()
    try:
        with open(path) as f:
            conf = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(conf, dict):
        return None
    try:
        with open(user) as f:
            u = json.load(f)
        if isinstance(u, dict):
            conf = _merge(conf, u)
    except (OSError, ValueError):
        pass
    return conf if isinstance(conf, dict) else None


def rd(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def wr(path, text):
    try:
        with open(path, "w") as f:
            f.write(str(text))
        return True
    except OSError:
        return False


def write_run(path, text):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w") as f:
            f.write(text)
        os.replace(path + ".tmp", path)
    except OSError:
        pass



class LowPower:
    DEFAULTS = {"enabled": True, "radios_off": True, "leds_off": True, "cpu_min": True, "offline_cpus": True,
                "devfreq_min": True}
    ORDER = ("offline", "cpu", "devfreq", "led", "radio")

    def __init__(self, conf=None, sys_root="/sys", run_dir="/run/rgos"):
        self.c = dict(self.DEFAULTS)
        extra = (conf or {}).get("low_power", {}) if isinstance(conf, dict) else {}
        if isinstance(extra, dict):
            self.c.update({k: bool(v) for k, v in extra.items() if k in self.DEFAULTS})
        self.sys, self.run_dir = sys_root, run_dir
        self.flag = os.path.join(run_dir, "sleeping")
        self.saved_file = os.path.join(run_dir, "lowpower.json")
        self.saved = {k: [] for k in self.ORDER}
        self.stage = 0

    def _p(self, *parts):
        return os.path.join(self.sys, *parts)

    def _set(self, category, path, value):
        old = rd(path, None)
        if old is None or old == str(value):
            return False
        if not wr(path, value):
            return False
        self.saved[category].append([path, old])
        return True

    def _persist(self):
        write_run(self.saved_file, json.dumps({"stage": self.stage, "saved": self.saved}))

    def _light(self):
        if self.c["radios_off"]:
            for d in sorted(glob.glob(self._p("class/rfkill/rfkill*"))):
                if rd(os.path.join(d, "type")) in ("wlan", "bluetooth"):
                    self._set("radio", os.path.join(d, "soft"), 1)
            write_run(self.flag, "1")
        if self.c["leds_off"]:
            for d in sorted(glob.glob(self._p("class/leds/*"))):
                if rd(os.path.join(d, "brightness")) not in ("", "0"):
                    self._set("led", os.path.join(d, "brightness"), 0)

    def _deep(self):
        if self.c["cpu_min"]:
            for d in sorted(glob.glob(self._p("devices/system/cpu/cpu[0-9]*/cpufreq"))):
                if "powersave" in rd(os.path.join(d, "scaling_available_governors")).split():
                    self._set("cpu", os.path.join(d, "scaling_governor"), "powersave")
                lowest = rd(os.path.join(d, "cpuinfo_min_freq"))
                if lowest.isdigit():
                    self._set("cpu", os.path.join(d, "scaling_max_freq"), lowest)
        if self.c["devfreq_min"]:
            for d in sorted(glob.glob(self._p("class/devfreq/*"))):
                if "powersave" in rd(os.path.join(d, "available_governors")).split():
                    self._set("devfreq", os.path.join(d, "governor"), "powersave")
        if self.c["offline_cpus"]:
            def cpu_no(d):
                tail = os.path.basename(d)[3:]
                return int(tail) if tail.isdigit() else -1
            for d in sorted(glob.glob(self._p("devices/system/cpu/cpu[0-9]*")), key=cpu_no):
                if cpu_no(d) >= 1:
                    self._set("offline", os.path.join(d, "online"), 0)

    def enter(self, full=False):
        if not self.c["enabled"]:
            return
        target = 2 if full else 1
        if self.stage < 1:
            self._light()
            self.stage = 1
        if target >= 2 and self.stage < 2:
            self._deep()
            self.stage = 2
        self._persist()

    def leave(self):
        for cat in self.ORDER:
            for path, old in reversed(self.saved[cat]):
                wr(path, old)
            self.saved[cat] = []
        for p in (self.flag, self.saved_file, self.saved_file + ".tmp"):
            try:
                os.unlink(p)
            except OSError:
                pass
        self.stage = 0

    def restore_stale(self):
        try:
            with open(self.saved_file) as f:
                data = json.load(f)
            saved = data.get("saved", {})
            for cat in self.ORDER:
                self.saved[cat] = [list(x) for x in saved.get(cat, []) if isinstance(x, list) and len(x) == 2]
        except (OSError, ValueError, AttributeError):
            pass
        self.leave()

    def prefer_deep_sleep(self):
        path = self._p("power/mem_sleep")
        states = rd(path).split()
        if "deep" in states and "[deep]" not in states:
            return wr(path, "deep")
        return False


class Backlight:
    DISPDBG = "/sys/kernel/debug/dispdbg"

    def __init__(self, conf=None, sys_root="/sys"):
        c = (conf or {}).get("backlight", {}) if conf else {}
        self.min_pct = int(c.get("min_pct", 5))
        self.gamma = float(c.get("gamma", 1.0))
        self.sys_root = sys_root
        self.kind = self.node = None
        self.max = 255
        self.cur = None
        want = c.get("backend", "auto")
        if c.get("path"):
            self._use_sysfs(c["path"])
        elif want in ("auto", "sysfs"):
            cands = sorted(glob.glob(os.path.join(sys_root, "class/backlight/*")),
                           key=lambda p: ("acpi" in p, "panel" not in p and "backlight" not in os.path.basename(p), p))
            for p in cands:
                if os.access(os.path.join(p, "brightness"), os.W_OK) and rd(os.path.join(p, "max_brightness")).isdigit():
                    self._use_sysfs(p)
                    break
        if not self.kind and want in ("auto", "dispdbg"):
            d = self.DISPDBG if sys_root == "/sys" else os.path.join(sys_root, "kernel/debug/dispdbg")
            if os.path.exists(os.path.join(d, "command")):
                self.kind, self.node, self.max = "dispdbg", d, int(c.get("dispdbg_max", 255))

    def _use_sysfs(self, p):
        mx = rd(os.path.join(p, "max_brightness"))
        self.kind, self.node = "sysfs", p
        self.max = int(mx) if mx.isdigit() and int(mx) > 0 else 255

    @property
    def available(self):
        return self.kind is not None

    def describe(self):
        return "none" if not self.kind else "%s %s (max %d)" % (self.kind, self.node, self.max)

    def _raw(self, pct):
        pct = max(0, min(100, pct))
        if pct == 0:
            return 0
        return max(1, int(round(self.max * ((pct / 100.0) ** self.gamma))))

    def _pct(self, raw):
        if raw <= 0:
            return 0
        return max(1, min(100, int(round(100.0 * ((raw / float(self.max)) ** (1.0 / self.gamma))))))

    def get(self):
        if self.kind == "sysfs":
            v = rd(os.path.join(self.node, "brightness"))
            return self._pct(int(v)) if v.isdigit() else None
        if self.kind == "dispdbg":
            return self._pct(self.cur) if self.cur is not None else None
        return None

    def set(self, pct):
        if not self.kind:
            return False
        pct = 0 if pct <= 0 else max(self.min_pct, min(100, int(pct)))
        raw = self._raw(pct)
        if self.kind == "sysfs":
            ok = wr(os.path.join(self.node, "brightness"), raw)
        else:
            ok = (wr(os.path.join(self.node, "name"), "lcd0") and wr(os.path.join(self.node, "command"), "setbl")
                  and wr(os.path.join(self.node, "param"), raw) and wr(os.path.join(self.node, "start"), 1))
        if ok:
            self.cur = raw
        return ok


class Battery:
    def __init__(self, conf=None, sys_root="/sys"):
        c = (conf or {}).get("battery", {}) if conf else {}
        self.vmin = float(c.get("empty_v", 3.3))
        self.vmax = float(c.get("full_v", 4.15))
        self.node = None
        base = os.path.join(sys_root, "class/power_supply")
        want = c.get("supply", "auto")
        cands = sorted(glob.glob(os.path.join(base, "*")))
        if want != "auto":
            cands = [p for p in cands if os.path.basename(p) == want] or cands
        batt = [p for p in cands if rd(os.path.join(p, "type")).lower() == "battery"]
        batt.sort(key=lambda p: "batt" not in os.path.basename(p).lower())
        if batt:
            self.node = batt[0]

    @property
    def available(self):
        return self.node is not None

    def read(self):
        if not self.node:
            return None
        cap, est = rd(os.path.join(self.node, "capacity")), False
        pct = int(cap) if cap.lstrip("-").isdigit() else None
        if pct is None:
            uv = rd(os.path.join(self.node, "voltage_now"))
            if uv.isdigit():
                v = int(uv) / 1e6
                pct, est = int(round(100 * (v - self.vmin) / (self.vmax - self.vmin))), True
        if pct is None:
            return None
        pct = max(0, min(100, pct))
        status = rd(os.path.join(self.node, "status"), "Unknown")
        st = status.lower()
        return {"pct": pct, "status": status, "estimated": est, "charging": st == "charging",
                "plugged": st in ("charging", "full", "not charging"), "discharging": st == "discharging"}


def _run(args, timeout=5):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def audio_card(cards_text=None):
    text = cards_text if cards_text is not None else rd("/proc/asound/cards")
    cards = re.findall(r"^\s*(\d+)\s+\[([^\]]*)\]\s*:\s*(.*)$", text, re.M)
    for idx, cid, desc in cards:
        if not re.search(r"hdmi|spdif|dummy|loopback", cid + " " + desc, re.I):
            return int(idx)
    return int(cards[0][0]) if cards else 0


def audio_pcm(card, proc="/proc/asound"):
    devs = []
    for d in glob.glob(os.path.join(proc, "card%d" % card, "pcm*p")):
        m = re.search(r"pcm(\d+)p$", d)
        if m:
            devs.append(int(m.group(1)))
    return min(devs) if devs else 0


OUTPUT_RE = re.compile(r"speaker|spk|lineout|line out|headphone|headset|\bhp\b|master|playback|digital|pa\b|amp", re.I)


def audio_enable(card, extra=()):
    names = re.findall(r"Simple mixer control '([^']+)',0", _run(["amixer", "-c", str(card), "scontrols"]))
    done = []
    for n in names:
        if "capture" in n.lower() or "mic" in n.lower() or "adc" in n.lower():
            continue
        if not (OUTPUT_RE.search(n) or n in extra):
            continue
        if "pswitch" in _run(["amixer", "-c", str(card), "sget", n]).lower():
            _run(["amixer", "-c", str(card), "-q", "sset", n, "unmute"])
            done.append(n)
    return done


AUDIO_DIR = "/etc/rgos/audio"

RAW_ON_RE = re.compile(r"speaker|spk|ear|headphone|headset|\bhp[lr]?\b|line ?out|\bpa\b|\bamp\b|\bdac\b|playback|output|\bout\b", re.I)
RAW_SKIP_RE = re.compile(r"capture|record|mic|adc|\bin\b|input|loop|bypass|sidetone|test|debug|voice|call|\bbt\b|bluetooth|\bfm\b|mute all", re.I)


def audio_enable_raw(card, run=None):
    run = run or _run
    out, done, cur = run(["amixer", "-c", str(card), "contents"]) or "", [], None
    for line in out.splitlines():
        m = re.match(r"\s*numid=(\d+),iface=\w+,name='([^']*)'", line)
        if m:
            cur = (m.group(1), m.group(2))
            continue
        if cur and re.search(r"type=BOOLEAN,access=\S*w", line):
            numid, name = cur
            cur = None
            if RAW_SKIP_RE.search(name) or not RAW_ON_RE.search(name):
                continue
            if re.search(r"mute$", name.strip(), re.I):
                val = "off"
            elif re.search(r"(switch|enable|on)$", name.strip(), re.I):
                val = "on"
            else:
                continue
            run(["amixer", "-c", str(card), "-q", "cset", "numid=" + numid, val])
            done.append("%s=%s" % (name, val))
    return done


def _audio_init_lines(path, user_conf):
    import shlex
    lines = []
    try:
        with open(path) as f:
            lines += [l.strip() for l in f]
    except OSError:
        pass
    try:
        with open(user_conf) as f:
            extra = (json.load(f).get("audio") or {}).get("init") or []
        if isinstance(extra, list):
            lines += [x for x in extra if isinstance(x, str)]
    except (OSError, ValueError, AttributeError):
        pass
    out = []
    for l in lines:
        if l and not l.startswith("#"):
            try:
                args = shlex.split(l)
            except ValueError:
                continue
            if args:
                out.append(args)
    return out


def audio_prepare(card, audio_dir=AUDIO_DIR, user_conf=USER_CONF, run=None):
    run = run or _run
    log = []
    state = os.path.join(audio_dir, "asound.state")
    if os.path.isfile(state) and os.path.getsize(state) > 0:
        run(["alsactl", "-f", state, "restore", str(card)])
        log.append("restored mixer state %s on card %d" % (state, card))
    for args in _audio_init_lines(os.path.join(audio_dir, "init.txt"), user_conf):
        run(["amixer", "-c", str(card), "-q"] + args)
        log.append("amixer %s" % " ".join(args))
    try:
        if "DSP VBC Profile Select" in (run(["amixer", "-c", str(card), "controls"]) or ""):
            run(["amixer", "-c", str(card), "-q", "cset", "name=DSP VBC Profile Select", "961216512"])
            log.append("amixer cset name='DSP VBC Profile Select' 961216512")
    except Exception as e:
        log.append("VBC profile select failed: %r" % e)
    try:
        raw = audio_enable_raw(card, run)
        log.append("output switches set by name (no stock mixer state / init.txt needed): %s" % (", ".join(raw) or "none found"))
    except Exception as e:
        log.append("audio_enable_raw failed: %r" % e)
    return log


class Motor:
    def __init__(self, conf=None, sys_root="/sys", gpio_root=None):
        c = (conf or {}).get("rumble", {}) if conf else {}
        self.gpio_root = gpio_root or os.path.join(sys_root, "class/gpio")
        self.active_low = bool(c.get("active_low", False))
        self.mode, self.path, self.state = "none", None, False
        want = c.get("mode", "auto")
        gpio = c.get("gpio")
        timed = os.path.join(sys_root, "class/timed_output/vibrator/enable")
        leds = [p for p in glob.glob(os.path.join(sys_root, "class/leds/*"))
                if re.search(r"vibr|motor|rumble", os.path.basename(p), re.I) and os.path.exists(p + "/brightness")]
        if want in ("auto", "gpio") and gpio is not None and gpio is not False and gpio != "":
            self.mode, self.path = "gpio", int(gpio)
            self._gpio_prepare()
        elif want in ("auto", "timed") and os.path.exists(timed):
            self.mode, self.path = "timed", timed
        elif want in ("auto", "led") and leds:
            self.mode, self.path = "led", leds[0] + "/brightness"
        if self.mode == "gpio" and not self.path_ok():
            self.mode, self.path = "none", None

    def path_ok(self):
        return os.path.exists(os.path.join(self.gpio_root, "gpio%d" % self.path, "value"))

    def _gpio_prepare(self):
        d = os.path.join(self.gpio_root, "gpio%d" % self.path)
        if not os.path.exists(d):
            wr(os.path.join(self.gpio_root, "export"), self.path)
        wr(os.path.join(d, "direction"), "high" if self.active_low else "low")

    @property
    def available(self):
        return self.mode != "none"

    def set(self, on):
        on = bool(on)
        if self.mode == "gpio":
            wr(os.path.join(self.gpio_root, "gpio%d" % self.path, "value"), 1 if on != self.active_low else 0)
        elif self.mode == "timed":
            wr(self.path, 5000 if on else 0)
        elif self.mode == "led":
            wr(self.path, 1 if on else 0)
        self.state = on

    def pulse(self, ms=120):
        if not self.available:
            return
        self.set(True)
        time.sleep(max(0.0, ms) / 1000.0)
        self.set(False)

    def describe(self):
        return "none" if self.mode == "none" else "%s %s" % (self.mode, self.path)


def retroarch_msg(text, port=55355):
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(("SHOW_MSG " + text).encode(), ("127.0.0.1", port))
        s.close()
    except OSError:
        pass


def report(conf=None):
    conf = conf if conf is not None else load_conf()
    bl, bt, mo = Backlight(conf), Battery(conf), Motor(conf)
    card = audio_card()
    return "\n".join([
        "config: %s" % ("none (this device has no hw-%s.json)" % device() if conf is None else "loaded"),
        "backlight: %s, now %s" % (bl.describe(), bl.get()),
        "battery: %s, now %s" % (bt.node or "none", bt.read()),
        "audio card: %d" % card,
        "motor: %s" % mo.describe(),
    ])
