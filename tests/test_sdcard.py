import os, re, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "rgos"))
import sdcard


def menu_system_ids():
    with open(os.path.join(ROOT, "rgos", "menu.py"), encoding="utf-8") as f:
        text = f.read()
    block = text[text.index("SYSTEMS = ["):text.index("ROMS_DIR =")]
    return re.findall(r'\("(\w+)", "[^"]+", "(?:retroarch|native)"', block)


class SecondCardFolders(unittest.TestCase):
    def test_every_menu_system_gets_a_folder(self):
        # A second SD card must get a roms/<system> folder for every system the menu lists (GameCube was missing).
        self.assertEqual(set(menu_system_ids()) - set(sdcard.SYSTEM_DIRS), set())

    def test_make_folders_creates_gc(self):
        with tempfile.TemporaryDirectory() as mp:
            self.assertTrue(sdcard.make_folders(mp))
            self.assertTrue(os.path.isdir(os.path.join(mp, "roms", "gc")))

    def test_make_folders_fills_in_a_partial_roms_dir(self):
        # a card that already has an (empty or half-filled) roms folder must still get every system folder
        with tempfile.TemporaryDirectory() as mp:
            os.makedirs(os.path.join(mp, "roms", "gba"))
            self.assertTrue(sdcard.make_folders(mp))
            for sid in sdcard.SYSTEM_DIRS:
                self.assertTrue(os.path.isdir(os.path.join(mp, "roms", sid)), sid)

    def test_make_folders_reports_failure(self):
        with tempfile.TemporaryDirectory() as mp:
            open(os.path.join(mp, "roms"), "w").close()  # a file where the folder should be
            self.assertFalse(sdcard.make_folders(mp))

    def test_readonly_detected_from_mount_table(self):
        table = [("/dev/mmcblk1p1", "/media/roms2", "exfat", "ro,noatime"), ("/dev/mmcblk0p3", "/media/roms", "exfat", "rw,noatime")]
        self.assertTrue(sdcard.is_readonly("/media/roms2", table))
        self.assertFalse(sdcard.is_readonly("/media/roms", table))

    def test_shipped_config_enables_card_2(self):
        with open(os.path.join(ROOT, "build.sh"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn('"enabled": true', [l for l in text.splitlines() if "sdcard.json" in l][0])

    def test_session_starts_the_card_watcher(self):
        with open(os.path.join(ROOT, "rgos", "rgos-session"), encoding="utf-8") as f:
            self.assertIn("sdcard.py watch", f.read())


class CardDetection(unittest.TestCase):
    def _img(self, boot):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(boot.ljust(2048, b"\0"))
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_sniff_exfat(self):
        self.assertEqual(sdcard.sniff_fs(self._img(b"\xeb\x76\x90EXFAT   ")), "exfat")

    def test_sniff_fat32(self):
        b = bytearray(512)
        b[82:90] = b"FAT32   "
        b[510:512] = b"\x55\xaa"
        self.assertEqual(sdcard.sniff_fs(self._img(bytes(b))), "vfat")

    def test_sniff_ext4(self):
        b = bytearray(2048)
        b[1080:1082] = b"\x53\xef"
        self.assertEqual(sdcard.sniff_fs(self._img(bytes(b))), "ext4")

    def test_sniff_garbage(self):
        self.assertEqual(sdcard.sniff_fs(self._img(b"")), "")

    def test_exfat_card_found_even_when_blkid_is_silent(self):
        # the RG35XXH-labelled exFAT card: blkid says nothing, the superblock sniff must still pick it
        conf = dict(sdcard.DEFAULTS)
        img = self._img(b"\xeb\x76\x90EXFAT   ")
        with mock.patch.object(sdcard, "partitions", return_value=[(img, 64 * 2048)]), \
             mock.patch.object(sdcard, "sh", return_value=(2, "")):
            got = sdcard.pick_partition("mmcblk1", conf)
        self.assertEqual((got["dev"], got["fstype"]), (img, "exfat"))

    def test_unrecognised_partition_is_still_tried(self):
        conf = dict(sdcard.DEFAULTS)
        img = self._img(b"nothing here")
        with mock.patch.object(sdcard, "partitions", return_value=[(img, 64 * 2048)]), \
             mock.patch.object(sdcard, "sh", return_value=(2, "")):
            self.assertEqual(sdcard.pick_partition("mmcblk1", conf)["fstype"], "auto")

    def test_boot_labels_and_swap_are_never_picked(self):
        conf = dict(sdcard.DEFAULTS)
        with mock.patch.object(sdcard, "partitions", return_value=[("/dev/x1", 64 * 2048), ("/dev/x2", 64 * 2048)]), \
             mock.patch.object(sdcard, "probe", side_effect=[{"TYPE": "vfat", "LABEL": "RGOS"}, {"TYPE": "swap"}]):
            self.assertIsNone(sdcard.pick_partition("mmcblk1", conf))

    def test_session_starts_watcher_before_portmaster_copy(self):
        with open(os.path.join(ROOT, "rgos", "rgos-session"), encoding="utf-8") as f:
            t = f.read()
        self.assertLess(t.index("sdcard.py watch"), t.index("preinstalled PortMaster"))


if __name__ == "__main__":
    unittest.main()
