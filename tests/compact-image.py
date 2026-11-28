#!/usr/bin/env python3
"""Shrink a finished RG OS SD card image to the smallest size that still holds everything.

The stock ROCKNIX image has a fixed, oversized FAT boot partition (that is why every image used to be ~2.2 GB no matter how
small the RG OS SYSTEM file was). This tool

  1. measures what is really on the boot partition (partition 1),
  2. builds a new FAT32 file system just big enough for it (+ headroom), with the same label and volume ID,
  3. copies everything over, and
  4. lays the image out again: whatever sits before partition 1 (U-Boot / SPL / idbloader / the partition table area) is copied
     as it is, partition 1 shrinks, and the partitions that follow it (STORAGE, 'uboot' on the RG Rotate, ...) are moved down
     so that they follow it directly. The partition table is rewritten and the file is cut off after the last partition.

The ROMS partition is not in the image: RG OS creates it on the first boot in the free space after partition 2
(rgos/rgos-roms), so a smaller image only means a smaller download and a smaller file to write.

usage: compact-image.py IMAGE [--headroom-mb N] [--label NAME]
  --headroom-mb N   free space left on the boot partition (default 64). Offline updates (rgos-update) stage the new SYSTEM
                    next to the old one, so install updates by tar only if N is about the size of SYSTEM; reflashing needs none.
Needs root (losetup, mount) plus sfdisk, mkfs.vfat and (optional) fsck.vfat on the build machine.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

MIB = 1 << 20
ALIGN = 2048
FAT32_MIN_CLUSTERS = 65525


def run(*cmd, check=True, capture=False, stdin=None):
    r = subprocess.run(cmd, check=False, text=True, input=stdin,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.STDOUT if capture else None)
    if check and r.returncode != 0:
        raise SystemExit("command failed (%d): %s\n%s" % (r.returncode, " ".join(cmd), r.stdout or ""))
    return r.stdout if capture else r.returncode


def align_up(n, a):
    return (n + a - 1) // a * a


def read_table(img):
    d = json.loads(run("sfdisk", "-J", img, capture=True))["partitiontable"]
    d["sectorsize"] = int(d.get("sectorsize", 512))
    for p in d["partitions"]:
        node = p["node"]
        suffix = node[len(img):] if node.startswith(img) else re.search(r"(\d+)$", node).group(1)
        p["num"] = int(suffix.lstrip("p"))
    return d


def tree_bytes(root, cluster):
    """Space the files need on a FAT volume whose clusters are `cluster` bytes (every file and directory rounds up)."""
    total = 0
    for dp, dn, fn in os.walk(root):
        total += cluster
        for f in fn:
            sz = os.lstat(os.path.join(dp, f)).st_size
            total += align_up(sz, cluster) if sz else 0
        total += align_up(32 * 3 * (len(fn) + len(dn)), cluster)
    return total


def pick_geometry(used, headroom):
    """Return (fs_bytes, sectors_per_cluster). Smaller clusters waste less; FAT32 needs >= 65525 clusters."""
    for spc in (8, 4, 2, 1):
        cluster = spc * 512
        need = used_for(used, cluster) + headroom
        fat = 2 * 4 * (need // cluster + 2)
        size = align_up(need + fat + 64 * 512 + 2 * MIB, MIB)
        if size // cluster >= FAT32_MIN_CLUSTERS + 64:
            return size, spc
    return align_up(FAT32_MIN_CLUSTERS * 512 + 4 * MIB, MIB), 1


def used_for(used, cluster):
    return used[cluster] if isinstance(used, dict) else used


def copy_range(src, dst, src_off, dst_off, length, chunk=MIB):
    """Copy bytes between open files, skipping all-zero chunks so the destination stays sparse."""
    zero = bytes(chunk)
    src.seek(src_off)
    done = 0
    while done < length:
        n = min(chunk, length - done)
        buf = src.read(n)
        if len(buf) != n:
            raise SystemExit("short read while copying (image truncated?)")
        if buf != zero[:n]:
            dst.seek(dst_off + done)
            dst.write(buf)
        done += n


def plan_layout(parts, new_p1_sectors, label):
    """New (partition, start, size) list and the total image size in sectors.

    Partitions that start before partition 1 stay where they are, partition 1 keeps its start and gets the new size, and the
    partitions after it follow directly (1 MiB aligned), in their old order and with their old sizes."""
    parts = sorted(parts, key=lambda p: p["start"])
    p1 = next(p for p in parts if p["num"] == 1)
    layout = [(p, p["start"], p["size"]) for p in parts if p["start"] < p1["start"]]
    layout.append((p1, p1["start"], new_p1_sectors))
    cursor = p1["start"] + new_p1_sectors
    for p in parts:
        if p["start"] > p1["start"]:
            start = align_up(cursor, ALIGN)
            layout.append((p, start, p["size"]))
            cursor = start + p["size"]
    end = max(s + z for _, s, z in layout)
    total = align_up(end + 34, ALIGN) if label == "gpt" else end
    return layout, total


def sfdisk_script(tab, layout):
    """sfdisk input that recreates the old table (label id, GUIDs, names, flags) with the new start/size values."""
    label = tab["label"]
    lines = ["label: %s" % label]
    if tab.get("id"):
        lines.append("label-id: %s" % tab["id"])
    if label == "gpt" and tab.get("firstlba"):
        lines.append("first-lba: %s" % tab["firstlba"])
    lines += ["unit: sectors", ""]
    for p, start, size in sorted(layout, key=lambda x: x[0]["num"]):
        f = ["start=%d" % start, "size=%d" % size, "type=%s" % p["type"]]
        if label == "gpt":
            if p.get("uuid"):
                f.append("uuid=%s" % p["uuid"])
            if p.get("name") is not None:
                f.append('name="%s"' % p["name"].replace('"', ""))
            if p.get("attrs"):
                f.append('attrs="%s"' % p["attrs"])
        elif p.get("bootable"):
            f.append("bootable")
        lines.append(", ".join(f))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--headroom-mb", type=int, default=64)
    ap.add_argument("--label", default=None)
    a = ap.parse_args()
    img = os.path.abspath(a.image)
    if os.geteuid() != 0:
        sys.exit("compact-image.py needs root (losetup / mount)")
    for t in ("sfdisk", "mkfs.vfat", "losetup", "mount", "umount", "blkid"):
        if not shutil.which(t):
            sys.exit("missing tool: %s (apt install dosfstools fdisk util-linux)" % t)

    tab = read_table(img)
    ss, label = tab["sectorsize"], tab["label"]
    if label not in ("dos", "gpt"):
        sys.exit("unsupported partition table '%s'" % label)
    parts = sorted(tab["partitions"], key=lambda p: p["start"])
    p1 = next((p for p in parts if p["num"] == 1), None)
    if p1 is None:
        sys.exit("the image has no partition 1")
    before = [p for p in parts if p["start"] < p1["start"]]
    old_total = os.path.getsize(img)
    print("==> compacting %s (%d MiB, %s, %d partitions)" % (os.path.basename(img), old_total // MIB, label, len(parts)))

    work = tempfile.mkdtemp(prefix="rgos-compact-", dir=os.path.dirname(img))
    loop = mnt_old = mnt_new = fat = None
    try:
        loop = run("losetup", "-Pfr", "--show", img, capture=True).strip()
        p1dev = "%sp1" % loop
        old_label = run("blkid", "-s", "LABEL", "-o", "value", p1dev, capture=True, check=False).strip()
        old_uuid = run("blkid", "-s", "UUID", "-o", "value", p1dev, capture=True, check=False).strip()
        fstype = run("blkid", "-s", "TYPE", "-o", "value", p1dev, capture=True, check=False).strip()
        if fstype != "vfat":
            sys.exit("partition 1 is '%s', not FAT: nothing to compact" % fstype)
        lbl = a.label or old_label or "RGOS"
        mnt_old = os.path.join(work, "old")
        os.makedirs(mnt_old)
        run("mount", "-o", "ro", p1dev, mnt_old)

        used = {spc * 512: tree_bytes(mnt_old, spc * 512) for spc in (8, 4, 2, 1)}
        headroom = a.headroom_mb * MIB
        fs_bytes, spc = pick_geometry(used, headroom)
        if fs_bytes >= p1["size"] * ss:
            print("   the boot partition is already as small as it gets; leaving the image alone")
            return 0
        print("   boot partition content %d MiB -> new FAT32 %d MiB (%d-byte clusters, %d MiB headroom)"
              % (used[spc * 512] // MIB, fs_bytes // MIB, spc * 512, a.headroom_mb))

        fat = os.path.join(work, "boot.fat")
        with open(fat, "wb") as f:
            f.truncate(fs_bytes)
        mk = ["mkfs.vfat", "-F", "32", "-n", lbl, "-s", str(spc), "-S", str(ss)]
        if old_uuid and len(old_uuid.replace("-", "")) == 8:
            mk += ["-i", old_uuid.replace("-", "")]
        run(*mk, fat)
        mnt_new = os.path.join(work, "new")
        os.makedirs(mnt_new)
        run("mount", "-o", "loop,rw,noatime", fat, mnt_new)
        run("cp", "-r", "--no-preserve=mode,ownership", "--preserve=timestamps", mnt_old + "/.", mnt_new + "/")
        run("sync")
        run("umount", mnt_new)
        mnt_new = None
        run("umount", mnt_old)
        mnt_old = None
        run("losetup", "-d", loop)
        loop = None
        if shutil.which("fsck.vfat"):
            rc = run("fsck.vfat", "-n", fat, check=False)
            if rc not in (0,):
                sys.exit("the new boot file system did not pass fsck.vfat (exit %d)" % rc)

        layout, total_sectors = plan_layout(parts, fs_bytes // ss, label)
        new_size = total_sectors * ss
        if new_size >= old_total:
            print("   the compacted image would not be smaller; leaving it alone")
            return 0

        newimg = os.path.join(work, "compact.img")
        with open(img, "rb") as src, open(newimg, "wb") as dst:
            dst.truncate(new_size)
            copy_range(src, dst, 0, 0, p1["start"] * ss)
            for p, start, size in layout:
                if p is p1 or any(p is b for b in before):
                    continue
                copy_range(src, dst, p["start"] * ss, start * ss, size * ss)
            with open(fat, "rb") as f:
                copy_range(f, dst, 0, p1["start"] * ss, fs_bytes)

        script = sfdisk_script(tab, layout)
        run("sfdisk", "--no-reread", "--no-tell-kernel", newimg, stdin=script)
        if label == "dos":
            with open(img, "rb") as src, open(newimg, "r+b") as dst:
                dst.write(src.read(440))

        chk = run("sfdisk", "-d", newimg, capture=True)
        if "label: %s" % label not in chk:
            sys.exit("the new image lost its %s partition table:\n%s" % (label, chk))
        loop = run("losetup", "-Pfr", "--show", newimg, capture=True).strip()
        got = run("blkid", "-s", "LABEL", "-o", "value", "%sp1" % loop, capture=True, check=False).strip()
        mnt_chk = os.path.join(work, "chk")
        os.makedirs(mnt_chk)
        run("mount", "-o", "ro", "%sp1" % loop, mnt_chk)
        try:
            if not os.path.isfile(os.path.join(mnt_chk, "SYSTEM")):
                sys.exit("the compacted boot partition has no SYSTEM file")
            if got != lbl:
                sys.exit("the compacted boot partition label is '%s', expected '%s'" % (got, lbl))
        finally:
            run("umount", mnt_chk)
            run("losetup", "-d", loop)
            loop = None

        os.replace(newimg, img)
        print("==> compacted: %d MiB -> %d MiB (%s)" % (old_total // MIB, new_size // MIB, os.path.basename(img)))
        for p, start, size in sorted(layout, key=lambda x: x[0]["num"]):
            print("   p%d  start %-9d size %-9d (%d MiB)  %s" % (p["num"], start, size, size * ss // MIB, p.get("name", "")))
        return 0
    finally:
        for m in (mnt_new, mnt_old):
            if m:
                run("umount", m, check=False)
        if loop:
            run("losetup", "-d", loop, check=False)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
