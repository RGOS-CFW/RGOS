"""Emulator core tables, kept apart from menu.py so rgos-launch can use them without importing pygame."""
import os


def user_core_dir():
    """Where the Core Installer puts downloaded cores: <ROMS>/cores (on the ROMS card, so they survive updates)."""
    return os.path.join(os.environ.get("RGOS_ROMS", "/media/roms"), "cores")


# Standalone emulators: not libretro cores but programs RG OS starts itself. They appear in the Emulators list under a
# pseudo-core name and count as "installed" when their executable is found. {pseudo-core: executable name}
STANDALONE = {"flycast_standalone": "flycast"}


def standalone_dirs():
    env = os.environ.get("RGOS_STANDALONE_DIRS")
    if env:
        return env.split(":")
    return ["/usr/local/bin", "/usr/bin", "/opt/flycast", os.path.join(user_core_dir(), "standalone")]


def standalone_path(core, dirs=None):
    """Full path of a standalone emulator's executable, or "" when it is not installed (or is not a standalone name)."""
    exe = STANDALONE.get(core)
    if not exe:
        return ""
    for d in (standalone_dirs() if dirs is None else dirs):
        p = os.path.join(d, exe)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return ""


def installed_cores():
    dirs = ("/usr/lib/aarch64-linux-gnu/libretro", "/usr/lib/libretro",
            "/usr/lib/aarch64-linux-gnu/retroarch/cores", "/usr/local/lib/libretro", user_core_dir())
    found = set()
    for directory in dirs:
        try:
            for filename in os.listdir(directory):
                if filename.endswith("_libretro.so"):
                    found.add(filename[:-len("_libretro.so")])
        except OSError:
            pass
    found.update(name for name in STANDALONE if standalone_path(name))
    return sorted(found)


def default_core(sid):
    return {"gba": "mgba", "gb": "gambatte", "gbc": "gambatte", "nes": "nestopia", "snes": "snes9x", "genesis": "genesis_plus_gx",
            "mastersystem": "genesis_plus_gx", "gamegear": "genesis_plus_gx",
            "sg1000": "genesis_plus_gx", "segacd": "genesis_plus_gx",
            "sega32x": "genesis_plus_gx", "segapico": "genesis_plus_gx",
            "dreamcast": "flycast", "saturn": "yabasanshiro", "n64": "mupen64plus_next",
            "arcade": "fbneo", "neogeo": "fbneo", "pico8": "fake08",
            "atari2600": "stella2014", "atari5200": "atari800", "atari7800": "prosystem",
            "ngp": "mednafen_ngp", "ngpc": "mednafen_ngp", "psx": "pcsx_rearmed", "gc": "dolphin", "ws": "mednafen_wswan", "wsc": "mednafen_wswan"}.get(sid, "")


SYSTEM_CORE_COMPATIBILITY = {
    "gba": ("mgba", "gpsp", "vbam", "mednafen_gba"),
    "gb": ("gambatte", "sameboy", "gearboy", "mgba", "vbam", "mednafen_gb"),
    "gbc": ("gambatte", "sameboy", "gearboy", "mgba", "vbam", "mednafen_gb"),
    "nes": ("nestopia", "fceumm", "quicknes", "mesen", "mesen_s"),
    "snes": ("snes9x", "snes9x2010", "bsnes", "bsnes_hd_beta", "bsnes2014_accuracy", "bsnes2014_balanced", "bsnes2014_performance", "bsnes_mercury_accuracy", "bsnes_mercury_balanced", "bsnes_mercury_performance"),
    "genesis": ("genesis_plus_gx", "picodrive"),
    "mastersystem": ("genesis_plus_gx", "picodrive"),
    "gamegear": ("genesis_plus_gx", "picodrive"),
    "sg1000": ("genesis_plus_gx",),
    "segacd": ("genesis_plus_gx", "picodrive"),
    "sega32x": ("genesis_plus_gx", "picodrive"),
    "segapico": ("genesis_plus_gx",),
    "dreamcast": ("flycast", "flycast_standalone"),
    "saturn": ("yabasanshiro", "yabause", "mednafen_saturn"),
    "n64": ("mupen64plus_next", "parallel_n64"),
    "atari2600": ("stella2014", "stella"),
    "atari5200": ("atari800",),
    "atari7800": ("prosystem",),
    "ngp": ("mednafen_ngp", "race"),
    "ngpc": ("mednafen_ngp", "race"),
    "psx": ("pcsx_rearmed", "mednafen_psx", "mednafen_psx_hw", "swanstation"),
    "gc": ("dolphin",),
    "ws": ("mednafen_wswan",),
    "wsc": ("mednafen_wswan",),
    "arcade": ("fbneo",),
    "neogeo": ("fbneo",),
    "pico8": ("fake08", "retro8"),
}


def compatible_cores(sid, cores=None):
    installed = set(installed_cores() if cores is None else cores)
    return [core for core in SYSTEM_CORE_COMPATIBILITY.get(sid, ()) if core in installed]
