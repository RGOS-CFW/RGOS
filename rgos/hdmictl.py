"""Mini HDMI output for the H700 handhelds (RG34XXSP, RG35XX H, RG35XX SP).

HDMI is selected by the kernel at boot through video=HDMI-A-1:<mode> in
extlinux.conf. The built-in panel remains the fallback when no cable is attached
at boot. This is intentionally boot-time only: it does not hot-switch displays.

Settings: /var/lib/rgos/display.json, {"hdmi": "auto"|"480p"|"720p"|"1080p"}
CLI: hdmictl.py status | set <mode> | boot | extlinux <extlinux.conf> <mode>
"""
import glob
import json
import os
import re
import shutil
import sys

SYS_DRM = os.environ.get("RGOS_SYS_DRM", "/sys/class/drm")
CONF = os.environ.get("RGOS_DISPLAY_CONF", "/var/lib/rgos/display.json")
ASOUND = os.environ.get("RGOS_ASOUND", "/proc/asound")
BOOT_DIR = os.environ.get("RGOS_BOOT_DIR", "/boot")
DEFAULT_MODE = "720p"
MODES = {
    "auto": ("Auto (the TV's own mode)", "", 0, 0),
    "480p": ("480p", "720x480@60", 720, 480),
    "720p": ("720p", "1280x720@60", 1280, 720),
    "1080p": ("1080p", "1920x1080@60", 1920, 1080),
}
ORDER = ("720p", "1080p", "480p", "auto")
DEFAULT_CONNECTOR = "HDMI-A-1"
VIDEO_ARG = re.compile(r"\s+video=HDMI-A-\d+:\S+")


def rd(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def connectors(sys_root=None):
    root = sys_root or SYS_DRM
    out = []
    for d in glob.glob(os.path.join(root, "card[0-9]*-*")):
        name = os.path.basename(d).split("-", 1)[1]
        cid = rd(os.path.join(d, "connector_id"))
        out.append({"name": name, "kind": "hdmi" if name.upper().startswith("HDMI") else "panel",
                    "connected": rd(os.path.join(d, "status")) == "connected",
                    "enabled": rd(os.path.join(d, "enabled")) == "enabled",
                    "id": int(cid) if cid.isdigit() else 0,
                    "modes": [m for m in rd(os.path.join(d, "modes")).splitlines() if m]})
    return sorted(out, key=lambda c: (c["id"], c["name"]))


def hdmi_connector(sys_root=None):
    return next((c for c in connectors(sys_root) if c["kind"] == "hdmi"), None)


def hdmi_active(sys_root=None):
    c = hdmi_connector(sys_root)
    return bool(c and c["connected"] and c["enabled"])


def monitor_index(sys_root=None):
    n = 0
    for c in connectors(sys_root):
        if c["connected"]:
            n += 1
            if c["kind"] == "hdmi":
                return n
    return 0


def get_mode(conf=None):
    try:
        with open(conf or CONF) as f:
            mode = json.load(f).get("hdmi")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_MODE
    return mode if isinstance(mode, str) and mode in MODES else DEFAULT_MODE


def kernel_arg(mode, name=DEFAULT_CONNECTOR):
    value = MODES.get(mode, MODES[DEFAULT_MODE])[1]
    return "video=%s:%s" % (name, value) if value else ""


def extlinux_path(boot_dir=None):
    root = boot_dir or BOOT_DIR
    for path in (os.path.join(root, "extlinux", "extlinux.conf"), os.path.join(root, "extlinux.conf")):
        if os.path.isfile(path):
            return path
    return None


def patch_extlinux_text(text, mode, name=DEFAULT_CONNECTOR):
    arg = kernel_arg(mode, name)

    def fix(match):
        line = VIDEO_ARG.sub("", match.group(0).rstrip())
        return line + (" " + arg if arg else "")
    return re.sub(r"(?im)^[ \t]*append\b[^\r\n]*", fix, text)


def apply_extlinux(mode, path=None, name=DEFAULT_CONNECTOR):
    path = path or extlinux_path()
    if not path:
        return None
    try:
        with open(path, newline="") as f:
            old = f.read()
        if not re.search(r"(?im)^[ \t]*append\b", old):
            return None
        new = patch_extlinux_text(old, mode, name)
        if new == old:
            return False
        backup = path + ".pre-hdmi"
        if not os.path.exists(backup):
            shutil.copyfile(path, backup)
        with open(path + ".new", "w", newline="") as f:
            f.write(new)
            f.flush()
            os.fsync(f.fileno())
        os.replace(path + ".new", path)
        return True
    except OSError:
        return None


def connector_name():
    c = hdmi_connector()
    return c["name"] if c else DEFAULT_CONNECTOR


def set_mode(mode, conf=None, extlinux=None):
    if mode not in MODES:
        return False, False
    changed = apply_extlinux(mode, extlinux, connector_name())
    if changed is None:
        return False, False
    target = conf or CONF
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target + ".tmp", "w") as f:
            json.dump({"hdmi": mode}, f)
        os.replace(target + ".tmp", target)
    except OSError:
        return False, False
    return True, changed


def cycle(step=1, conf=None, extlinux=None):
    current = get_mode(conf)
    return set_mode(ORDER[(ORDER.index(current) + step) % len(ORDER)], conf, extlinux)


def boot_check(conf=None, extlinux=None):
    mode = get_mode(conf)
    path = extlinux or extlinux_path()
    if not path:
        return "no extlinux.conf found"
    result = apply_extlinux(mode, path, connector_name())
    return {None: "could not write extlinux.conf", False: "ok", True: "restored video=%s" % mode}[result]


def audio_hdmi_card(cards_text=None):
    text = cards_text if cards_text is not None else rd(os.path.join(ASOUND, "cards"))
    for idx, cid, desc in re.findall(r"^\s*(\d+)\s+\[([^\]]*)\]\s*:\s*(.*)$", text, re.M):
        if re.search(r"hdmi", cid + " " + desc, re.I):
            return int(idx)
    return None


def audio_device(sys_root=None, cards_text=None):
    if not hdmi_active(sys_root):
        return None
    card = audio_hdmi_card(cards_text)
    if card is None:
        return None
    pcms = [int(m.group(1)) for d in glob.glob(os.path.join(ASOUND, "card%d" % card, "pcm*p"))
            for m in [re.search(r"pcm(\d+)p$", d)] if m]
    return "plughw:%d,%d" % (card, min(pcms) if pcms else 0)


def retroarch_lines(sys_root=None):
    if not hdmi_active(sys_root):
        return []
    idx = monitor_index(sys_root)
    return ['video_fullscreen_x = "0"', 'video_fullscreen_y = "0"', 'video_windowed_fullscreen = "false"',
            'video_monitor_index = "%d"' % idx]


def status_text(sys_root=None, conf=None):
    c = hdmi_connector(sys_root)
    label = MODES[get_mode(conf)][0]
    if not c:
        return "%s   (no HDMI port found by the kernel)" % label
    if not c["connected"]:
        return "%s   (no cable at boot; connect the TV before powering on)" % label
    return "%s   (TV connected%s)" % (label, ", " + c["modes"][0] if c["modes"] else "")


def report(sys_root=None):
    lines = []
    for c in connectors(sys_root):
        lines.append("%s: %s%s, modes: %s" % (c["name"], "connected" if c["connected"] else "disconnected",
                                              " (enabled)" if c["enabled"] else "", " ".join(c["modes"][:6]) or "none"))
    mode = get_mode()
    lines.append("saved mode: %s -> %s" % (mode, kernel_arg(mode) or "no video= argument"))
    lines.append("HDMI active: %s; sound: %s; RetroArch: %s" % (hdmi_active(), audio_device() or "built-in codec",
                                                                 " ".join(retroarch_lines()) or "panel settings"))
    return "\n".join(lines)


def main(argv):
    if len(argv) >= 2 and argv[1] == "status":
        print(report())
    elif len(argv) == 3 and argv[1] == "set":
        ok, changed = set_mode(argv[2])
        print("saved" + (", restart to apply" if changed else "") if ok else "failed (unknown mode, /boot not writable, or no APPEND line in extlinux.conf)")
    elif len(argv) >= 2 and argv[1] == "boot":
        print("hdmi: %s" % boot_check())
        print(report())
    elif len(argv) == 4 and argv[1] == "extlinux":
        print({None: "failed", False: "unchanged", True: "patched"}[apply_extlinux(argv[3], argv[2])])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
