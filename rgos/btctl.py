#!/usr/bin/env python3
import fcntl, glob, json, os, re, select, subprocess, sys, tarfile, threading, time, uuid

CONF = os.environ.get("RGOS_BT_CONF", "/var/lib/rgos/bt.json")
PAIRINGS = os.environ.get("RGOS_BT_PAIRINGS", "/var/lib/rgos/bluetooth.tar.gz")
STATE_DIR = "/var/lib/bluetooth"
SYSBT = "/sys/class/bluetooth"
SYSSERIAL = "/sys/bus/serial"
LOCK = os.environ.get("RGOS_BT_LOCK", "/run/rgos-bt-start.lock")
KEY_MODULES = ("bluetooth", "hci_uart", "btrtl", "btbcm", "btusb")  # a failed modprobe of one of these explains a missing adapter
BLUETOOTHD = ["/usr/libexec/bluetooth/bluetoothd", "/usr/lib/bluetooth/bluetoothd", "/usr/sbin/bluetoothd"]
MODULES = ["bluetooth", "rfcomm", "bnep", "hidp", "uhid", "hid-generic", "hid-sony", "hid-playstation", "hid-nintendo",
           "btrtl", "btbcm", "btintel", "btmtk", "btqca", "hci_uart", "btusb"]
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x01|\x02|\r")
MAC = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", re.I)


def log(msg):
    print("%s rgos-bt: %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def run(cmd, timeout=10, inp=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace", input=inp)
        return r.returncode, ANSI.sub("", r.stdout + r.stderr)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def enabled():
    try:
        with open(CONF) as f:
            return bool(json.load(f).get("enabled", True))
    except (OSError, ValueError, AttributeError):
        return True


def set_enabled(on):
    try:
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF, "w") as f:
            json.dump({"enabled": bool(on)}, f)
    except OSError:
        pass
    run(["rfkill", "unblock", "bluetooth"])
    run(["bluetoothctl", "power", "on" if on else "off"])


def apply_power():
    run(["bluetoothctl", "power", "on" if enabled() else "off"])


def restore_pairings():
    if not os.path.exists(PAIRINGS):
        return
    try:
        with tarfile.open(PAIRINGS) as t:
            t.extractall("/", filter="fully_trusted") if sys.version_info >= (3, 12) else t.extractall("/")
        log("restored pairings from %s" % PAIRINGS)
    except Exception as e:
        log("could not restore pairings: %r" % (e,))


def save_pairings():
    try:
        os.makedirs(os.path.dirname(PAIRINGS), exist_ok=True)
        tmp = PAIRINGS + ".tmp"
        with tarfile.open(tmp, "w:gz") as t:
            if os.path.isdir(STATE_DIR):
                t.add(STATE_DIR, arcname=STATE_DIR.lstrip("/"))
        os.replace(tmp, PAIRINGS)
        return True
    except Exception as e:
        log("could not save pairings: %r" % (e,))
        return False


def module_names():
    names = list(MODULES)
    for root, _d, files in os.walk("/lib/modules"):
        if "/bluetooth" in root:
            names += [re.sub(r"\.ko(\..*)?$", "", f) for f in files if ".ko" in f]
        else:
            names += [re.sub(r"\.ko(\..*)?$", "", f) for f in files if re.match(r"(btrtl|rtk_bt|.*_bt(_uart|_usb)?|bt_.*)\.ko", f)]
    return list(dict.fromkeys(names))


def adapter():
    try:
        hci = sorted(n for n in os.listdir(SYSBT) if re.fullmatch(r"hci\d+", n))
        return hci[0] if hci else None
    except OSError:
        return None


def load_modules():
    failed = []
    for m in module_names():
        rc, out = run(["modprobe", m], timeout=20)
        if rc != 0 and m in KEY_MODULES:
            failed.append("%s: %s" % (m, out.strip().replace("\n", " ")[:100]))
    return failed


def reprobe_serdev():
    """The RTL8821CS on the H700 handhelds hangs off a UART as a serdev device. If it was created before
    hci_uart existed (or its probe was deferred and then lost), nothing binds it: ask the bus to try again."""
    try:
        devs = [d for d in os.listdir(SYSSERIAL + "/devices") if "-" in d]
    except OSError:
        return []
    kicked = []
    for d in devs:
        if os.path.exists("%s/devices/%s/driver" % (SYSSERIAL, d)):
            continue
        try:
            with open(SYSSERIAL + "/drivers_probe", "w") as f:
                f.write(d)
            kicked.append(d)
        except OSError:
            pass
    return kicked


def _read(path, n=200):
    try:
        with open(path, "rb") as f:
            return f.read(n).replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return ""


def diag(tag):
    """Everything needed to tell 'no node in the device tree' from 'driver missing' from 'firmware missing'."""
    log("---- diagnostics (%s)" % tag)
    log("kernel %s" % run(["uname", "-r"])[1].strip())
    nodes = []
    for root, _d, files in os.walk("/proc/device-tree"):
        if "compatible" in files:
            comp = _read(os.path.join(root, "compatible"))
            if re.search(r"bluetooth|-bt\b|rtl8\w*-bt|brcm,bcm\d+-bt|hci", comp, re.I):
                nodes.append("%s [%s] status=%s" % (root[len("/proc/device-tree"):] or "/", comp,
                                                    _read(os.path.join(root, "status")) or "okay"))
    log("device-tree Bluetooth nodes: %s" % (" | ".join(nodes) or "NONE (the device tree has no Bluetooth node: the kernel cannot create an adapter)"))
    try:
        sdev = sorted(os.listdir(SYSSERIAL + "/devices"))
    except OSError:
        sdev = []
    log("serdev devices: %s" % (" ".join("%s->%s" % (d, os.path.basename(os.path.realpath("%s/devices/%s/driver" % (SYSSERIAL, d))) if os.path.exists("%s/devices/%s/driver" % (SYSSERIAL, d)) else "unbound") for d in sdev) or "(none)"))
    fw = []
    for pat in ("rtl_bt/*", "rtlbt/*", "*/rtl*_fw*", "brcm/*.hcd", "qca/*", "mediatek/*bt*"):
        fw += [os.path.relpath(x, "/lib/firmware") for x in glob.glob("/lib/firmware/" + pat)]
    log("/lib/firmware Bluetooth files: %s" % (" ".join(sorted(dict.fromkeys(fw)))[:500] or "NONE"))
    log("firmware_class.path = %r" % _read("/sys/module/firmware_class/parameters/path"))
    rc, out = run(["lsmod"], timeout=6)
    log("lsmod (bluetooth): %s" % (" | ".join(l.split()[0] for l in out.splitlines()[1:] if re.match(r"(bluetooth|hci|bt|rfcomm|bnep|hidp|uhid)", l)) or "(none)"))
    rc, out = run(["dmesg"], timeout=6)
    hits = [l for l in out.splitlines() if re.search(r"bluetooth|hci\d|btrtl|rtl8\d+|hci_uart|serdev|\bh5\b|bt_|rfkill", l, re.I)]
    log("dmesg (%d matching lines, last 30):" % len(hits))
    for l in hits[-30:]:
        log("  " + l[:200])


def _wait_adapter(seconds):
    for _ in range(int(seconds)):
        if adapter():
            return True
        time.sleep(1)
    return bool(adapter())


def find_adapter(attempts=3):
    """Load the drivers and wait for hci0. Retried, because the adapter can appear late (firmware download over
    a slow UART, deferred probes) and a single 30 s window used to leave Bluetooth dead until the next reboot."""
    for n in range(1, attempts + 1):
        failed = load_modules()
        if failed:
            log("modprobe failed: %s" % "; ".join(failed))
        kicked = reprobe_serdev()
        if kicked:
            log("re-probed serdev devices: %s" % " ".join(kicked))
        run(["rfkill", "unblock", "bluetooth"])
        if _wait_adapter(30 if n == 1 else 20):
            if n > 1:
                log("adapter appeared on attempt %d" % n)
            return True
        if n == 1:
            diag("no adapter after attempt 1")
        log("no adapter after attempt %d of %d" % (n, attempts))
    return False


def start():
    try:
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        lk = open(LOCK, "w")
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("start: another start is already running")
        return 0
    except OSError:
        lk = None
    try:
        return _start()
    finally:
        if lk:
            lk.close()


def _start():
    log("start")
    if not find_adapter():
        rc, out = run(["rfkill", "list"])
        log("no Bluetooth adapter in %s (kernel/driver/firmware does not provide one; see diagnostics above). rfkill: %s" % (SYSBT, out.strip().replace("\n", " | ")))
        diag("giving up")
        return 1
    log("adapter %s" % adapter())
    restore_pairings()
    os.makedirs("/run/dbus", exist_ok=True)
    os.makedirs("/var/lib/dbus", exist_ok=True)
    if not os.path.exists("/var/lib/dbus/machine-id"):
        with open("/var/lib/dbus/machine-id", "w") as f:
            f.write(uuid.uuid4().hex + "\n")
    if not os.path.exists("/run/dbus/system_bus_socket"):
        rc, out = run(["dbus-daemon", "--system", "--fork"])
        log("dbus-daemon rc=%s %s" % (rc, out.strip()))
        for _ in range(20):
            if os.path.exists("/run/dbus/system_bus_socket"):
                break
            time.sleep(0.25)
    exe = next((p for p in BLUETOOTHD if os.path.exists(p)), None)
    if not exe:
        log("bluetoothd not found (bluez missing from the image)")
        return 1
    rc, _ = run(["pidof", "bluetoothd"])
    if rc != 0:
        subprocess.Popen([exe, "-n"], stdout=sys.stdout, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(30):
        rc, out = run(["bluetoothctl", "show"], timeout=5)
        if rc == 0 and "Controller" in out:
            break
        time.sleep(0.5)
    else:
        log("bluetoothd did not answer: %s" % out.strip())
        return 1
    apply_power()
    run(["bluetoothctl", "pairable", "on"])
    run(["bluetoothctl", "discoverable", "off"])
    rc, out = run(["bluetoothctl", "show"])
    log("ready: %s" % " ".join(l.strip() for l in out.splitlines() if re.search(r"Controller|Powered|Name:", l)))
    return 0


def parse_info(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"\s*Device ((?:[0-9A-F]{2}:){5}[0-9A-F]{2})", line, re.I)
        if m:
            cur = out.setdefault(m.group(1).upper(), {"name": "", "paired": False, "connected": False, "trusted": False, "rssi": None})
            continue
        if cur is None or ":" not in line:
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        if k in ("Alias", "Name") and (k == "Alias" or not cur["name"]):
            cur["name"] = v
        elif k in ("Paired", "Connected", "Trusted"):
            cur[k.lower()] = v.lower().startswith("yes")
        elif k == "RSSI":
            m2 = re.search(r"\(?(-?\d+)\)?\s*$", v)
            cur["rssi"] = int(m2.group(1)) if m2 else None
    return out


def devices():
    rc, out = run(["bluetoothctl", "devices"], timeout=6)
    macs = [m.group(1).upper() for m in re.finditer(r"Device ((?:[0-9A-F]{2}:){5}[0-9A-F]{2})", out, re.I)] if rc == 0 else []
    if not macs:
        return []
    rc, text = run(["bluetoothctl"], timeout=15, inp="".join("info %s\n" % m for m in macs) + "quit\n")
    info = parse_info(text)
    rows = []
    for mac in macs:
        d = info.get(mac)
        if not d:
            continue
        if not d["paired"] and (not d["name"] or d["name"].replace("-", ":").upper() == mac):
            continue
        rows.append(dict(d, mac=mac))
    rows.sort(key=lambda d: (not d["paired"], not d["connected"], -(d["rssi"] if d["rssi"] is not None else -200)))
    return rows[:16]


def powered():
    rc, out = run(["bluetoothctl", "show"], timeout=5)
    if rc != 0 or "Controller" not in out:
        return None
    return bool(re.search(r"Powered:\s*yes", out))


def scan(seconds=8):
    run(["rfkill", "unblock", "bluetooth"])
    run(["bluetoothctl", "power", "on"])
    run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"], timeout=seconds + 6)


def _converse(cmds, waits, timeout):
    p = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    outs = []
    try:
        for cmd, pat in zip(cmds, waits):
            p.stdin.write(cmd + "\n"); p.stdin.flush()
            buf, end = "", time.time() + (timeout if pat else 1.0)
            while time.time() < end:
                r, _, _ = select.select([p.stdout], [], [], 0.3)
                if r:
                    chunk = os.read(p.stdout.fileno(), 4096).decode("utf-8", "replace")
                    if not chunk:
                        break
                    buf += ANSI.sub("", chunk)
                    if pat and re.search(pat, buf):
                        break
            outs.append(buf)
        return outs
    finally:
        try:
            p.stdin.write("quit\n"); p.stdin.flush()
        except OSError:
            pass
        try:
            p.wait(3)
        except subprocess.TimeoutExpired:
            p.kill()


def pair(mac):
    if not MAC.match(mac):
        return False, "bad address"
    outs = _converse(["agent NoInputNoOutput", "default-agent", "pair " + mac, "trust " + mac, "connect " + mac],
                     [None, None, r"Pairing successful|Failed to pair|AlreadyExists|Already Exists|not available",
                      r"trust succeeded|not available|Failed", r"Connection successful|Failed to connect"], 35)
    paired = re.search(r"Pairing successful|AlreadyExists|Already Exists", outs[2]) is not None
    connected = "Connection successful" in outs[4]
    save_pairings()
    if connected:
        return True, "Connected"
    if paired:
        return True, "Paired (connect failed: put the device in pairing mode / switch it on)"
    return False, "Pairing failed (is the device in pairing mode?)"


def connect(mac):
    rc, out = run(["bluetoothctl", "connect", mac], timeout=25)
    return ("Connection successful" in out), ("Connected" if "Connection successful" in out else "Could not connect")


def disconnect(mac):
    run(["bluetoothctl", "disconnect", mac], timeout=10)
    return True, "Disconnected"


def forget(mac):
    run(["bluetoothctl", "remove", mac], timeout=10)
    save_pairings()
    return True, "Forgot device"


class Manager:
    def __init__(self):
        self.rows, self.on, self.busy, self.msg, self.msg_until, self.scanning = [], None, False, "", 0.0, False
        self.last_retry = 0.0

    def _bg(self, fn):
        if self.busy:
            return
        self.busy = True

        def job():
            try:
                fn()
            except Exception as e:
                self.say("Error: %r" % (e,))
            finally:
                self.busy = False
        threading.Thread(target=job, daemon=True).start()

    def say(self, m, secs=5):
        self.msg, self.msg_until = m, time.time() + secs

    def _refresh(self):
        self.on = powered()
        if self.on is None and time.time() - self.last_retry > 60:
            # no adapter / bluetoothd yet: the boot-time attempt may have lost a race, so try the whole bring-up again
            self.last_retry = time.time()
            self.say("Looking for the Bluetooth adapter...", 90)
            start()
            self.msg_until = 0.0
            self.on = powered()
        self.rows = devices() if self.on is not None else []

    def refresh(self):
        self._bg(self._refresh)

    def scan_now(self):
        def job():
            self.scanning = True
            try:
                scan()
            finally:
                self.scanning = False
            self._refresh()
        self._bg(job)

    def act(self, fn, mac, label):
        def job():
            self.say(label + "...", 40)
            ok, m = fn(mac)
            self.say(m)
            self._refresh()
        self._bg(job)

    def toggle(self):
        def job():
            set_enabled(not bool(self.on))
            self._refresh()
        self._bg(job)


def status_text():
    p = powered()
    if p is None:
        return "No Bluetooth adapter (see /var/log/rgos-bt.log)" if not adapter() else "Starting..."
    return "Bluetooth is on" if p else "Bluetooth is off"


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "start":
        sys.exit(start())
    elif cmd == "diag":
        diag("manual")
    elif cmd == "list":
        for d in devices():
            print(d["mac"], "paired" if d["paired"] else "-", "connected" if d["connected"] else "-", d["name"])
    elif cmd == "scan":
        scan(); print("done")
    elif cmd == "pair" and len(sys.argv) > 2:
        print(pair(sys.argv[2]))
    elif cmd in ("on", "off"):
        set_enabled(cmd == "on")
    else:
        print("usage: btctl.py start | diag | list | scan | pair <mac> | on | off", file=sys.stderr); sys.exit(2)
