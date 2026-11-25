import os, re, sys, tempfile, unittest

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


if __name__ == "__main__":
    unittest.main()
