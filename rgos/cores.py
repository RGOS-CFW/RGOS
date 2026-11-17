"""Emulator core tables, kept apart from menu.py so rgos-launch can use them without importing pygame."""
import os


def installed_cores():
    dirs = ("/usr/lib/aarch64-linux-gnu/libretro", "/usr/lib/libretro",
            "/usr/lib/aarch64-linux-gnu/retroarch/cores", "/usr/local/lib/libretro")
    found = set()
    for directory in dirs:
        try:
            for filename in os.listdir(directory):
                if filename.endswith("_libretro.so"):
                    found.add(filename[:-len("_libretro.so")])
        except OSError:
            pass
    return sorted(found)


def default_core(sid):
    return {"gba": "mgba", "gb": "gambatte", "gbc": "gambatte", "nes": "nestopia", "snes": "snes9x", "genesis": "genesis_plus_gx",
            "mastersystem": "genesis_plus_gx", "gamegear": "genesis_plus_gx",
            "sg1000": "genesis_plus_gx", "segacd": "genesis_plus_gx",
            "sega32x": "genesis_plus_gx", "segapico": "genesis_plus_gx",
            "arcade": "fbneo", "neogeo": "fbneo",
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
}


def compatible_cores(sid, cores=None):
    installed = set(installed_cores() if cores is None else cores)
    return [core for core in SYSTEM_CORE_COMPATIBILITY.get(sid, ()) if core in installed]
