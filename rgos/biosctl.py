#!/usr/bin/env python3
import hashlib
import os

MD5_MAX_BYTES = 16 * 1024 * 1024
_md5_cache = {}

_PSX_REQ = ("mednafen_psx", "mednafen_psx_hw", "swanstation")

BIOS = {
    "gba": [
        ("gba_bios.bin", "Game Boy Advance BIOS", ("a860e8c0b6d573d191e4ec7db1b1e4f6",), ("gpsp",), ""),
    ],
    "gb": [
        ("gb_bios.bin", "Game Boy boot ROM", ("32fbbd84168d3482956eb3c5051637f5",), (), ""),
        ("gbc_bios.bin", "Game Boy Color boot ROM", ("dbfce9db9deaa2567f6a84fde55f9680",), (), ""),
    ],
    "gbc": [
        ("gbc_bios.bin", "Game Boy Color boot ROM", ("dbfce9db9deaa2567f6a84fde55f9680",), (), ""),
        ("gb_bios.bin", "Game Boy boot ROM", ("32fbbd84168d3482956eb3c5051637f5",), (), ""),
    ],
    "nes": [
        ("disksys.rom", "Famicom Disk System BIOS (only for .fds games)", ("ca30b50f880eb660a320674ed365ef7a",), (), ""),
    ],
    "mastersystem": [
        ("bios_E.sms", "Master System BIOS (Europe)", ("",), (), ""),
        ("bios_U.sms", "Master System BIOS (USA)", ("",), (), ""),
        ("bios_J.sms", "Master System BIOS (Japan)", ("24a519c53f67b00640d0048ef7089105",), (), ""),
    ],
    "gamegear": [
        ("bios.gg", "Game Gear BIOS", ("672e104c3be3a238301aceffc3b23fd6",), (), ""),
    ],
    "segacd": [
        ("bios_CD_U.bin", "Sega CD BIOS (USA)", ("2efd74e3232ff260e371b99f84024f7f",), "*", "segacd"),
        ("bios_CD_E.bin", "Mega-CD BIOS (Europe)", ("e66fa1dc5820d254611fdcdba0662372",), "*", "segacd"),
        ("bios_CD_J.bin", "Mega-CD BIOS (Japan)", ("278a9397d192149e84e820ac621a8edd",), "*", "segacd"),
    ],
    "atari5200": [
        ("5200.rom", "Atari 5200 BIOS", ("281f20ea4320404ec820fb7ec0693b38",), "*", ""),
    ],
    "atari7800": [
        ("7800 BIOS (U).rom", "Atari 7800 BIOS (USA)", ("0763f1ffb006ddbe32e52d497ee848ae",), (), ""),
        ("7800 BIOS (E).rom", "Atari 7800 BIOS (Europe)", ("397bb566584be7b9764e7a68974c4263",), (), ""),
    ],
    "neogeo": [
        ("neogeo.zip", "Neo Geo BIOS set (leave it zipped)", ("",), "*", ""),
    ],
    "psx": [
        ("scph5501.bin", "PlayStation BIOS (USA)", ("490f666e1afb15b7362b406ed1cea246",), _PSX_REQ, "psx"),
        ("scph5502.bin", "PlayStation BIOS (Europe)", ("32736f17079d0b2b7024407c39bd3050",), _PSX_REQ, "psx"),
        ("scph5500.bin", "PlayStation BIOS (Japan)", ("8dd7d5296a650fac7319bce665a6a53c",), _PSX_REQ, "psx"),
    ],
    "gc": [
        ("dolphin-emu/Sys/GC/USA/IPL.bin", "GameCube boot logo BIOS (USA)", ("",), (), ""),
        ("dolphin-emu/Sys/GC/EUR/IPL.bin", "GameCube boot logo BIOS (Europe)", ("",), (), ""),
        ("dolphin-emu/Sys/GC/JAP/IPL.bin", "GameCube boot logo BIOS (Japan)", ("",), (), ""),
    ],
}

OK, DIFFERS, CASE, MISSING, OPTIONAL = "ok", "differs", "case", "missing", "optional"
FOUND = (OK, DIFFERS, CASE)


def needs_bios(sid):
    return bool(BIOS.get(sid))


def _find(bios_dir, rel):
    exact = os.path.join(bios_dir, *rel.split("/"))
    if os.path.isfile(exact):
        return exact, OK
    cur = bios_dir
    for part in rel.split("/"):
        try:
            names = os.listdir(cur)
        except OSError:
            return "", MISSING
        hit = part if part in names else next((n for n in sorted(names) if n.lower() == part.lower()), None)
        if hit is None:
            return "", MISSING
        cur = os.path.join(cur, hit)
    return (cur, CASE) if os.path.isfile(cur) else ("", MISSING)


def md5_of(path):
    try:
        st = os.stat(path)
        if st.st_size > MD5_MAX_BYTES:
            return ""
        key = (path, st.st_size, st.st_mtime_ns)
        if key in _md5_cache:
            return _md5_cache[key]
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if len(_md5_cache) > 256:
            _md5_cache.clear()
        _md5_cache[key] = h.hexdigest()
        return _md5_cache[key]
    except OSError:
        return ""


def is_required(entry, core):
    req = entry[3]
    return req == "*" or (isinstance(req, tuple) and bool(core) and core in req)


def check_file(entry, bios_dirs):
    rel, _desc, md5s, _req, _grp = entry
    best = ("", MISSING)
    for d in bios_dirs:
        path, st = _find(d, rel)
        if st == OK:
            best = (path, OK)
            break
        if st == CASE and best[1] == MISSING:
            best = (path, CASE)
    path, st = best
    if st == OK:
        known = [m for m in md5s if m]
        if known and md5_of(path) not in known:
            return DIFFERS, path
    return st, path


def check_system(sid, core, bios_dirs):
    out = []
    entries = BIOS.get(sid, [])
    found = [check_file(e, bios_dirs) for e in entries]
    satisfied = {e[4] for e, (st, _p) in zip(entries, found) if e[4] and st in FOUND}
    for e, (st, path) in zip(entries, found):
        req = is_required(e, core)
        if st == MISSING:
            st = MISSING if (req and e[4] not in satisfied) else OPTIONAL
        out.append({"file": e[0], "desc": e[1], "status": st, "path": path, "required": req})
    return out


def check_all(systems, core_of, bios_dirs):
    rows, summ = [], {"missing": 0, "optional": 0, "ok": 0, "systems": 0}
    for sid, name in systems:
        if not needs_bios(sid):
            continue
        core = core_of(sid)
        res = check_system(sid, core, bios_dirs)
        rows.append((sid, name, core, res))
        summ["systems"] += 1
        for r in res:
            if r["status"] == MISSING:
                summ["missing"] += 1
            elif r["status"] == OPTIONAL:
                summ["optional"] += 1
            else:
                summ["ok"] += 1
    return rows, summ


def display_dir(bios_dir, roms_root, label="ROMS"):
    try:
        rel = os.path.relpath(bios_dir, roms_root)
    except ValueError:
        return bios_dir
    return label + "/" + rel.replace(os.sep, "/") if not rel.startswith("..") else bios_dir


def build_lines(rows, show_all, where):
    lines = []
    for sid, name, core, res in rows:
        bad = [r for r in res if r["status"] in (MISSING, OPTIONAL, CASE, DIFFERS)]
        n_miss = sum(r["status"] == MISSING for r in res)
        if n_miss:
            tag = "%d missing" % n_miss
        elif any(r["status"] == CASE for r in res):
            tag = "rename needed"
        elif any(r["status"] == OPTIONAL for r in res):
            tag = "optional files missing"
        else:
            tag = "all present"
        lines.append(("head", name, tag))
        for r in (res if show_all else bad):
            kind = {MISSING: "miss", OPTIONAL: "opt", OK: "ok", DIFFERS: "diff", CASE: "case"}[r["status"]]
            right = {MISSING: "MISSING", OPTIONAL: "optional", OK: "OK", DIFFERS: "other version", CASE: "wrong case"}[r["status"]]
            lines.append((kind, r["file"].split("/")[-1] + "  " + r["desc"], right))
            if r["status"] in (MISSING, OPTIONAL):
                sub = r["file"].rsplit("/", 1)[0] + "/" if "/" in r["file"] else ""
                lines.append(("path", "put in  %s/%s" % (where, sub), ""))
            elif r["status"] == CASE:
                lines.append(("path", "rename to  %s" % r["file"].split("/")[-1], ""))
    return lines
