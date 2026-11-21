#!/usr/bin/env python3
"""RG OS first-boot installer: the logic (pure Python, no pygame, so the tests can run it anywhere).

An installer image (`sudo ./build.sh <device> installer`) is a normal RG OS card plus a payload folder on the FAT boot
partition:

  /rgos-payload/manifest.json        {"format": 1, "id": ..., "device": ..., "components": [...]}
  /rgos-payload/<component>.tar.gz   one archive per component (PortMaster, the libretro cores, optional extras)

On the first boot rgos-session runs `rgos-installer` (the screen) before anything else. It uses this module to

  1. create and format the ROMS partition in the free space of the card (rgos-roms) and mount it,
  2. create the folder tree (roms/<system>, saves/, states/, bios/, ...),
  3. unpack every payload component (checked against its SHA-256 while it streams in),
  4. write /rgos-installed.json on the boot partition, delete the payload, and ask for a reboot.

Every step is safe to repeat: a failed install is resumed on the next boot (finished components are remembered in
/rgos-install-state.json) and nothing on the ROMS partition is ever deleted. Options are read from /rgos-install.txt on
the boot partition (one `key=value` per line):

  skip_install=1        never run the installer on this card (boot RG OS as it is)
  keep_payload=1        keep /rgos-payload after a successful install (so it can be reinstalled by deleting rgos-installed.json)
  skip=cores,portmaster component ids to leave out
"""
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import traceback

import sdcard

BOOT = os.environ.get("RGOS_BOOT_MNT", "/boot")
ROMS = os.environ.get("RGOS_ROMS", "/media/roms")
RUN = os.environ.get("RGOS_RUN", "/run/rgos")
LOG_FILE = os.environ.get("RGOS_INSTALL_LOG", "/var/log/rgos-installer.log")
DEVICE_FILE = os.environ.get("RGOS_DEVICE_FILE", "/etc/rgos-device")
ROMS_SCRIPT = os.environ.get("RGOS_ROMS_SCRIPT", "/opt/rgos/rgos-roms")

PAYLOAD = "rgos-payload"
MANIFEST = "manifest.json"
DONE_FILE = "rgos-installed.json"
STATE_FILE = "rgos-install-state.json"
OPTIONS_FILE = "rgos-install.txt"
LOG_COPY = "rgos-install-log.txt"
FORMAT = 1
MARGIN = 32 << 20           # free space that must be left on ROMS after everything is unpacked
EXIT_REBOOT = 10            # exit status of rgos-installer: installed, reboot now
DEVICES = ("rg34xxsp", "rg35xxh", "rg35xxsp", "rg-rotate")
CANVAS = {"rg-rotate": (720, 720), "rg34xxsp": (720, 480), "rg35xxh": (720, 540), "rg35xxsp": (720, 540)}
DEVICE_NAMES = {"rg-rotate": "Anbernic RG Rotate", "rg34xxsp": "Anbernic RG34XXSP",
                "rg35xxh": "Anbernic RG35XX H", "rg35xxsp": "Anbernic RG35XX SP"}
SHARED_DIRS = ("artwork", "bios", "config", "cores", "firmware", "music", "saves", "screenshots", "splash", "states", "update")
# NOT created here: rgos-data. rgos-session copies the boot partition's settings there only when the folder is missing.

ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
ARCHIVE_RE = re.compile(r"^[A-Za-z0-9._-]{1,96}\.(tar|tar\.gz|tgz)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
DESTS = ("roms", "boot")


class InstallError(Exception):
    """A failure whose text is fit to show on screen."""


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def device_id():
    try:
        with open(DEVICE_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def safe_rel(name):
    """A normalised relative path that stays inside its root, or None."""
    if not isinstance(name, str) or not name or "\0" in name or "\\" in name:
        return None
    p = posixpath.normpath(name)
    if p in (".", "") or p.startswith("/"):
        return None
    if any(part in ("", "..") for part in p.split("/")):
        return None
    return p


def read_options(boot=None):
    opts = {"skip_install": False, "keep_payload": False, "skip": set()}
    try:
        with open(os.path.join(boot or BOOT, OPTIONS_FILE), encoding="utf-8-sig", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return opts
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip().lower(), val.strip()
        if key in ("skip_install", "keep_payload"):
            opts[key] = val.lower() in ("1", "true", "yes", "on")
        elif key == "skip":
            opts["skip"] = {v.strip() for v in val.split(",") if v.strip()}
    return opts


def pending(boot=None):
    """The payload folder when this card still has to be installed, else None."""
    boot = boot or BOOT
    if os.path.exists(os.path.join(boot, DONE_FILE)):
        return None
    pdir = os.path.join(boot, PAYLOAD)
    if not os.path.isfile(os.path.join(pdir, MANIFEST)):
        return None
    if read_options(boot)["skip_install"]:
        return None
    return pdir


def load_manifest(pdir, device=None):
    """Read and check manifest.json; returns {"id", "device", "components": [...]}."""
    try:
        with open(os.path.join(pdir, MANIFEST), encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError) as e:
        raise InstallError("the installer payload is unreadable (%s)" % e)
    if not isinstance(man, dict) or man.get("format") != FORMAT:
        raise InstallError("the installer payload has an unknown format")
    want = device if device is not None else device_id()
    if want and man.get("device") != want:
        raise InstallError("this payload is for %s, not %s" % (man.get("device"), want))
    if not isinstance(man.get("id"), str) or not ID_RE.match(man["id"]):
        raise InstallError("the payload has a bad build id")
    comps, seen = [], set()
    raw = man.get("components")
    if not isinstance(raw, list):
        raise InstallError("the payload lists no components")
    for c in raw:
        if not isinstance(c, dict):
            raise InstallError("a payload component is malformed")
        cid, arch = c.get("id"), c.get("archive")
        if not isinstance(cid, str) or not ID_RE.match(cid) or cid in seen:
            raise InstallError("bad or duplicate component id %r" % (cid,))
        if not isinstance(arch, str) or not ARCHIVE_RE.match(arch):
            raise InstallError("%s: bad archive name" % cid)
        sha, size = c.get("sha256"), c.get("bytes", 0)
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            raise InstallError("%s: bad checksum" % cid)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise InstallError("%s: bad size" % cid)
        dest = c.get("dest")
        if dest not in DESTS:
            raise InstallError("%s: bad destination %r" % (cid, dest))
        target = c.get("target", "")
        if target not in ("", None) and safe_rel(target) is None:
            raise InstallError("%s: bad target folder" % cid)
        miss = c.get("if_missing")
        if miss not in ("", None) and safe_rel(miss) is None:
            raise InstallError("%s: bad if_missing path" % cid)
        name = c.get("name")
        seen.add(cid)
        comps.append({"id": cid, "name": name if isinstance(name, str) and name else cid, "archive": arch, "sha256": sha,
                      "bytes": size, "dest": dest, "target": safe_rel(target) if target else "",
                      "if_missing": safe_rel(miss) if miss else ""})
    return {"id": man["id"], "device": man.get("device", ""), "components": comps}


class _Reader:
    """Read-only file wrapper that hashes and counts what tarfile pulls through it."""

    def __init__(self, f, on_bytes):
        self.f, self.h, self.n, self.cb = f, hashlib.sha256(), 0, on_bytes

    def read(self, size=-1):
        b = self.f.read(size)
        if b:
            self.h.update(b)
            self.n += len(b)
            self.cb(self.n)
        return b


def extract(archive, root, sha256, progress=None):
    """Stream a tar(.gz) into `root`. Only plain files and folders whose paths stay inside `root` are written.

    The SHA-256 of the whole archive is checked once it has been read to the end; a mismatch raises InstallError (the
    files already written are overwritten again by the retry, nothing is deleted). Returns (files, bytes written).
    """
    total = max(1, os.path.getsize(archive))
    files = written = skipped = 0
    root_real = os.path.realpath(root)
    os.makedirs(root, exist_ok=True)
    with open(archive, "rb") as raw:
        rd = _Reader(raw, (lambda n: progress(min(1.0, n / total))) if progress else (lambda n: None))
        try:
            with tarfile.open(fileobj=rd, mode="r|*") as tf:
                for m in tf:
                    if m.name in (".", "./"):
                        continue
                    rel = safe_rel(m.name)
                    if rel is None:
                        raise InstallError("unsafe path in an archive: %r" % m.name[:80])
                    dest = os.path.join(root, rel)
                    where = os.path.realpath(dest if m.isdir() else os.path.dirname(dest))
                    if where != root_real and not where.startswith(root_real + os.sep):
                        raise InstallError("an archive tries to write outside its folder: %r" % m.name[:80])
                    if m.isdir():
                        os.makedirs(dest, exist_ok=True)
                        continue
                    if not m.isreg():
                        skipped += 1
                        continue
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    src = tf.extractfile(m)
                    with open(dest, "wb") as out:
                        shutil.copyfileobj(src, out, 256 << 10)
                    try:
                        os.chmod(dest, 0o755 if m.mode & 0o111 else 0o644)
                    except OSError:
                        pass
                    files += 1
                    written += m.size
        except tarfile.TarError as e:
            raise InstallError("an archive is damaged (%s)" % e)
        except (EOFError, OSError) as e:
            if isinstance(e, OSError) and getattr(e, "errno", None) in (28, 122):
                raise InstallError("the ROMS partition is full")
            raise InstallError("could not unpack an archive (%s)" % e)
        while rd.read(1 << 20):
            pass
    if rd.h.hexdigest() != sha256:
        raise InstallError("an archive failed its checksum (bad copy of the card image?)")
    if skipped:
        log("%s: skipped %d non-regular entries" % (os.path.basename(archive), skipped))
    return files, written


def folder_list(roms):
    dirs = [os.path.join(roms, d) for d in SHARED_DIRS] + [os.path.join(roms, "roms")]
    for sid in sdcard.SYSTEM_DIRS:
        dirs.append(os.path.join(roms, "roms", sid))
        if sid != "ports":
            dirs += [os.path.join(roms, "saves", sid), os.path.join(roms, "states", sid)]
    return dirs


def make_folders(roms):
    for d in folder_list(roms):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            raise InstallError("could not create %s (%s)" % (d, e))


def _run(args, timeout=60):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, universal_newlines=True)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "%s" % e


def _blkid_type(dev):
    rc, out = _run(["blkid", "-p", "-o", "value", "-s", "TYPE", dev])
    return out.strip() if rc == 0 else ""


def _boot_source(boot):
    try:
        with open("/proc/mounts") as f:
            for line in f:
                p = line.split()
                if len(p) > 1 and p[1] == boot:
                    return p[0]
    except OSError:
        pass
    return ""


def partition_roms(boot=None):
    """Create + format the ROMS partition with rgos-roms (which only touches layouts it recognises); returns its device."""
    boot = boot or BOOT
    src = _boot_source(boot)
    m = re.match(r"^(/dev/mmcblk\d+)p1$", src)
    if not m:
        raise InstallError("RG OS is not running from an SD card (boot partition: %s), so the card cannot be partitioned" % (src or "unknown"))
    log("running %s" % ROMS_SCRIPT)
    rc, out = _run(["sh", ROMS_SCRIPT], timeout=900)
    log("rgos-roms exit %s %s" % (rc, out.strip()[-400:]))
    try:
        with open(os.path.join(RUN, "roms-part")) as f:
            pn = f.read().strip()
    except OSError:
        pn = ""
    if not pn.isdigit():
        raise InstallError("the card's partition table was not recognised (see /var/log/rgos-roms.log)")
    dev = "%sp%s" % (m.group(1), pn)
    for _ in range(40):
        if os.path.exists(dev):
            break
        time.sleep(0.25)
    if not os.path.exists(dev):
        raise InstallError("the ROMS partition was not created (see /var/log/rgos-roms.log)")
    fs = _blkid_type(dev)
    if not fs:
        raise InstallError("the ROMS partition could not be formatted (see /var/log/rgos-roms.log)")
    log("ROMS partition %s holds %s" % (dev, fs))
    return dev


def mount_roms(dev, mountpoint):
    if os.path.ismount(mountpoint):
        return
    os.makedirs(mountpoint, exist_ok=True)
    fs = _blkid_type(dev)
    attempts = []
    if fs == "exfat":
        try:
            with open("/proc/filesystems") as f:
                have = "exfat" in f.read().split()
        except OSError:
            have = False
        if not have:
            _run(["modprobe", "exfat"])
        attempts.append(["mount", "-t", "exfat", "-o", "noatime,umask=000", dev, mountpoint])
    elif fs == "vfat":
        attempts.append(["mount", "-t", "vfat", "-o", "noatime,umask=000", dev, mountpoint])
    elif fs == "ext4":
        attempts.append(["mount", "-t", "ext4", "-o", "noatime", dev, mountpoint])
    for a in attempts:
        rc, out = _run(a, timeout=120)
        if rc == 0 and os.path.ismount(mountpoint):
            return
        log("%s -> %s %s" % (" ".join(a), rc, out.strip()))
    raise InstallError("the ROMS partition (%s, %s) could not be mounted" % (dev, fs or "unknown file system"))


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Installer:
    """Runs the install. `snapshot()` is what the screen draws; call `run()` from a worker thread."""

    def __init__(self, boot=None, roms=None, partition=None, mount=None, device=None):
        self.boot = boot or BOOT
        self.roms = roms or ROMS
        self.partition = partition or (lambda: partition_roms(self.boot))
        self.mount = mount or (lambda dev: mount_roms(dev, self.roms))
        self.device = device if device is not None else device_id()
        self.lock = threading.Lock()
        self.pdir = os.path.join(self.boot, PAYLOAD)
        self.opts = read_options(self.boot)
        self.error = ""
        self.finished = False
        self.ok = False
        self.detail = ""
        self.fraction = 0.0
        self.indeterminate = False
        self.man = {"id": "", "device": self.device, "components": []}
        try:
            self.man = load_manifest(self.pdir, self.device)
        except InstallError as e:
            self.error = str(e)
        comps = [c for c in self.man["components"] if c["id"] not in self.opts["skip"]]
        self.comps = comps
        total = sum(max(1, c["bytes"]) for c in comps) or 1
        steps = [{"id": "partition", "name": "Partitioning the SD card", "weight": 10.0},
                 {"id": "folders", "name": "Creating folders", "weight": 2.0}]
        for c in comps:
            steps.append({"id": c["id"], "name": "Installing " + c["name"], "weight": max(1.0, 85.0 * max(1, c["bytes"]) / total)})
        steps.append({"id": "finish", "name": "Finishing up", "weight": 3.0})
        for s in steps:
            s["status"] = "pending"
        self.steps = steps
        self.current = -1
        self.sum_w = sum(s["weight"] for s in steps)

    # -- state shown on screen ---------------------------------------------------------------------------------------
    def snapshot(self):
        with self.lock:
            return {"steps": [dict(s) for s in self.steps], "current": self.current, "fraction": self.fraction,
                    "detail": self.detail, "error": self.error, "finished": self.finished, "ok": self.ok,
                    "indeterminate": self.indeterminate, "device": self.device, "id": self.man["id"]}

    def _begin(self, index, detail="", indeterminate=False):
        with self.lock:
            self.current = index
            self.steps[index]["status"] = "run"
            self.detail = detail
            self.indeterminate = indeterminate
            self._recalc(0.0)
        log("== %s" % self.steps[index]["name"])

    def _recalc(self, frac):
        done = sum(s["weight"] for s in self.steps if s["status"] in ("done", "skip"))
        cur = self.steps[self.current]["weight"] * frac if 0 <= self.current < len(self.steps) and self.steps[self.current]["status"] == "run" else 0.0
        self.fraction = min(1.0, (done + cur) / self.sum_w)

    def _progress(self, frac, detail=None):
        with self.lock:
            if detail is not None:
                self.detail = detail
            self.indeterminate = False
            self._recalc(frac)

    def _end(self, index, status="done"):
        with self.lock:
            self.steps[index]["status"] = status
            self._recalc(0.0)

    def _fail(self, msg):
        with self.lock:
            self.error = msg
            if 0 <= self.current < len(self.steps):
                self.steps[self.current]["status"] = "fail"
            self.finished, self.ok = True, False
        log("FAILED: %s" % msg)
        self._copy_log()

    def _copy_log(self):
        try:
            if os.path.isfile(LOG_FILE) and os.path.isdir(self.boot):
                shutil.copyfile(LOG_FILE, os.path.join(self.boot, LOG_COPY))
        except OSError:
            pass

    # -- the install ---------------------------------------------------------------------------------------------------
    def run(self):
        if self.error:
            self._fail(self.error)
            return False
        try:
            self._run()
        except InstallError as e:
            self._fail(str(e))
            return False
        except Exception as e:  # a bug must show on screen, not leave the card half installed with a blank display
            log(traceback.format_exc())
            self._fail("unexpected error: %s" % e)
            return False
        with self.lock:
            self.finished, self.ok = True, True
            self.fraction = 1.0
            self.detail = ""
            self.indeterminate = False
        return True

    def _state(self):
        try:
            with open(os.path.join(self.boot, STATE_FILE)) as f:
                st = json.load(f)
            return set(x for x in st.get("done", []) if isinstance(x, str)) if isinstance(st, dict) else set()
        except (OSError, ValueError):
            return set()

    def _save_state(self, done):
        try:
            _write_json(os.path.join(self.boot, STATE_FILE), {"id": self.man["id"], "done": sorted(done)})
        except OSError as e:
            log("could not save the install state: %s" % e)

    def _root(self, dest):
        return self.roms if dest == "roms" else self.boot

    def _run(self):
        log("installer start: build %s, device %s, components %s" % (self.man["id"], self.device, [c["id"] for c in self.comps]))
        # 1. partition + format + mount
        self._begin(0, "Creating the ROMS partition", True)
        dev = self.partition()
        self.mount(dev)
        for c in self.comps:
            if not os.path.isfile(os.path.join(self.pdir, c["archive"])):
                raise InstallError("%s: the archive %s is missing from the payload" % (c["name"], c["archive"]))
        need = sum(c["bytes"] for c in self.comps if c["dest"] == "roms") + MARGIN
        free = shutil.disk_usage(self.roms).free
        if free < need:
            raise InstallError("the ROMS partition is too small: %d MB free, %d MB needed" % (free >> 20, need >> 20))
        self._end(0)
        # 2. folders
        i = 1
        self._begin(i, "roms/, saves/, states/, bios/ ...")
        make_folders(self.roms)
        self._end(i)
        # 3. components
        done = self._state()
        for c in self.comps:
            i += 1
            self._begin(i, c["name"])
            root = self._root(c["dest"])
            target = os.path.join(root, c["target"]) if c["target"] else root
            if c["id"] in done:
                log("%s: already installed on an earlier boot" % c["id"])
                self._end(i, "skip")
                continue
            if c["if_missing"] and os.path.exists(os.path.join(root, c["if_missing"])):
                log("%s: %s already exists, left alone" % (c["id"], c["if_missing"]))
                self._end(i, "skip")
                done.add(c["id"])
                self._save_state(done)
                continue
            name = c["name"]
            files, _ = extract(os.path.join(self.pdir, c["archive"]), target, c["sha256"],
                               lambda fr, n=name: self._progress(fr, "%s  %d%%" % (n, int(fr * 100))))
            log("%s: %d files into %s" % (c["id"], files, target))
            done.add(c["id"])
            self._save_state(done)
            self._end(i)
        # 4. finish
        i += 1
        self._begin(i, "Writing the install record", True)
        self._finish(done)
        self._end(i)

    def _finish(self, done):
        stamp = {"id": self.man["id"], "device": self.device, "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "components": sorted(done)}
        try:
            _write_json(os.path.join(self.boot, DONE_FILE), stamp)
        except OSError as e:
            raise InstallError("could not write %s on the boot partition (%s)" % (DONE_FILE, e))
        try:
            os.remove(os.path.join(self.boot, STATE_FILE))
        except OSError:
            pass
        if not self.opts["keep_payload"]:
            shutil.rmtree(self.pdir, ignore_errors=True)
        self._copy_log()
        try:
            os.sync()
        except (AttributeError, OSError):
            pass
        log("installer done")


def main(argv):
    """Headless use / debugging: `installer.py check` or `installer.py run` (no screen)."""
    cmd = argv[1] if len(argv) > 1 else "check"
    pdir = pending()
    if cmd == "check":
        print("pending: %s" % (pdir or "no"))
        return 0 if pdir else 1
    if cmd == "run":
        if not pdir:
            print("nothing to install")
            return 0
        inst = Installer()
        ok = inst.run()
        snap = inst.snapshot()
        print("installed" if ok else "FAILED: %s" % snap["error"])
        return EXIT_REBOOT if ok else 2
    print("usage: installer.py [check|run]")
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv))
