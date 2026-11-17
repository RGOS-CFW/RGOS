import hashlib
import os
import sys
import unittest
from unittest import mock

from tests import helpers

menu = helpers.load_menu()
sys.path.insert(0, helpers.RGOS)
import biosctl


def put(root, rel, data=b"x"):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return p


def good_md5(path):
    base = os.path.basename(path).lower()
    for entries in biosctl.BIOS.values():
        for e in entries:
            if e[0].split("/")[-1].lower() == base:
                return e[2][0]
    return ""


def by_file(res):
    return {r["file"]: r for r in res}


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.bios = os.path.join(helpers.sandbox(), "bios")
        os.makedirs(self.bios)

    def test_every_entry_is_well_formed(self):
        for sid, entries in biosctl.BIOS.items():
            for e in entries:
                self.assertEqual(len(e), 5, (sid, e))
                self.assertTrue(e[0] and not e[0].startswith("/") and ".." not in e[0], e[0])
                self.assertTrue(all(m == "" or (len(m) == 32 and m == m.lower()) for m in e[2]), e[0])
                self.assertTrue(e[3] == "*" or isinstance(e[3], tuple), e[0])

    def test_missing_required_vs_optional_depends_on_the_core(self):
        r = by_file(biosctl.check_system("psx", "pcsx_rearmed", [self.bios]))
        self.assertTrue(all(x["status"] == biosctl.OPTIONAL for x in r.values()))
        r = by_file(biosctl.check_system("psx", "swanstation", [self.bios]))
        self.assertTrue(all(x["status"] == biosctl.MISSING for x in r.values()))

    @mock.patch.object(biosctl, "md5_of", good_md5)
    def test_one_psx_region_satisfies_the_group(self):
        put(self.bios, "scph5501.bin")
        r = by_file(biosctl.check_system("psx", "swanstation", [self.bios]))
        self.assertEqual(r["scph5501.bin"]["status"], biosctl.OK)      
        self.assertEqual(r["scph5500.bin"]["status"], biosctl.OPTIONAL)
        self.assertEqual(r["scph5502.bin"]["status"], biosctl.OPTIONAL)

    def test_md5(self):
        data = b"hello"
        good = hashlib.md5(data).hexdigest()
        entry = ("t.bin", "test", (good,), "*", "")
        put(self.bios, "t.bin", data)
        self.assertEqual(biosctl.check_file(entry, [self.bios])[0], biosctl.OK)
        put(self.bios, "u.bin", b"other")
        self.assertEqual(biosctl.check_file(("u.bin", "t", (good,), "*", ""), [self.bios])[0], biosctl.DIFFERS)
        self.assertEqual(biosctl.check_file(("u.bin", "t", ("",), "*", ""), [self.bios])[0], biosctl.OK)

    def test_wrong_case_is_reported_not_missing(self):
        put(self.bios, "NEOGEO.ZIP")
        r = by_file(biosctl.check_system("neogeo", "fbneo", [self.bios]))
        self.assertEqual(r["neogeo.zip"]["status"], biosctl.CASE)
        put(self.bios, "Dolphin-Emu/sys/gc/usa/ipl.bin")
        r = by_file(biosctl.check_system("gc", "dolphin", [self.bios]))
        self.assertEqual(r["dolphin-emu/Sys/GC/USA/IPL.bin"]["status"], biosctl.CASE)

    def test_subfolder_file_and_second_card(self):
        card2 = os.path.join(helpers.sandbox(), "bios")
        put(card2, "dolphin-emu/Sys/GC/EUR/IPL.bin")
        r = by_file(biosctl.check_system("gc", "dolphin", [self.bios, card2]))
        self.assertEqual(r["dolphin-emu/Sys/GC/EUR/IPL.bin"]["status"], biosctl.OK)
        self.assertEqual(r["dolphin-emu/Sys/GC/USA/IPL.bin"]["status"], biosctl.OPTIONAL)

    def test_missing_bios_folder_does_not_crash(self):
        r = biosctl.check_system("segacd", "genesis_plus_gx", [os.path.join(self.bios, "nope")])
        self.assertTrue(all(x["status"] == biosctl.MISSING for x in r))

    def test_summary_and_lines(self):
        rows, summ = biosctl.check_all([("segacd", "Sega CD"), ("snes", "SNES")], lambda s: "genesis_plus_gx", [self.bios])
        self.assertEqual(summ["systems"], 1)
        self.assertEqual(summ["missing"], 3)
        lines = biosctl.build_lines(rows, False, "ROMS/bios")
        self.assertEqual(lines[0], ("head", "Sega CD", "3 missing"))
        self.assertIn(("path", "put in  ROMS/bios/", ""), lines)
        self.assertTrue(any(k == "miss" and "bios_CD_U.bin" in t for k, t, _ in lines))

    @mock.patch.object(biosctl, "md5_of", good_md5)
    def test_ok_systems_are_one_line_unless_show_all(self):
        for f in ("bios_CD_U.bin", "bios_CD_E.bin", "bios_CD_J.bin"):
            put(self.bios, f)
        rows, summ = biosctl.check_all([("segacd", "Sega CD")], lambda s: "genesis_plus_gx", [self.bios])
        self.assertEqual(summ["missing"], 0)
        self.assertEqual(len(biosctl.build_lines(rows, False, "ROMS/bios")), 1)
        self.assertEqual(len(biosctl.build_lines(rows, True, "ROMS/bios")), 4)

    def test_subfolder_hint(self):
        rows, _ = biosctl.check_all([("gc", "GameCube")], lambda s: "dolphin", [self.bios])
        self.assertIn(("path", "put in  ROMS/bios/dolphin-emu/Sys/GC/USA/", ""), biosctl.build_lines(rows, False, "ROMS/bios"))


class MenuTests(unittest.TestCase):
    def test_row_is_registered_with_an_icon(self):
        self.assertIn("bios", menu.SETTINGS_ROWS)
        self.assertIn("bios", menu.ICONS)

    def test_scan_uses_the_selected_core(self):
        bios = os.path.join(helpers.sandbox(), "bios")
        os.makedirs(bios)
        menu.SYSTEMS_BACKUP = menu.SYSTEMS
        try:
            menu.SYSTEMS = [("psx", "PSX", "retroarch", (".cue",), "Sony PlayStation")]
            menu.bios_dirs = lambda: [bios]
            _rows, s = menu.bios_scan({})
            self.assertEqual((s["missing"], s["optional"]), (0, 3))
            _rows, s = menu.bios_scan({"emulators": {"psx": "swanstation"}})
            self.assertEqual(s["missing"], 3)
            _rows, s = menu.bios_scan({"emulators": "garbage"})
            self.assertEqual(s["systems"], 1)
        finally:
            menu.SYSTEMS = menu.SYSTEMS_BACKUP

    def test_summary_text(self):
        self.assertIn("No installed", menu.bios_summary_text({"systems": 0, "missing": 0, "optional": 0, "ok": 0}))
        self.assertEqual(menu.bios_summary_text({"systems": 2, "missing": 2, "optional": 1, "ok": 4}), "2 required missing   1 optional missing   4 OK")


if __name__ == "__main__":
    unittest.main()
