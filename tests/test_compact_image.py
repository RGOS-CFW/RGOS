import importlib.util
import os
import re
import unittest

from helpers import ROOT

spec = importlib.util.spec_from_file_location("compact_image", os.path.join(ROOT, "tools", "compact-image.py"))
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)

SECTORS_2GB = 4194304


def mbr_table():
    return {"label": "dos", "id": "0x12345678", "sectorsize": 512, "partitions": [
        {"num": 1, "node": "x.img1", "start": 32768, "size": SECTORS_2GB, "type": "c", "bootable": True},
        {"num": 2, "node": "x.img2", "start": 32768 + SECTORS_2GB, "size": 65536, "type": "83"}]}


def gpt_table():
    return {"label": "gpt", "id": "AAAAAAAA-0000-0000-0000-000000000001", "sectorsize": 512, "firstlba": 34, "partitions": [
        {"num": 1, "node": "x.img1", "start": 4096, "size": SECTORS_2GB, "type": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
         "uuid": "11111111-0000-0000-0000-000000000001", "name": "boot"},
        {"num": 2, "node": "x.img2", "start": 4096 + SECTORS_2GB, "size": 65536, "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
         "uuid": "11111111-0000-0000-0000-000000000002", "name": "storage"},
        {"num": 3, "node": "x.img3", "start": 4096 + SECTORS_2GB + 65536, "size": 16384,
         "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4", "uuid": "11111111-0000-0000-0000-000000000003", "name": "uboot",
         "attrs": "RequiredPartition"}]}


class Layout(unittest.TestCase):
    def test_mbr_partition_two_follows_the_smaller_boot_partition(self):
        t = mbr_table()
        layout, total = ci.plan_layout(t["partitions"], 262144, "dos")
        (p1, s1, z1), (p2, s2, z2) = layout
        self.assertEqual((s1, z1), (32768, 262144))
        self.assertEqual(s2, 32768 + 262144)
        self.assertEqual(z2, 65536)
        self.assertEqual(total, s2 + z2)
        self.assertLess(total * 512, 200 * 1024 * 1024)

    def test_gpt_keeps_partition_order_and_leaves_room_for_the_backup_table(self):
        t = gpt_table()
        layout, total = ci.plan_layout(t["partitions"], 262144, "gpt")
        starts = [s for _, s, _ in layout]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual([p["name"] for p, _, _ in layout], ["boot", "storage", "uboot"])
        last_end = layout[-1][1] + layout[-1][2]
        self.assertGreaterEqual(total, last_end + 33)
        self.assertEqual(total % ci.ALIGN, 0)

    def test_moved_partitions_stay_aligned_and_never_overlap(self):
        for t, label in ((mbr_table(), "dos"), (gpt_table(), "gpt")):
            layout, _ = ci.plan_layout(t["partitions"], 262144 + 123, label)
            for (a, sa, za), (b, sb, zb) in zip(layout, layout[1:]):
                self.assertGreaterEqual(sb, sa + za)
                self.assertEqual(sb % ci.ALIGN, 0)

    def test_a_partition_before_the_boot_partition_is_not_moved(self):
        t = mbr_table()
        pre = {"num": 3, "node": "x.img3", "start": 8192, "size": 8192, "type": "83"}
        layout, _ = ci.plan_layout(t["partitions"] + [pre], 262144, "dos")
        self.assertEqual(layout[0], (pre, 8192, 8192))


class Script(unittest.TestCase):
    def test_gpt_script_keeps_ids_names_and_flags(self):
        t = gpt_table()
        layout, _ = ci.plan_layout(t["partitions"], 262144, "gpt")
        s = ci.sfdisk_script(t, layout)
        self.assertIn("label: gpt", s)
        self.assertIn("label-id: AAAAAAAA-0000-0000-0000-000000000001", s)
        self.assertIn("first-lba: 34", s)
        self.assertIn('name="uboot"', s)
        self.assertIn('attrs="RequiredPartition"', s)
        self.assertIn("uuid=11111111-0000-0000-0000-000000000003", s)
        self.assertIn("size=262144", s)

    def test_dos_script_keeps_the_signature_type_and_bootable_flag(self):
        t = mbr_table()
        layout, _ = ci.plan_layout(t["partitions"], 262144, "dos")
        s = ci.sfdisk_script(t, layout)
        self.assertIn("label: dos", s)
        self.assertIn("label-id: 0x12345678", s)
        self.assertRegex(s, r"start=32768, size=262144, type=c, bootable")
        self.assertRegex(s, r"start=294912, size=65536, type=83")


class Geometry(unittest.TestCase):
    def test_fat32_always_has_enough_clusters_and_room_for_the_content(self):
        for used_mb in (1, 40, 300, 900):
            used = {spc * 512: used_mb << 20 for spc in (8, 4, 2, 1)}
            size, spc = ci.pick_geometry(used, 64 << 20)
            self.assertGreaterEqual(size // (spc * 512), ci.FAT32_MIN_CLUSTERS)
            self.assertGreaterEqual(size, (used_mb + 64) << 20)
            self.assertEqual(size % ci.MIB, 0)

    def test_headroom_is_added(self):
        used = {spc * 512: 500 << 20 for spc in (8, 4, 2, 1)}
        small, _ = ci.pick_geometry(used, 0)
        big, _ = ci.pick_geometry(used, 256 << 20)
        self.assertGreaterEqual(big - small, 256 << 20)

    def test_copy_range_skips_zero_chunks_and_copies_the_rest(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "s"), os.path.join(d, "d")
            with open(src, "wb") as f:
                f.write(bytes(ci.MIB) + b"\x01" * 10 + bytes(ci.MIB - 10))
            with open(dst, "wb") as f:
                f.truncate(4 * ci.MIB)
            with open(src, "rb") as a, open(dst, "r+b") as b:
                ci.copy_range(a, b, 0, ci.MIB, 2 * ci.MIB)
            with open(dst, "rb") as f:
                data = f.read()
            self.assertEqual(len(data), 4 * ci.MIB)
            self.assertEqual(data[2 * ci.MIB:2 * ci.MIB + 10], b"\x01" * 10)
            self.assertEqual(data[:2 * ci.MIB], bytes(2 * ci.MIB))


class BuildWiring(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "build.sh"), newline="") as f:
            self.b = f.read()

    def test_build_compacts_image_and_installer_builds_not_update_tars(self):
        self.assertIn("tools/compact-image.py", self.b)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "tools", "compact-image.py")))
        i = self.b.index("tools/compact-image.py")
        self.assertGreater(i, self.b.index('"$MODE" == "update" ]]; then\n  UPD_ID'))
        self.assertLess(i, self.b.index("Partitions in the image (partition 3"))

    def test_options_are_validated_and_can_be_switched_off(self):
        for opt in ("COMPACT_IMAGE", "PRUNE_ROCKNIX", "BOOT_HEADROOM_MB", "FIRMWARE_KEEP", "PRUNE_BOOT_EXTRA"):
            self.assertIn(opt, self.b)
        self.assertRegex(self.b, r'COMPACT_IMAGE" == 1 \]\]; then')

    def test_what_the_boot_and_radio_setup_needs_is_never_pruned(self):
        m = re.search(r"for pat in (.*?); do", self.b, re.S)
        pats = m.group(1).replace("\\\n", " ").split()
        for needed in ("rtl_bt", "rtlbt", "brcm", "regulatory.db", "mali", "sprd", "rtw88", "rtw89"):
            self.assertNotIn(needed, pats)

    def test_boot_files_the_device_loads_are_protected_from_pruning(self):
        i = self.b.index("boot_ref()")
        block = self.b[i:i + 600]
        for keep in ("KERNEL", "SYSTEM", "dtb.img", "INITRD_NAME", "extlinux"):
            self.assertIn(keep, block)


if __name__ == "__main__":
    unittest.main()
