"""Run any native Linux/ARM program as a port.

Pure standard library (no pygame), shared by the menu (what shows up in Ports) and rgos-launch (how it is started).

What it solves
  * Ports are often a bare executable, not a .sh: the menu recognises them by their ELF header, so the name
    ("game", "game.aarch64", "game.bin", "Game.arm64") does not matter.
  * The ROMS card is FAT/exFAT, which has no execute bit (or is mounted noexec). A binary that cannot be exec'd is
    started through its dynamic loader instead ("ld.so program"), which only needs read access.
  * Ports ship their own .so files (lib/, libs/, libs.aarch64/ ...): those folders are put on LD_LIBRARY_PATH.
  * 32-bit ARM (armhf) ports run when an armhf loader exists, either in the image or shipped with the port.
  * A missing library or the wrong CPU is reported by name instead of "exited with an error (code 127)".
"""
import os, struct, subprocess

EM_386, EM_ARM, EM_X86_64, EM_AARCH64, EM_RISCV = 3, 40, 62, 183, 243
ET_EXEC, ET_DYN = 2, 3
PT_INTERP = 3
MACHINES = {EM_386: "x86 (32-bit)", EM_ARM: "ARM (32-bit)", EM_X86_64: "x86-64", EM_AARCH64: "ARM64", EM_RISCV: "RISC-V"}

# Files in a ports folder that are never programs, even if one sneaks an ELF header in.
SKIP_EXT = (".so", ".txt", ".md", ".json", ".cfg", ".ini", ".conf", ".log", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".7z",
            ".tar", ".gz", ".xz", ".pdf", ".dat", ".pak", ".wav", ".ogg", ".mp3", ".mp4", ".bak", ".tmp", ".py", ".lua",
            ".xml", ".csv", ".db", ".sav", ".srm", ".state", ".sf2", ".ttf", ".otf", ".dll", ".exe", ".bat")

LOADERS = {
    EM_AARCH64: ("/lib/ld-linux-aarch64.so.1", "/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1",
                 "/lib64/ld-linux-aarch64.so.1", "/lib/ld-musl-aarch64.so.1"),
    EM_ARM: ("/lib/ld-linux-armhf.so.3", "/lib/arm-linux-gnueabihf/ld-linux-armhf.so.3", "/lib/ld-linux.so.3",
             "/lib/ld-musl-armhf.so.1"),
}
# Loader file names a port may carry itself.
LOADER_NAMES = {EM_AARCH64: ("ld-linux-aarch64.so.1", "ld-musl-aarch64.so.1"),
                EM_ARM: ("ld-linux-armhf.so.3", "ld-linux.so.3", "ld-musl-armhf.so.1")}

# Sub folders ports use for their own libraries. Architecture-specific names are only used for a matching binary.
LIB_DIRS_COMMON = ("", "lib", "libs", "lib64", "lib/gl4es", "libs/gl4es")
LIB_DIRS_ARCH = {EM_AARCH64: ("lib.aarch64", "libs.aarch64", "lib/aarch64", "libs/aarch64", "lib/aarch64-linux-gnu",
                              "lib64/aarch64", "aarch64/lib", "aarch64/libs", "aarch64"),
                 EM_ARM: ("lib.armhf", "libs.armhf", "lib32", "lib/armhf", "libs/armhf", "lib/arm-linux-gnueabihf",
                          "lib.arm", "libs.arm", "armhf/lib", "armhf/libs", "armhf")}
HOST = EM_AARCH64


def read_elf(path):
    """Header facts of an ELF file, or None when it is not one. {bits, machine, type, interp}."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
            if len(head) < 52 or head[:4] != b"\x7fELF" or head[5] not in (1, 2):
                return None
            bits = 32 if head[4] == 1 else 64
            end = "<" if head[5] == 1 else ">"
            etype, machine = struct.unpack_from(end + "HH", head, 16)
            if bits == 64:
                phoff, = struct.unpack_from(end + "Q", head, 32)
                phentsize, phnum = struct.unpack_from(end + "HH", head, 54)
            else:
                phoff, = struct.unpack_from(end + "I", head, 28)
                phentsize, phnum = struct.unpack_from(end + "HH", head, 42)
            interp = ""
            if phoff and phentsize and 0 < phnum < 256:
                f.seek(phoff)
                table = f.read(phentsize * phnum)
                for i in range(phnum):
                    ent = table[i * phentsize:(i + 1) * phentsize]
                    if len(ent) < phentsize:
                        break
                    if struct.unpack_from(end + "I", ent, 0)[0] != PT_INTERP:
                        continue
                    if bits == 64:
                        off, size = struct.unpack_from(end + "QQ", ent, 8)[0], struct.unpack_from(end + "Q", ent, 32)[0]
                    else:
                        off, size = struct.unpack_from(end + "I", ent, 4)[0], struct.unpack_from(end + "I", ent, 16)[0]
                    f.seek(off)
                    interp = f.read(min(size, 256)).split(b"\0")[0].decode("utf-8", "replace")
                    break
            return {"bits": bits, "machine": machine, "type": etype, "interp": interp}
    except (OSError, struct.error):
        return None


def machine_name(machine):
    return MACHINES.get(machine, "machine %d" % machine)


def shebang(path):
    """Interpreter line of a script ('#!/bin/sh' -> ['/bin/sh']), or None."""
    try:
        with open(path, "rb") as f:
            first = f.readline(256)
    except OSError:
        return None
    if not first.startswith(b"#!"):
        return None
    parts = first[2:].decode("utf-8", "replace").strip().split()
    return parts or None


def is_port_binary(path):
    """True for a runnable ARM / ARM64 program: an executable (or static) ELF that is not a shared library."""
    name = os.path.basename(path).lower()
    if name.startswith(".") or ".so." in name or name.endswith(SKIP_EXT):
        return False
    info = read_elf(path)
    if not info or info["machine"] not in (EM_AARCH64, EM_ARM):
        return False
    return info["type"] in (ET_EXEC, ET_DYN)


def _isdir(p):
    return os.path.isdir(p)


def lib_dirs(binary, info=None, extra=()):
    """Folders next to the program (and shared ones) that hold its libraries, existing ones only, in search order."""
    info = info or read_elf(binary) or {}
    base = os.path.dirname(os.path.abspath(binary))
    names = list(LIB_DIRS_ARCH.get(info.get("machine"), ())) + list(LIB_DIRS_COMMON)
    out = []
    for n in names:
        d = os.path.normpath(os.path.join(base, n))
        if _isdir(d) and d not in out:
            out.append(d)
    for d in extra:
        if d and _isdir(d) and d not in out:
            out.append(d)
    return out


def find_loader(info, dirs=()):
    """Dynamic loader for the program: the one it asks for, a system one for its CPU, or one the port carries."""
    if not info:
        return ""
    cands = []
    if info.get("interp"):
        cands.append(info["interp"])
    cands.extend(LOADERS.get(info["machine"], ()))
    for p in cands:
        if os.path.isfile(p):
            return p
    for d in dirs:
        for n in LOADER_NAMES.get(info["machine"], ()):
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return ""


def can_exec(path):
    return os.access(path, os.X_OK)


def make_executable(path):
    """Try to give the file its execute bit (ext4 / ROMS partitions that keep modes). True if it can now be exec'd."""
    if can_exec(path):
        return True
    try:
        os.chmod(path, os.stat(path).st_mode | 0o111)
    except OSError:
        return False
    return can_exec(path)


def plan(path, extra_lib_dirs=(), chmod=True):
    """How to start a file as a port.

    Returns {"cmd": [...], "env": {...}, "error": "", "title": "", "note": ""}. On error "cmd" is empty and
    "title" / "error" are ready for show_error().
    """
    res = {"cmd": [], "env": {}, "error": "", "title": "", "note": ""}
    info = read_elf(path)
    if info is None:
        sb = shebang(path)
        if sb:
            interp = sb[0]
            if os.path.basename(interp) == "env" and len(sb) > 1:
                interp = sb[1]
            exe = interp if os.path.isabs(interp) and os.path.isfile(interp) else None
            if exe is None:
                import shutil
                exe = shutil.which(os.path.basename(interp))
            if not exe:
                res.update(title="RG OS: script interpreter missing",
                           error="%s needs '%s', which this image does not have." % (os.path.basename(path), interp))
                return res
            res["cmd"] = [exe, path]
            return res
        res.update(title="RG OS: not a Linux program",
                   error="%s is neither an executable nor a script.\nPorts must be ARM64 (aarch64) or 32-bit ARM Linux programs." % os.path.basename(path))
        return res
    if info["machine"] not in (EM_AARCH64, EM_ARM):
        res.update(title="RG OS: wrong CPU for this port",
                   error="%s is built for %s; this device is ARM64.\nGet the aarch64 (arm64) build of the port." % (os.path.basename(path), machine_name(info["machine"])))
        return res
    dirs = lib_dirs(path, info, extra_lib_dirs)
    loader = find_loader(info, dirs)
    if info["interp"] and not loader:
        res.update(title="RG OS: %s port needs a loader this image lacks" % machine_name(info["machine"]),
                   error="%s wants %s.\nPut the matching loader and libraries in a lib folder next to the port%s." % (
                       os.path.basename(path), info["interp"],
                       " (armhf libs: libs.armhf/)" if info["machine"] == EM_ARM else ""))
        return res
    if dirs:
        res["env"]["LD_LIBRARY_PATH"] = ":".join(dirs)
    if chmod and make_executable(path) and (info["machine"] == HOST or loader):
        # a 32-bit program whose interpreter path does not exist cannot be exec'd even with the bit set
        if not info["interp"] or os.path.isfile(info["interp"]):
            res["cmd"] = [path]
            return res
    if loader:
        res["cmd"] = [loader, path]
        res["note"] = "started through %s (no execute permission on this card)" % loader
        return res
    res.update(title="RG OS: native port is not executable",
               error="%s has no execute permission and no loader was found to start it.\nMake it executable or provide a .sh launcher." % os.path.basename(path))
    return res


def missing_libs(path, env=None, extra_lib_dirs=(), timeout=15):
    """Shared libraries the program cannot find ([] when all resolve or the check is not possible)."""
    info = read_elf(path)
    if not info or not info["interp"]:
        return []
    dirs = lib_dirs(path, info, extra_lib_dirs)
    loader = find_loader(info, dirs)
    if not loader:
        return []
    e = dict(env or os.environ)
    if dirs:
        e["LD_LIBRARY_PATH"] = ":".join(dirs + ([e["LD_LIBRARY_PATH"]] if e.get("LD_LIBRARY_PATH") else []))
    try:
        out = subprocess.run([loader, "--list", path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True, timeout=timeout, env=e).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({l.split("=>")[0].strip() for l in out.splitlines() if "not found" in l})
