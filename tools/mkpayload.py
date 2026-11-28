#!/usr/bin/env python3
"""Build the payload folder that the RG OS first-boot installer (rgos/installer.py) unpacks.

usage: mkpayload.py OUTDIR ID DEVICE COMPONENT [COMPONENT ...]
  OUTDIR     receives manifest.json and one <component id>.tar.gz per component (copied to /rgos-payload on the boot partition)
  ID         build id, [A-Za-z0-9._-]{1,64}
  DEVICE     h700-ddr3, h700-ddr4, rg-rotate or miniloong (the chipset, must match /etc/rgos-chipset on the device)
  COMPONENT  "id|name|SRC_DIR|dest|target|if_missing"
               id          [A-Za-z0-9._-]{1,64}; also the file name of the archive and the name `skip=` in rgos-install.txt uses
               name        shown on the installer screen
               SRC_DIR     the folder whose CONTENTS are archived
               dest        roms (the ROMS partition) or boot (the FAT boot partition)
               target      folder under dest the contents are unpacked into ("" = the root)
               if_missing  optional path under dest; when it already exists the component is skipped (keeps a PortMaster that
                           has updated itself)
Only regular files and folders are archived; symlinks are skipped.
"""
import hashlib
import json
import os
import re
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rgos"))
import installer  # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def pack(src, archive):
    """Write src's contents into archive (tar.gz); returns (file count, uncompressed bytes)."""
    count = size = 0

    def norm(ti):
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        ti.mode = 0o755 if ti.isdir() or ti.mode & 0o111 else 0o644
        return ti

    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT, compresslevel=6) as tf:
        for base, dirs, files in os.walk(src):
            dirs.sort()
            for d in list(dirs):
                full = os.path.join(base, d)
                if os.path.islink(full):
                    print("skipping symlink %s" % full, file=sys.stderr)
                    dirs.remove(d)
                    continue
                tf.add(full, arcname=os.path.relpath(full, src), recursive=False, filter=norm)
            for fn in sorted(files):
                full = os.path.join(base, fn)
                if os.path.islink(full) or not os.path.isfile(full):
                    print("skipping %s (not a regular file)" % full, file=sys.stderr)
                    continue
                if installer.safe_rel(os.path.relpath(full, src)) is None:
                    sys.exit("unsafe file name: %s" % full)
                tf.add(full, arcname=os.path.relpath(full, src), recursive=False, filter=norm)
                count += 1
                size += os.path.getsize(full)
    return count, size


def main(argv):
    if len(argv) < 5:
        sys.exit(__doc__)
    out, bid, device = argv[1:4]
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", bid):
        sys.exit("bad id %r" % bid)
    if device not in installer.DEVICES + installer.CONSOLES:
        sys.exit("unknown device %r (use one of: %s)" % (device, ", ".join(installer.DEVICES)))
    os.makedirs(out, exist_ok=True)
    comps = []
    for spec in argv[4:]:
        parts = spec.split("|")
        if len(parts) != 6:
            sys.exit("bad component %r: need id|name|src|dest|target|if_missing" % spec)
        cid, name, src, dest, target, miss = parts
        if not installer.ID_RE.match(cid):
            sys.exit("bad component id %r" % cid)
        if dest not in installer.DESTS:
            sys.exit("%s: dest must be roms or boot" % cid)
        if target and installer.safe_rel(target) is None:
            sys.exit("%s: unsafe target %r" % (cid, target))
        if miss and installer.safe_rel(miss) is None:
            sys.exit("%s: unsafe if_missing %r" % (cid, miss))
        if not os.path.isdir(src):
            sys.exit("%s: %s is not a folder" % (cid, src))
        archive = os.path.join(out, cid + ".tar.gz")
        count, size = pack(src, archive)
        if count == 0:
            os.remove(archive)
            print("component %s has no files: left out" % cid, file=sys.stderr)
            continue
        comps.append({"id": cid, "name": name or cid, "archive": cid + ".tar.gz", "sha256": sha256(archive), "bytes": size,
                      "dest": dest, "target": target, "if_missing": miss})
        print("payload: %-12s %5d files, %6.1f MiB unpacked, %6.1f MiB packed" % (cid, count, size / 1048576.0, os.path.getsize(archive) / 1048576.0))
    if not comps:
        sys.exit("no component has any files")
    with open(os.path.join(out, installer.MANIFEST), "w") as f:
        json.dump({"format": installer.FORMAT, "id": bid, "device": device, "components": comps}, f, indent=1, sort_keys=True)
    print("payload: %s (id %s, device %s, %d components)" % (out, bid, device, len(comps)))


if __name__ == "__main__":
    main(sys.argv)
