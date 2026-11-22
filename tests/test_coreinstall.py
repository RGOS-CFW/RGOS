import io
import os
import platform
import sys
import time
import unittest
import urllib.error
import zipfile

from tests import helpers

menu = helpers.load_menu()
sys.path.insert(0, helpers.RGOS)
import coreinstall
import cores

MACHINE = coreinstall.ELF_MACHINE.get(platform.machine().lower(), 183)


def elf(machine=None):
    return b"\x7fELF" + bytes(14) + (MACHINE if machine is None else machine).to_bytes(2, "little") + bytes(64)


def make_zip(name, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, data)
    return buf.getvalue()


class FakeResp(io.BytesIO):
    def __init__(self, data, length=True):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))} if length else {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def serving(files):
    """An opener serving {url suffix: bytes}; anything else is a 404."""
    seen = []

    def opener(req, timeout=0):
        seen.append(req.full_url)
        for suffix, data in files.items():
            if req.full_url.endswith(suffix):
                return FakeResp(data)
        raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
    opener.seen = seen
    return opener


class CatalogTests(unittest.TestCase):
    SYSTEMS = [("gba", "GBA", "Game Boy Advance"), ("gb", "GB", "Game Boy"), ("gc", "GC", "GameCube"), ("arcade", "ARC", "Arcade")]

    def test_missing_first_and_systems_merged(self):
        rows = coreinstall.candidates(self.SYSTEMS, cores.SYSTEM_CORE_COMPATIBILITY, ["mgba", "gambatte"])
        names = [r["core"] for r in rows]
        self.assertNotIn("dolphin", names)
        first_installed = min(i for i, r in enumerate(rows) if r["installed"])
        self.assertTrue(all(r["installed"] for r in rows[first_installed:]))
        self.assertFalse(any(r["installed"] for r in rows[:first_installed]))
        mgba = next(r for r in rows if r["core"] == "mgba")
        self.assertEqual(mgba["systems"], ["GBA", "GB"])

    def test_only_listed_systems_are_considered(self):
        rows = coreinstall.candidates([("gba", "GBA", "x")], cores.SYSTEM_CORE_COMPATIBILITY, [])
        self.assertEqual({r["core"] for r in rows}, set(cores.SYSTEM_CORE_COMPATIBILITY["gba"]))

    def test_uncovered_systems(self):
        self.assertEqual(coreinstall.uncovered(self.SYSTEMS, cores.SYSTEM_CORE_COMPATIBILITY, ["mgba"]), ["gc", "arcade"])

    def test_every_catalog_name_is_safe(self):
        for sid, lst in cores.SYSTEM_CORE_COMPATIBILITY.items():
            for c in lst:
                self.assertRegex(c, coreinstall.NAME_RE, c)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.dest = os.path.join(helpers.sandbox(), "cores")

    def test_installs_core(self):
        op = serving({"/gpsp_libretro.so.zip": make_zip("gpsp_libretro.so", elf())})
        prog = []
        path = coreinstall.download("gpsp", self.dest, "https://example.test/x", prog.append, None, op)
        self.assertEqual(path, os.path.join(self.dest, "gpsp_libretro.so"))
        self.assertEqual(open(path, "rb").read(), elf())
        self.assertEqual(op.seen, ["https://example.test/x/gpsp_libretro.so.zip"])
        self.assertEqual(prog[-1], 100)
        self.assertEqual(sorted(os.listdir(self.dest)), ["gpsp_libretro.so"])

    def test_installed_core_is_picked_up_by_core_lookup(self):
        old = os.environ.get("RGOS_ROMS")
        os.environ["RGOS_ROMS"] = os.path.dirname(self.dest)
        try:
            coreinstall.download("gpsp", self.dest, "https://e.test", None, None, serving({"gpsp_libretro.so.zip": make_zip("gpsp_libretro.so", elf())}))
            self.assertIn("gpsp", cores.installed_cores())
            self.assertIn("gpsp", cores.compatible_cores("gba"))
        finally:
            if old is None:
                del os.environ["RGOS_ROMS"]
            else:
                os.environ["RGOS_ROMS"] = old

    def test_404(self):
        with self.assertRaisesRegex(coreinstall.CoreInstallError, "Not available"):
            coreinstall.download("nope", self.dest, "https://e.test", None, None, serving({}))
        self.assertEqual(os.listdir(self.dest), [])

    def test_offline(self):
        def op(req, timeout=0):
            raise urllib.error.URLError("no route")
        with self.assertRaisesRegex(coreinstall.CoreInstallError, "Wi-Fi"):
            coreinstall.download("gpsp", self.dest, "https://e.test", None, None, op)

    def test_rejects_wrong_zip_member(self):
        op = serving({"gpsp_libretro.so.zip": make_zip("../evil_libretro.so", elf())})
        with self.assertRaisesRegex(coreinstall.CoreInstallError, "does not contain"):
            coreinstall.download("gpsp", self.dest, "https://e.test", None, None, op)
        self.assertEqual(os.listdir(self.dest), [])

    def test_rejects_non_elf_and_wrong_cpu_and_bad_zip(self):
        for data, msg in ((make_zip("gpsp_libretro.so", b"<html>nope</html>" + bytes(40)), "not a core"),
                          (make_zip("gpsp_libretro.so", elf(machine=8)), "different CPU"),
                          (b"this is not a zip", "damaged")):
            with self.assertRaisesRegex(coreinstall.CoreInstallError, msg):
                coreinstall.download("gpsp", self.dest, "https://e.test", None, None, serving({"gpsp_libretro.so.zip": data}))
            self.assertEqual(os.listdir(self.dest), [])

    def test_failed_install_keeps_existing_core(self):
        os.makedirs(self.dest)
        keep = os.path.join(self.dest, "gpsp_libretro.so")
        open(keep, "wb").write(b"old")
        with self.assertRaises(coreinstall.CoreInstallError):
            coreinstall.download("gpsp", self.dest, "https://e.test", None, None, serving({}))
        self.assertEqual(open(keep, "rb").read(), b"old")

    def test_bad_names_never_touch_the_network(self):
        op = serving({})
        for bad in ("../x", "a/b", "", "UP", "a b"):
            with self.assertRaises(coreinstall.CoreInstallError):
                coreinstall.download(bad, self.dest, "https://e.test", None, None, op)
        self.assertEqual(op.seen, [])

    def test_cancel_cleans_up(self):
        op = serving({"gpsp_libretro.so.zip": make_zip("gpsp_libretro.so", elf())})
        with self.assertRaisesRegex(coreinstall.CoreInstallError, "Cancelled"):
            coreinstall.download("gpsp", self.dest, "https://e.test", None, lambda: True, op)
        self.assertEqual(os.listdir(self.dest), [])

    def test_base_url_override(self):
        old = os.environ.get("RGOS_CORE_URL")
        try:
            os.environ["RGOS_CORE_URL"] = "https://mirror.test/cores/"
            self.assertEqual(coreinstall.base_url(), "https://mirror.test/cores")
            os.environ["RGOS_CORE_URL"] = "ftp://bad"
            self.assertEqual(coreinstall.base_url(), coreinstall.DEFAULT_URL)
        finally:
            if old is None:
                os.environ.pop("RGOS_CORE_URL", None)
            else:
                os.environ["RGOS_CORE_URL"] = old


def wait(inst, secs=5):
    end = time.time() + secs
    while inst.snapshot()["busy"] and time.time() < end:
        time.sleep(0.01)
    return inst.snapshot()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.dest = os.path.join(helpers.sandbox(), "cores")

    def test_installs_several_and_reports_once(self):
        files = {"gpsp_libretro.so.zip": make_zip("gpsp_libretro.so", elf()), "vbam_libretro.so.zip": make_zip("vbam_libretro.so", elf())}
        inst = coreinstall.Installer(self.dest, "https://e.test", serving(files), {"gpsp": "gpSP"})
        self.assertTrue(inst.start(["gpsp", "vbam", "gpsp"]))
        s = wait(inst)
        self.assertEqual((s["ok"], s["failed"], s["msg"]), (["gpsp", "vbam"], [], "Installed 2 cores"))
        self.assertTrue(inst.take_changed())
        self.assertFalse(inst.take_changed())

    def test_partial_failure(self):
        inst = coreinstall.Installer(self.dest, "https://e.test", serving({"gpsp_libretro.so.zip": make_zip("gpsp_libretro.so", elf())}))
        inst.start(["gpsp", "vbam"])
        s = wait(inst)
        self.assertEqual(s["ok"], ["gpsp"])
        self.assertIn("1 installed, 1 failed", s["msg"])
        self.assertTrue(inst.take_changed())

    def test_failure_changes_nothing(self):
        inst = coreinstall.Installer(self.dest, "https://e.test", serving({}), {"vbam": "VBA-M"})
        inst.start(["vbam"])
        s = wait(inst)
        self.assertEqual(s["msg"], "VBA-M: Not available for this device")
        self.assertFalse(inst.take_changed())

    def test_offline_stops_the_queue(self):
        calls = []

        def op(req, timeout=0):
            calls.append(req.full_url)
            raise urllib.error.URLError("down")
        inst = coreinstall.Installer(self.dest, "https://e.test", op)
        inst.start(["gpsp", "vbam", "sameboy"])
        s = wait(inst)
        self.assertEqual(len(calls), 1)
        self.assertIn("Wi-Fi", s["msg"])

    def test_nothing_to_do_and_excluded(self):
        inst = coreinstall.Installer(self.dest)
        self.assertFalse(inst.start([]))
        self.assertFalse(inst.start(["dolphin", "../x"]))


class ReinstallTests(unittest.TestCase):
    def setUp(self):
        self.dest = os.path.join(helpers.sandbox(), "cores")

    def test_has_copy_only_for_a_file_in_the_roms_cores_folder(self):
        self.assertFalse(coreinstall.has_copy(self.dest, "gpsp"))
        os.makedirs(self.dest)
        open(os.path.join(self.dest, "gpsp_libretro.so"), "wb").write(b"x")
        self.assertTrue(coreinstall.has_copy(self.dest, "gpsp"))
        self.assertFalse(coreinstall.has_copy(self.dest, "vbam"))
        self.assertFalse(coreinstall.has_copy(self.dest, "../gpsp"))

    def test_reinstall_replaces_the_copy_and_says_reinstalled(self):
        os.makedirs(self.dest)
        path = os.path.join(self.dest, "gpsp_libretro.so")
        open(path, "wb").write(b"old")
        inst = coreinstall.Installer(self.dest, "https://e.test", serving({"gpsp_libretro.so.zip": make_zip("gpsp_libretro.so", elf())}),
                                     {"gpsp": "gpSP"})
        self.assertTrue(inst.start(["gpsp"], reinstall=True))
        s = wait(inst)
        self.assertEqual((s["ok"], s["msg"]), (["gpsp"], "Reinstalled gpSP"))
        self.assertEqual(open(path, "rb").read(), elf())
        self.assertTrue(inst.take_changed())

    def test_a_plain_install_still_says_installed_after_a_reinstall(self):
        inst = coreinstall.Installer(self.dest, "https://e.test", serving({"gpsp_libretro.so.zip": make_zip("gpsp_libretro.so", elf())}))
        inst.start(["gpsp"], reinstall=True)
        wait(inst)
        inst.start(["gpsp"])
        self.assertEqual(wait(inst)["msg"], "Installed gpsp")

    def test_a_failed_reinstall_keeps_the_old_core_and_reports_why(self):
        os.makedirs(self.dest)
        path = os.path.join(self.dest, "gpsp_libretro.so")
        open(path, "wb").write(b"old")
        inst = coreinstall.Installer(self.dest, "https://e.test", serving({}), {"gpsp": "gpSP"})
        inst.start(["gpsp"], reinstall=True)
        s = wait(inst)
        self.assertEqual((s["ok"], s["msg"]), ([], "gpSP: Not available for this device"))
        self.assertEqual(open(path, "rb").read(), b"old")
        self.assertFalse(inst.take_changed())

    def test_say_shows_a_note_only_when_idle(self):
        inst = coreinstall.Installer(self.dest)
        self.assertTrue(inst.say("hello"))
        self.assertEqual(inst.snapshot()["msg"], "hello")
        inst._s["busy"] = True
        self.assertFalse(inst.say("again"))
        self.assertEqual(inst.snapshot()["msg"], "hello")

    def test_rows_know_which_cores_have_a_copy_on_the_roms_card(self):
        root = helpers.sandbox()
        os.makedirs(os.path.join(root, "cores"))
        open(os.path.join(root, "cores", "gpsp_libretro.so"), "wb").write(b"x")
        old_root, old_inst = menu.ROMS_ROOT, menu.installed_cores
        menu.ROMS_ROOT, menu.installed_cores = root, lambda: ["mgba", "gpsp"]
        try:
            rows = {r["core"]: r for r in menu.core_installer_rows()}
        finally:
            menu.ROMS_ROOT, menu.installed_cores = old_root, old_inst
        self.assertTrue(rows["gpsp"]["copy"])           # downloaded: X can reinstall it
        self.assertFalse(rows["mgba"]["copy"])          # ships in the image: nothing to replace
        self.assertFalse(rows["fbneo"]["copy"])         # not installed at all

    def test_the_menu_wires_x_to_reinstall_and_shows_it(self):
        src = open(os.path.join(helpers.RGOS, "menu.py"), encoding="utf-8").read()
        self.assertIn('elif a == "x" and ci_rows and not ci_s["busy"]:', src)
        self.assertIn('ci.start([r["core"]], reinstall=True)', src)
        self.assertIn("X Reinstall", src)


class MenuTests(unittest.TestCase):
    def test_tool_is_listed(self):
        self.assertIn(("coreinstall", "Core Installer"), [(t[0], t[1]) for t in menu.TOOLS])
        self.assertIn("@view:coreinstall", [t[3] for t in menu.TOOLS])

    def test_rows_cover_systems_hidden_for_lack_of_a_core(self):
        old = menu.installed_cores
        menu.installed_cores = lambda: ["mgba"]
        try:
            rows = {r["core"]: r for r in menu.core_installer_rows()}
        finally:
            menu.installed_cores = old
        self.assertTrue(rows["mgba"]["installed"])
        self.assertFalse(rows["fbneo"]["installed"])
        self.assertEqual(rows["fbneo"]["systems"], ["ARC", "NEO"])
        self.assertNotIn("dolphin", rows)

    def test_filter_systems_follows_installed_cores_in_place(self):
        ref = menu.SYSTEMS
        old = menu.installed_cores
        prev = list(ref)
        try:
            menu.installed_cores = lambda: ["mgba"]
            menu.filter_systems()
            self.assertIs(menu.SYSTEMS, ref)
            self.assertEqual([sy[0] for sy in ref if sy[2] == "retroarch"], ["gba", "gb", "gbc"])
            menu.installed_cores = lambda: ["mgba", "fbneo"]
            menu.filter_systems()
            self.assertIn("arcade", [sy[0] for sy in ref])
            self.assertIn("neogeo", [sy[0] for sy in ref])
        finally:
            menu.installed_cores = old
            ref[:] = prev


if __name__ == "__main__":
    unittest.main()
