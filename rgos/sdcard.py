#!/usr/bin/env python3
import fcntl, json, os, re, subprocess, sys, time

CONF_FILES = [os.environ.get("RGOS_SDCARD_CONF", "/etc/rgos/sdcard.json"), "/var/lib/rgos/sdcard.json"]
DEFAULTS = {"enabled": True,
            "mountpoint": "/media/roms2",
            "fs": ["exfat", "vfat", "ext4", "ntfs"],
            "min_mb": 8,
            "create_folders": True,
            "readonly": False}
STATUS_FILE = os.environ.get("RGOS_SDCARD_STATUS", "/run/rgos/sdcard2.json")
LOCK_FILE = os.environ.get("RGOS_SDCARD_LOCK", "/run/rgos/sdcard.lock")
LOG_FILE = os.environ.get("RGOS_SDCARD_LOG", "/var/log/rgos-sdcard.log")
PROC_MOUNTS = "/proc/mounts"
SYS_BLOCK = "/sys/block"
SYS_DEV_BLOCK = "/sys/dev/block"
DEV_DIR = "/dev"
PRIMARY_MOUNT = "/media/roms"
SYSTEM_MOUNTS = ("/", "/boot", PRIMARY_MOUNT)
SKIP_LABELS = ("RGBOOT", "RGOS", "ROCKNIX", "rgos-root")
SYSTEM_DIRS = ("gba", "nes", "snes", "gb", "gbc", "genesis", "mastersystem", "gamegear", "sg1000", "segacd", "sega32x", "segapico", "n64", "dreamcast", "saturn", "atari2600", "atari5200", "atari7800", "psx", "gc", "ngp", "ngpc", "ws", "wsc", "arcade", "neogeo", "pico8", "ports")
MOUNT_TYPES = {"exfat": ("exfat",), "vfat": ("vfat",), "ext4": ("ext4",), "ntfs": ("ntfs3", "ntfs")}
MOUNT_OPTS = {"exfat": "noatime,umask=000", "vfat": "noatime,umask=000", "ext4": "noatime", "ntfs3": "noatime,umask=000", "ntfs": "noatime,umask=000"}
DISK_RE = re.compile(r"^mmcblk\d+$")


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def sh(args, timeout=15):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, universal_newlines=True)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "%s" % e


def load_conf():
    conf = dict(DEFAULTS)
    for path in CONF_FILES:
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                conf.update({k: v for k, v in data.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    for key in ("enabled", "create_folders", "readonly"):
        if not isinstance(conf.get(key), bool):
            conf[key] = DEFAULTS[key]

    fs = conf.get("fs")
    allowed_fs = set(MOUNT_TYPES)
    if not isinstance(fs, list):
        fs = list(DEFAULTS["fs"])
    fs = [item for item in fs if isinstance(item, str) and item in allowed_fs]
    conf["fs"] = fs or list(DEFAULTS["fs"])

    min_mb = conf.get("min_mb")
    if isinstance(min_mb, bool) or not isinstance(min_mb, int) or not 1 <= min_mb <= 1024:
        conf["min_mb"] = DEFAULTS["min_mb"]

    mp = conf.get("mountpoint")
    if not isinstance(mp, str) or not mp.startswith("/") or "\x00" in mp:
        mp = DEFAULTS["mountpoint"]
    else:
        mp = os.path.normpath(mp)
        if (not mp.startswith("/media/") or mp in ("/media", PRIMARY_MOUNT)
                or mp.startswith(PRIMARY_MOUNT + "/")):
            mp = DEFAULTS["mountpoint"]
    conf["mountpoint"] = mp
    return conf



def mounts():
    out = []
    try:
        with open(PROC_MOUNTS) as f:
            for line in f:
                p = line.split()
                if len(p) >= 4:
                    dec = lambda s: re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), s)
                    out.append((dec(p[0]), dec(p[1]), p[2], p[3]))
    except OSError:
        pass
    return out


def disk_of(name):
    m = re.match(r"^(?:/dev/)?(mmcblk\d+)(?:p\d+)?$", name or "")
    return m.group(1) if m else None


def _disk_of_path(path):
    try:
        st = os.stat(path)
        real = os.path.realpath("%s/%d:%d" % (SYS_DEV_BLOCK, os.major(st.st_dev), os.minor(st.st_dev)))
    except OSError:
        return None
    if os.path.exists(os.path.join(real, "partition")):
        real = os.path.dirname(real)
    d = os.path.basename(real)
    return d if DISK_RE.match(d) else None


def disk_backing(mountpoint, table=None):
    for src, mnt, _fs, _o in (mounts() if table is None else table):
        if mnt == mountpoint and disk_of(src):
            return disk_of(src)
    return _disk_of_path(mountpoint) if any(m[1] == mountpoint for m in (mounts() if table is None else table)) else None


def boot_disk(table=None):
    table = mounts() if table is None else table
    for mp in ("/", "/boot"):
        d = disk_backing(mp, table)
        if d:
            return d
    return "mmcblk0"



def _num(name):
    return int(re.sub(r"\D", "", name) or 0)


def _read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def candidate_disks(table=None):
    table = mounts() if table is None else table
    system = {d for d in (disk_backing(mp, table) for mp in SYSTEM_MOUNTS) if d}
    system.add(boot_disk(table))
    try:
        names = os.listdir(SYS_BLOCK)
    except OSError:
        return []
    out = []
    for d in sorted((n for n in names if DISK_RE.match(n)), key=_num):
        if d in system or _read_int(os.path.join(SYS_BLOCK, d, "size")) <= 0:
            continue
        out.append(d)
    return out


def partitions(disk):
    parts = []
    try:
        for n in os.listdir(os.path.join(SYS_BLOCK, disk)):
            if re.fullmatch(re.escape(disk) + r"p\d+", n):
                parts.append((n, _read_int(os.path.join(SYS_BLOCK, disk, n, "size"))))
    except OSError:
        pass
    if not parts:
        return [(os.path.join(DEV_DIR, disk), _read_int(os.path.join(SYS_BLOCK, disk, "size")))]
    return [(os.path.join(DEV_DIR, n), s) for n, s in sorted(parts, key=lambda x: _num(x[0].rsplit("p", 1)[1]))]


def sniff_fs(dev):
    """Identify the file system by reading the superblock ourselves: used when blkid is missing, stale or silent."""
    try:
        with open(dev, "rb") as f:
            head = f.read(1024)
            f.seek(1080)
            magic = f.read(2)
    except OSError:
        return ""
    if head[3:11] == b"EXFAT   ":
        return "exfat"
    if head[3:11] == b"NTFS    ":
        return "ntfs"
    if magic == b"\x53\xef":
        return "ext4"
    if len(head) >= 512 and head[510:512] == b"\x55\xaa" and (head[82:90] == b"FAT32   " or head[54:59] in (b"FAT12", b"FAT16")):
        return "vfat"
    return ""


def probe(dev):
    # -p = low-level probe of the device itself. Plain blkid answers from /run/blkid + /etc/blkid.tab, which goes stale when
    # a card is swapped or was probed before it was ready, and that made a perfectly good exFAT card look like "nothing".
    info = {}
    for args in (["blkid", "-p", "-o", "export", dev], ["blkid", "-o", "export", dev]):
        rc, out = sh(args, 8)
        if rc == 0:
            for line in out.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    info[k.strip()] = v.strip()
        if info.get("TYPE"):
            break
    if not info.get("TYPE"):
        guess = sniff_fs(dev)
        if guess:
            info["TYPE"] = guess
            info["SNIFFED"] = "1"
    return info


def pick_partition(disk, conf):
    best = None
    for dev, sectors in partitions(disk):
        if sectors * 512 < conf["min_mb"] * 1048576:
            continue
        info = probe(dev)
        fs, label = info.get("TYPE", ""), info.get("LABEL", "")
        if label in SKIP_LABELS:
            continue
        known = fs in conf["fs"] and fs in MOUNT_TYPES
        if fs and not known:
            continue                    # swap, an Android partition, a file system the user switched off, ...
        # an unrecognised partition is still tried (fstype "auto"): better a failed mount in the log than a silently ignored card
        cand = {"dev": dev, "disk": disk, "fstype": fs if known else "auto", "label": label, "sectors": sectors}
        key = (known, label.upper() == "ROMS", sectors)
        if best is None or key > best[0]:
            best = (key, cand)
    return best[1] if best else None



def mount_dev(dev, fstype, mountpoint, readonly=False, order=None):
    """Returns (mounted, read_only, fstype_used)."""
    os.makedirs(mountpoint, exist_ok=True)
    kinds = list(order or DEFAULTS["fs"]) if fstype == "auto" else [fstype]
    for kind in kinds:
        for mod in {"exfat": ("exfat",), "vfat": ("vfat",), "ntfs": ("ntfs3", "ntfs")}.get(kind, ()):
            sh(["modprobe", mod], 10)
    for ro in ([True] if readonly else [False, True]):
        for kind in kinds:
            for t in MOUNT_TYPES.get(kind, ()):
                opts = MOUNT_OPTS[t] + (",ro" if ro else "")
                rc, out = sh(["mount", "-t", t, "-o", opts, dev, mountpoint], 20)
                if rc == 0:
                    return True, ro, kind
                log("mount -t %s -o %s %s %s failed (rc=%s): %s" % (t, opts, dev, mountpoint, rc, out.strip()[:200]))
    try:
        with open("/proc/filesystems") as f:
            log("kernel file systems: %s" % " ".join(x.split()[-1] for x in f if x.strip()))
    except OSError:
        pass
    rc, out = sh(["dmesg"], 5)
    tail = [l for l in out.splitlines() if re.search(r"exfat|mmc|FAT-fs|EXT4-fs|ntfs", l, re.I)][-6:]
    for l in tail:
        log("dmesg: " + l.strip()[:200])
    return False, False, None


def umount(mountpoint):
    rc, out = sh(["umount", mountpoint], 15)
    if rc != 0:
        sh(["umount", "-l", mountpoint], 15)


def make_folders(mountpoint):
    base = os.path.join(mountpoint, "roms")
    ok = True
    for s in SYSTEM_DIRS:
        path = os.path.join(base, s)
        if os.path.isdir(path):
            continue
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            log("could not create %s: %s" % (path, e))
            ok = False
            break
    return ok


def is_readonly(mountpoint, table=None):
    for _src, mnt, _fs, opts in (mounts() if table is None else table):
        if mnt == mountpoint:
            return "ro" in opts.split(",")
    return False


def write_status(info):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        if info is None:
            if os.path.exists(STATUS_FILE):
                os.unlink(STATUS_FILE)
            return
        tmp = STATUS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(info, f)
        os.replace(tmp, STATUS_FILE)
    except OSError:
        pass


def heal_primary(table, conf):
    cur = disk_backing(PRIMARY_MOUNT, table)
    boot = boot_disk(table)
    if cur is None or cur == boot:
        return False
    for dev, sectors in partitions(boot):
        info = probe(dev)
        if info.get("LABEL") == "ROMS" and info.get("TYPE") in MOUNT_TYPES:
            log("/media/roms is on %s, not on the boot card %s: remounting %s" % (cur, boot, dev))
            umount(PRIMARY_MOUNT)
            ok, _ro, _fs = mount_dev(dev, info["TYPE"], PRIMARY_MOUNT)
            return ok
    return False


def sync():
    conf = load_conf()
    mp = conf["mountpoint"]
    table = mounts()
    if heal_primary(table, conf):
        table = mounts()
    mounted = next((m for m in table if m[1] == mp), None)
    want = None
    if conf["enabled"]:
        for d in candidate_disks(table):
            want = pick_partition(d, conf)
            if want:
                break
    if mounted and want and os.path.basename(mounted[0]) == os.path.basename(want["dev"]):
        pass
    else:
        if mounted:
            log("unmounting %s (%s): %s" % (mp, mounted[0], "card removed or changed" if want else "no card 2"))
            umount(mp)
            mounted = None
        if want:
            ok, ro, used = mount_dev(want["dev"], want["fstype"], mp, bool(conf["readonly"]), conf["fs"])
            if ok:
                want["ro"] = ro
                want["fstype"] = used or want["fstype"]
                log("card 2: %s (%s%s) mounted on %s" % (want["dev"], want["fstype"], ", read-only" if ro else "", mp))
            else:
                log("card 2: could not mount %s (%s)" % (want["dev"], want["fstype"]))
                want = None
    if want:
        if is_readonly(mp):
            want["ro"] = True
        if conf["create_folders"]:
            if want.get("ro"):
                log("card 2 is mounted read-only: cannot create the roms folders on %s" % mp)
            else:
                make_folders(mp)
        st = {"mount": mp, "dev": want["dev"], "disk": want["disk"], "fstype": want["fstype"], "label": want["label"],
              "ro": bool(want.get("ro", False)), "time": int(time.time())}
        write_status(st)
    else:
        write_status(None)
        try:
            os.rmdir(mp)
        except OSError:
            pass
    return want



def load_status_file():
    try:
        with open(STATUS_FILE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def status():
    st = load_status_file()
    if not st or not st.get("mount"):
        return None
    if not any(m[1] == st["mount"] for m in mounts()):
        return None
    return st


def extra_roots():
    st = status()
    return [st["mount"]] if st else []


def usage(mountpoint):
    try:
        s = os.statvfs(mountpoint)
        return s.f_bavail * s.f_frsize, s.f_blocks * s.f_frsize
    except OSError:
        return None



def signature():
    """Cheap fingerprint of the SD slots: changes when a card is inserted or removed."""
    sig = []
    try:
        names = sorted(n for n in os.listdir(SYS_BLOCK) if DISK_RE.match(n))
    except OSError:
        return ()
    for n in names:
        size = _read_int(os.path.join(SYS_BLOCK, n, "size"))
        if size > 0:
            parts = tuple(sorted(x for x in os.listdir(os.path.join(SYS_BLOCK, n)) if x.startswith(n + "p")))
            sig.append((n, size, parts))
    return tuple(sig)


def locked_sync():
    try:
        os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
        lock = open(LOCK_FILE, "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
    except OSError:
        lock = None
    try:
        sync()
    except Exception as e:
        log("sync failed: %r" % (e,))
    finally:
        if lock:
            lock.close()


def card_present():
    return bool(candidate_disks())


def watch(interval=2.0):
    """There is no udev here: poll the slots and sync on boot and whenever a card shows up or goes away.
    A card that is in the slot but not mounted yet (still initialising, partitions not exposed, slow first read) keeps being
    retried for about two minutes instead of the old three polls."""
    last = None
    retry_at = 0.0
    tries = 0
    while True:
        sig = signature()
        now = time.time()
        want_sync = sig != last
        if want_sync:
            tries = 0
        elif retry_at and now >= retry_at:
            want_sync = True
        if want_sync:
            sh(["udevadm", "settle", "--timeout=3"], 5)
            locked_sync()
            last = sig
            if status() is None and card_present() and tries < 40:
                tries += 1
                retry_at = time.time() + min(2.0 + tries * 1.5, 10.0)
            else:
                retry_at = 0.0
        time.sleep(interval)


def cli(argv):
    cmd = next((a for a in argv if not a.startswith("--")), "sync")
    if cmd == "status":
        st = status()
        print(json.dumps(st) if st else "no second SD card")
        return 0 if st else 1
    if cmd == "bootdisk":
        print(boot_disk())
        return 0
    if cmd == "watch":
        watch()
        return 0
    if cmd == "roots":
        for r in extra_roots():
            print(r)
        return 0
    if cmd != "sync":
        print("usage: sdcard.py [sync|watch|status|roots|bootdisk]", file=sys.stderr)
        return 2
    try:
        os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
        lock = open(LOCK_FILE, "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
    except OSError:
        lock = None
    if "--settle" in argv:
        sh(["udevadm", "settle", "--timeout=5"], 8)
    try:
        sync()
    except Exception as e:
        log("sync failed: %r" % (e,))
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
