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


if __name__ == "__main__":
    unittest.main()
