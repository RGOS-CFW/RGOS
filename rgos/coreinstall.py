#!/usr/bin/env python3
"""Core Installer: download RetroArch cores that are not installed yet.

Pure Python, no pygame, so menu.py can use it and the tests can run it anywhere.

Cores come from the libretro buildbot (one `<core>_libretro.so.zip` per core) and are written to `<ROMS>/cores/`, which
survives reboots and updates (the system image itself is read-only). cores.py and rgos-launch both look in that folder.

The download address can be changed with the RGOS_CORE_URL environment variable or {"url": "..."} in
/etc/rgos/coreinstall.json (a mirror, or a folder of your own with the same `<core>_libretro.so.zip` layout).

Versions: the image carries the build's cores.conf as /etc/rgos/cores.conf (<CORE>_REF=<tag | branch | commit>). A core that is
pinned there is fetched from `<pin_url>/<ref>/<core>_libretro.so.zip` (RGOS_CORE_PIN_URL or {"pin_url": "..."} in coreinstall.json),
never from the latest-nightly folder: like the image build, a pinned version that cannot be had is an error, not a silent fall
back to the latest source. A core with an empty (or no) ref installs the latest as before. An environment variable of the same
name as the setting (e.g. N64_REF) overrides the file, as it does in build.sh.
"""
import json
import os
import platform
import re
import shutil
import threading
import urllib.error
import urllib.request
import zipfile

DEFAULT_URL = "https://buildbot.libretro.com/nightly/linux/aarch64/latest"
CONF_FILE = os.environ.get("RGOS_CORE_CONF", "/etc/rgos/coreinstall.json")
CORES_CONF = os.environ.get("RGOS_CORES_CONF", "/etc/rgos/cores.conf")
# core name (as in cores.SYSTEM_CORE_COMPATIBILITY) -> the cores.conf setting that pins it (same map as core_ref_var in tools/cores-lib.sh)
REF_VAR = {"mednafen_ngp": "NGP_REF", "genesis_plus_gx": "GENESIS_REF", "pcsx_rearmed": "PSX_REF", "dolphin": "GC_REF",
           "flycast": "DC_REF", "flycast_standalone": "DC_REF", "mupen64plus_next": "N64_REF", "yabasanshiro": "SATURN_REF",
           "fake08": "PICO8_REF", "retro8": "PICO8_ALT_REF", "stella2014": "STELLA_REF", "atari800": "ATARI800_REF",
           "prosystem": "PROSYSTEM_REF", "mame2003_plus": "MAME2003_REF", "mame": "MAME_REF"}
REF_RE = re.compile(r"^[A-Za-z0-9._/@+-]*$")
# Cores that must not be offered: dolphin needs its Sys data folder, which only the RG Rotate and H700 images carry, and
# flycast_standalone is a program, not a libretro core (there is nothing to download from the buildbot).
EXCLUDE = frozenset(("dolphin", "flycast_standalone"))
# Cores whose libretro buildbot build asks for desktop OpenGL. RetroArch on this image is a GLES build, so these start and
# die at once ("Requesting OpenGL context, but RetroArch is compiled against OpenGLES"). The image's build.sh builds a GLES
# Flycast; downloading the buildbot one only puts a core on the card that cannot run (and hides the real problem).
# A mirror set in coreinstall.json / RGOS_CORE_URL is trusted: it may carry GLES builds.
DESKTOP_GL_ONLY = frozenset(("flycast",))
MAX_ZIP = 300 << 20
MAX_SO = 600 << 20
CHUNK = 64 << 10
NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")
ELF_MACHINE = {"aarch64": 183, "arm64": 183, "x86_64": 62, "amd64": 62, "armv7l": 40}


class CoreInstallError(Exception):
    """An install failure whose text is fit to show on screen."""


def base_url():
    url = os.environ.get("RGOS_CORE_URL", "")
    if not url:
        try:
            with open(CONF_FILE) as f:
                url = str(json.load(f).get("url", ""))
        except (OSError, ValueError, AttributeError):
            url = ""
    url = (url or DEFAULT_URL).strip().rstrip("/")
    return url if url.startswith(("http://", "https://")) else DEFAULT_URL


def _conf_value(key):
    try:
        with open(CONF_FILE) as f:
            return str(json.load(f).get(key, "") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def pin_url():
    """Where pinned versions live: `<pin_url>/<ref>/<core>_libretro.so.zip`. Empty = no such source is configured."""
    url = (os.environ.get("RGOS_CORE_PIN_URL") or _conf_value("pin_url")).strip().rstrip("/")
    return url if url.startswith(("http://", "https://")) else ""


def read_pins(path=None):
    """{SETTING: ref} from cores.conf, read like tools/cores-lib.sh does (KEY=value lines, # comments, nothing is executed; only
    the known *_REF names and plain ref characters are accepted). An environment variable of the same name wins, even when empty."""
    pins = {}
    try:
        with open(path or CORES_CONF, newline="") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    known = set(REF_VAR.values())
    for line in lines:
        line = line.split("#", 1)[0]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = re.sub(r"\s+", "", k), v.strip().strip("\"'")
        if k in known and REF_RE.match(v):
            pins[k] = v
    for k in known:
        if k in os.environ:
            v = os.environ[k].strip()
            pins[k] = v if REF_RE.match(v) else pins.get(k, "")
    return pins


def pinned_ref(core, pins=None):
    """The version cores.conf pins `core` to, or "" when it follows the latest (or is not covered by cores.conf)."""
    var = REF_VAR.get(core)
    return (read_pins() if pins is None else pins).get(var, "") if var else ""


def short_ref(ref):
    """A ref as shown on screen: a commit hash is cut to 7 characters, a tag or branch is left alone."""
    return ref[:7] if re.fullmatch(r"[0-9a-f]{8,40}", ref or "") else (ref or "")


def core_dir(roms_root):
    return os.path.join(roms_root, "cores")


def has_copy(dest, core):
    """True if `core` has its own file in the ROMS cores folder, i.e. one this installer can replace (a core that ships in
    the read-only system image does not)."""
    return bool(NAME_RE.match(core)) and os.path.isfile(os.path.join(dest, core + "_libretro.so"))


def candidates(systems, compat, installed, names=None):
    """Every core that could serve one of the given systems, as rows for the menu.

    systems   [(sid, tag, full name)] in menu order; only these systems are considered
    compat    {sid: (core, ...)} the compatibility table (cores.SYSTEM_CORE_COMPATIBILITY)
    installed names of the cores already on the device
    Missing cores come first, installed ones after, each group in table order.
    """
    names, have, rows, by_core = names or {}, set(installed), [], {}
    for sid, tag, _full in systems:
        for core in compat.get(sid, ()):
            if core in EXCLUDE or not NAME_RE.match(core):
                continue
            row = by_core.get(core)
            if row is None:
                row = by_core[core] = {"core": core, "name": names.get(core) or core.replace("_", " "), "systems": [],
                                       "installed": core in have}
                rows.append(row)
            if tag not in row["systems"]:
                row["systems"].append(tag)
    return [r for r in rows if not r["installed"]] + [r for r in rows if r["installed"]]


def uncovered(systems, compat, installed):
    """Systems that have no installed core at all (hidden in the menu until one is installed)."""
    have = set(installed)
    return [sid for sid, _t, _f in systems if not any(c in have for c in compat.get(sid, ()))]


def _check_elf(path):
    try:
        with open(path, "rb") as f:
            head = f.read(20)
    except OSError as e:
        raise CoreInstallError("Could not read the download (%s)" % e.strerror)
    if len(head) < 20 or head[:4] != b"\x7fELF":
        raise CoreInstallError("The download is not a core file")
    want = ELF_MACHINE.get(platform.machine().lower())
    if want is not None and int.from_bytes(head[18:20], "little") != want:
        raise CoreInstallError("That core is built for a different CPU")


def _http_error(e, ref=""):
    if e.code == 404:
        return ("Version %s not available" % ref) if ref else "Not available for this device"
    return "Server error %d" % e.code


def core_url(core, base=None, ref=None):
    """Address of one core's zip. `ref` is the cores.conf version (None = look it up); "" = the latest."""
    ref = pinned_ref(core) if ref is None else ref
    if not ref:
        return "%s/%s_libretro.so.zip" % (base or base_url(), core)
    root = (base or pin_url()).rstrip("/")
    if not root:
        raise CoreInstallError("cores.conf pins %s to %s, but no source for that version is set" % (core, ref))
    return "%s/%s/%s_libretro.so.zip" % (root, ref, core)


def download(core, dest, base=None, progress=None, cancelled=None, opener=None, ref=None):
    """Download and install one core into dest, at the version cores.conf pins it to (the latest when it does not).
    Returns the installed path; raises CoreInstallError."""
    if not NAME_RE.match(core):
        raise CoreInstallError("Bad core name")
    ref = pinned_ref(core) if ref is None else ref
    if core in DESKTOP_GL_ONLY and not base and base_url() == DEFAULT_URL and not (ref and pin_url()):
        raise CoreInstallError("Desktop GL only, won't run. Rebuild image")
    progress = progress or (lambda pct: None)
    cancelled = cancelled or (lambda: False)
    opener = opener or urllib.request.urlopen
    url = core_url(core, base, ref)
    final = os.path.join(dest, core + "_libretro.so")
    zpart, spart = os.path.join(dest, ".%s.zip.part" % core), os.path.join(dest, ".%s.so.part" % core)
    try:
        os.makedirs(dest, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "RGOS-core-installer"})
        try:
            resp = opener(req, timeout=20)
        except urllib.error.HTTPError as e:
            raise CoreInstallError(_http_error(e, ref))
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise CoreInstallError("Can't reach the server. Check Wi-Fi in Settings")
        with resp:
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except (TypeError, ValueError, AttributeError):
                total = 0
            if total > MAX_ZIP:
                raise CoreInstallError("Download is too big")
            free = shutil.disk_usage(dest).free
            if total and free < total * 4 + (4 << 20):
                raise CoreInstallError("Not enough free space on the ROMS card")
            got = 0
            with open(zpart, "wb") as out:
                while True:
                    if cancelled():
                        raise CoreInstallError("Cancelled")
                    try:
                        chunk = resp.read(CHUNK)
                    except OSError:
                        raise CoreInstallError("Connection lost. Check Wi-Fi in Settings")
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > MAX_ZIP:
                        raise CoreInstallError("Download is too big")
                    out.write(chunk)
                    if total:
                        progress(min(90, int(got * 90 / total)))
            if total and got < total:
                raise CoreInstallError("Download was cut short")
        wanted = core + "_libretro.so"
        try:
            with zipfile.ZipFile(zpart) as zf:
                info = next((i for i in zf.infolist() if i.filename == wanted), None)
                if info is None:
                    raise CoreInstallError("The download does not contain the core")
                if info.file_size > MAX_SO:
                    raise CoreInstallError("Download is too big")
                if shutil.disk_usage(dest).free < info.file_size + (4 << 20):
                    raise CoreInstallError("Not enough free space on the ROMS card")
                done = 0
                with zf.open(info) as src, open(spart, "wb") as out:
                    while True:
                        if cancelled():
                            raise CoreInstallError("Cancelled")
                        chunk = src.read(CHUNK)
                        if not chunk:
                            break
                        done += len(chunk)
                        if done > MAX_SO:
                            raise CoreInstallError("Download is too big")
                        out.write(chunk)
                        progress(90 + min(9, int(done * 9 / max(1, info.file_size))))
        except zipfile.BadZipFile:
            raise CoreInstallError("The download is damaged")
        _check_elf(spart)
        try:
            os.chmod(spart, 0o755)
        except OSError:
            pass
        os.replace(spart, final)
        progress(100)
        return final
    except OSError as e:
        raise CoreInstallError("Could not write to the ROMS card (%s)" % (e.strerror or "error"))
    finally:
        for p in (zpart, spart):
            try:
                os.remove(p)
            except OSError:
                pass


class Installer:
    """Runs installs on a worker thread; the menu polls snapshot() each frame."""

    def __init__(self, dest, base=None, opener=None, names=None):
        self.dest, self.base, self.opener, self.names = dest, base, opener, names or {}
        self._lock = threading.Lock()
        self._cancel = False
        self._changed = False
        self._verb = "Installed"
        self._s = {"busy": False, "core": "", "pct": 0, "index": 0, "total": 0, "msg": "", "ok": [], "failed": []}

    def snapshot(self):
        with self._lock:
            s = dict(self._s)
            s["ok"], s["failed"] = list(s["ok"]), list(s["failed"])
            return s

    def take_changed(self):
        """True once after a run that installed at least one core."""
        with self._lock:
            c, self._changed = self._changed, False
            return c

    def start(self, cores, reinstall=False):
        """Download cores on a worker thread. reinstall=True is for cores that are already there: they are fetched again and
        replaced (a failed or cancelled download leaves the old file untouched, see download()); only the final message
        differs ("Reinstalled ...")."""
        cores = [c for c in dict.fromkeys(cores) if NAME_RE.match(c) and c not in EXCLUDE]
        with self._lock:
            if self._s["busy"] or not cores:
                return False
            self._cancel = False
            self._verb = "Reinstalled" if reinstall else "Installed"
            self._s.update(busy=True, core=cores[0], pct=0, index=1, total=len(cores), msg="", ok=[], failed=[])
        threading.Thread(target=self._run, args=(cores,), daemon=True).start()
        return True

    def say(self, msg):
        """Show a one line note in the menu header (not while a download runs). Returns False if it was busy."""
        with self._lock:
            if self._s["busy"]:
                return False
            self._s.update(msg=msg, ok=[], failed=[])
            return True

    def cancel(self):
        with self._lock:
            self._cancel = True

    def _set(self, **kw):
        with self._lock:
            self._s.update(kw)

    def _run(self, cores):
        for i, core in enumerate(cores, 1):
            if self._cancel:
                break
            self._set(core=core, pct=0, index=i)
            try:
                download(core, self.dest, self.base, lambda p: self._set(pct=p), lambda: self._cancel, self.opener)
            except CoreInstallError as e:
                with self._lock:
                    self._s["failed"].append((core, str(e)))
                if str(e) == "Cancelled":
                    break
                if str(e).startswith(("Can't reach", "Connection lost")):
                    break
            except Exception as e:
                with self._lock:
                    self._s["failed"].append((core, "Unexpected error: %s" % e))
            else:
                with self._lock:
                    self._s["ok"].append(core)
        with self._lock:
            ok, failed = self._s["ok"], self._s["failed"]
            label = lambda c: self.names.get(c) or c
            if self._cancel:
                msg = "Cancelled" + ((": %d installed" % len(ok)) if ok else "")
            elif failed and not ok:
                msg = "%s: %s" % (label(failed[0][0]), failed[0][1]) if len(cores) == 1 or len(failed) == 1 else failed[0][1]
            elif failed:
                msg = "%d installed, %d failed (%s)" % (len(ok), len(failed), failed[0][1])
            elif len(ok) == 1:
                msg = "%s %s" % (self._verb, label(ok[0]))
            else:
                msg = "%s %d cores" % (self._verb, len(ok))
            self._changed = bool(ok)
            self._s.update(busy=False, core="", pct=0, msg=msg)
