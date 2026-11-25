"""SDL controller mapping for native Linux ports.

The input hub (rgos-input) exposes one virtual pad, "RG OS Gamepad", with a fixed button
layout. SDL ports (including everything PortMaster launches) only treat a joystick as a
game controller when an SDL_GameControllerDB entry matches its GUID, so without one most
ports ignore the pad or see a raw, unlabelled joystick. This module builds that entry.

Button numbers follow SDL's evdev ordering of the hub's key codes:
  0 BTN_SOUTH  1 BTN_EAST  2 BTN_NORTH  3 BTN_WEST  4/5 L1/R1  6/7 L2/R2
  8 select  9 start  10 mode  11/12 L3/R3  13-16 dpad up/down/left/right
which matches config/autoconfig/RG_OS_Gamepad.cfg. Axes 0 and 1 are the left stick: always present,
because "DPAD to joystick" drives them. Axes 2 and 3 (right stick) exist only when analog sticks are
enabled in /etc/rgos/input.json.
"""
import json, os, struct

HUB_NAME = "RG OS Gamepad"
# Must match make_uinput() in rgos-input: bus, vendor, product, version of the virtual pad.
BUS, VENDOR, PRODUCT, VERSION = 0x19, 0x484B, 0x14DF, 0x0100
INPUT_CONF = os.environ.get("RGOS_INPUT_CONF", "/etc/rgos/input.json")
DEVICE_FILE = os.environ.get("RGOS_DEVICE_FILE", "/etc/rgos-device")
USER_DB_NAME = "rgos-gamecontrollerdb.txt"
MAX_USER_BYTES = 256 * 1024
MAX_ENV_BYTES = 48 * 1024

# SDL name -> hub button index. Positional like an Xbox pad: a = bottom, b = right, x = left, y = top.
BUTTONS = (
    ("a", 0), ("b", 1), ("x", 3), ("y", 2),
    ("back", 8), ("start", 9), ("guide", 10),
    ("leftshoulder", 4), ("rightshoulder", 5),
    ("leftstick", 11), ("rightstick", 12),
    ("dpup", 13), ("dpdown", 14), ("dpleft", 15), ("dpright", 16),
    ("lefttrigger", 6), ("righttrigger", 7),
)
LEFT_STICK = (("leftx", 0), ("lefty", 1))
STICKS = LEFT_STICK + (("rightx", 2), ("righty", 3))


def sdl_guid():
    """Linux SDL joystick GUID of the virtual pad (name CRC left at 0, which SDL treats as a wildcard)."""
    return struct.pack("<8H", BUS, 0, VENDOR, 0, PRODUCT, 0, VERSION, 0).hex()


def _load_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def analog_enabled(conf=None, devfile=None):
    """Whether the hub publishes stick axes. Mirrors rgos-input's load_input_conf().

    The hub merges /etc/rgos/input-<device>.json over input.json, and the build writes the analog flag
    only into the per-device file, so reading input.json alone left ports without stick axes. An explicit
    conf (tests) is read on its own.
    """
    if conf:
        return bool(_load_json(conf).get("analog", False))
    out = _load_json(INPUT_CONF)
    try:
        with open(devfile or DEVICE_FILE) as f:
            dev = f.read().strip()
        out.update(_load_json(os.path.join(os.path.dirname(INPUT_CONF), "input-%s.json" % dev)))
    except OSError:
        pass
    return bool(out.get("analog", False))


def stick_count(conf=None, devfile=None):
    """1 for a one-stick device (\"sticks\": 1 in input-<device>.json), else 2."""
    if conf:
        return 1 if _load_json(conf).get("sticks") == 1 else 2
    out = _load_json(INPUT_CONF)
    try:
        with open(devfile or DEVICE_FILE) as f:
            dev = f.read().strip()
        out.update(_load_json(os.path.join(os.path.dirname(INPUT_CONF), "input-%s.json" % dev)))
    except OSError:
        pass
    return 1 if out.get("sticks") == 1 else 2


def mapping_line(analog=False, sticks=2):
    buttons = [kv for kv in BUTTONS if not (sticks == 1 and kv[0] == "rightstick")]
    parts = [sdl_guid(), HUB_NAME] + ["%s:b%d" % kv for kv in buttons]
    parts += ["%s:a%d" % kv for kv in (STICKS if analog and sticks != 1 else LEFT_STICK)]
    parts.append("platform:Linux")
    return ",".join(parts)


def user_lines(*paths):
    """Mapping lines from user override files (SDL db format). Later files and lines win."""
    out = []
    for path in paths:
        if not path:
            continue
        try:
            if os.path.getsize(path) > MAX_USER_BYTES:
                continue
            with open(path, "r", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and line.count(",") >= 2:
                out.append(line)
    return out


def user_files(roms_root, port_dir=None):
    files = [os.path.join(roms_root, "ports", USER_DB_NAME), os.path.join(roms_root, "roms", "ports", USER_DB_NAME)]
    if port_dir:
        files.append(os.path.join(port_dir, USER_DB_NAME))
    return files


def build_db(analog=False, extra=(), sticks=2):
    lines = ["# RG OS generated controller mappings (SDL_GameControllerDB format)",
             "# Override a mapping by putting a line with the same GUID in %s" % USER_DB_NAME,
             mapping_line(analog, sticks)]
    lines.extend(extra)
    return "\n".join(lines) + "\n"


def write_db(run_dir, text):
    """Write the db under run_dir; returns its path, or '' if it could not be written."""
    path = os.path.join(run_dir, "gamecontrollerdb.txt")
    try:
        os.makedirs(run_dir, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, path)
        return path
    except OSError:
        return ""


def env_for(base_env, run_dir, roms_root, port_dir=None, conf=None):
    """SDL environment variables that make ports see the hub pad as a mapped game controller.

    A mapping the user already exported in SDL_GAMECONTROLLERCONFIG is kept and wins over ours.
    """
    extra = user_lines(*user_files(roms_root, port_dir))
    text = build_db(analog_enabled(conf), extra, stick_count(conf))
    lines, cfg, size = text.splitlines()[2:], [], 0  # drop the comment header, keep mapping + user lines
    for line in lines:  # one env string over 128 KiB makes every exec() fail with E2BIG; the file keeps all lines
        size += len(line) + 1
        if cfg and size > MAX_ENV_BYTES:
            break
        cfg.append(line)
    cfg = "\n".join(cfg)
    existing = (base_env.get("SDL_GAMECONTROLLERCONFIG") or "").strip()
    env = {"SDL_GAMECONTROLLERCONFIG": cfg + ("\n" + existing if existing else "")}
    path = write_db(run_dir, text)
    if path:
        env["SDL_GAMECONTROLLERCONFIG_FILE"] = path
    return env
