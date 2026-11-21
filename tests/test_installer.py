import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import unittest
from collections import namedtuple
from unittest import mock

from tests import helpers

ROOT = helpers.ROOT
sys.path.insert(0, os.path.join(ROOT, "rgos"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import installer  # noqa: E402
import mkpayload  # noqa: E402


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def load_ui():
    loader = importlib.machinery.SourceFileLoader("rgos_installer_ui", os.path.join(ROOT, "rgos", "rgos-installer"))
    spec = importlib.util.spec_from_loader("rgos_installer_ui", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class Card(unittest.TestCase):
    """A fake card: a boot folder with a payload, an (empty) ROMS folder, and the real installer logic on top."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rgos-inst-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.boot, self.roms, self.src = [os.path.join(self.tmp, n) for n in ("boot", "roms", "src")]
        os.makedirs(self.boot)
        p = mock.patch.object(installer, "LOG_FILE", os.path.join(self.tmp, "installer.log"))
        p.start()
        self.addCleanup(p.stop)
        cores = os.path.join(self.src, "cores")
        os.makedirs(cores)
        for n in ("mgba", "snes9x"):
            with open(os.path.join(cores, n + "_libretro.so"), "wb") as f:
                f.write(b"\x7fELF" + n.encode() * 100)
        seed = os.path.join(self.src, "seed", "PortMaster", "pylibs")
        os.makedirs(seed)
        with open(os.path.join(self.src, "seed", "PortMaster", "PortMaster.sh"), "w") as f:
            f.write("#!/bin/sh\necho pm\n")
        os.chmod(os.path.join(self.src, "seed", "PortMaster", "PortMaster.sh"), 0o755)
        with open(os.path.join(seed, "harness.py"), "w") as f:
            f.write("x = 1\n")
        self.pdir = os.path.join(self.boot, installer.PAYLOAD)
        with contextlib.redirect_stdout(io.StringIO()):
            mkpayload.main(["mkpayload", self.pdir, "test-1", "rg34xxsp",
                            "cores|Emulator cores|%s|roms|cores|" % cores,
                            "portmaster|PortMaster|%s|roms|roms/ports|roms/ports/PortMaster" % os.path.join(self.src, "seed")])

    def make(self, device="rg34xxsp"):
        def mount(dev):
            os.makedirs(self.roms, exist_ok=True)
        return installer.Installer(boot=self.boot, roms=self.roms, partition=lambda: "/dev/fake-roms", mount=mount, device=device)

    def p(self, *a):
        return os.path.join(self.roms, *a)


class Payload(Card):
    def test_manifest_matches_the_archives(self):
        man = installer.load_manifest(self.pdir, "rg34xxsp")
        self.assertEqual([c["id"] for c in man["components"]], ["cores", "portmaster"])
        for c in man["components"]:
            with open(os.path.join(self.pdir, c["archive"]), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), c["sha256"])
        cores = man["components"][0]
        self.assertEqual((cores["dest"], cores["target"]), ("roms", "cores"))
        self.assertGreater(cores["bytes"], 0)
        self.assertEqual(man["components"][1]["if_missing"], "roms/ports/PortMaster")

    def test_payload_for_another_device_is_refused(self):
        with self.assertRaises(installer.InstallError) as cm:
            installer.load_manifest(self.pdir, "rg35xxh")
        self.assertIn("rg34xxsp", str(cm.exception))

    def test_bad_manifests_are_refused(self):
        path = os.path.join(self.pdir, installer.MANIFEST)
        with open(path) as f:
            good = json.load(f)
        cases = []
        for key, val in (("archive", "../evil.tar.gz"), ("archive", "a/b.tar.gz"), ("sha256", "zz"), ("dest", "system"),
                         ("target", "../x"), ("target", "/abs"), ("if_missing", "a/../../b"), ("bytes", -1), ("id", "bad id")):
            m = json.loads(json.dumps(good))
            m["components"][0][key] = val
            cases.append(m)
        for m in cases:
            with open(path, "w") as f:
                json.dump(m, f)
            with self.assertRaises(installer.InstallError, msg=str(m["components"][0])):
                installer.load_manifest(self.pdir, "rg34xxsp")
        with open(path, "w") as f:
            f.write("{not json")
        with self.assertRaises(installer.InstallError):
            installer.load_manifest(self.pdir, "rg34xxsp")

    def test_mkpayload_skips_symlinks_and_leaves_out_empty_components(self):
        d = os.path.join(self.tmp, "x")
        os.makedirs(os.path.join(d, "sub"))
        with open(os.path.join(d, "sub", "a.txt"), "w") as f:
            f.write("a")
        os.symlink("/etc/passwd", os.path.join(d, "link"))
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        out = os.path.join(self.tmp, "out")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            mkpayload.main(["mkpayload", out, "t", "rg-rotate", "x|X|%s|boot||" % d, "e|E|%s|roms||" % empty])
        man = installer.load_manifest(out, "rg-rotate")
        self.assertEqual([c["id"] for c in man["components"]], ["x"])
        with tarfile.open(os.path.join(out, "x.tar.gz")) as tf:
            self.assertEqual(sorted(tf.getnames()), ["sub", "sub/a.txt"])

    def test_mkpayload_rejects_bad_input(self):
        for args in (["o", "bad id", "rg34xxsp", "a|A|/tmp|roms||"], ["o", "t", "gameboy", "a|A|/tmp|roms||"],
                     ["o", "t", "rg34xxsp", "a|A|/tmp|system||"], ["o", "t", "rg34xxsp", "a|A|/tmp|roms|../x|"],
                     ["o", "t", "rg34xxsp", "a|A|/nonexistent-folder|roms||"], ["o", "t", "rg34xxsp", "only|three|fields"]):
            args[0] = os.path.join(self.tmp, "o")
            with self.assertRaises(SystemExit, msg=args), contextlib.redirect_stderr(io.StringIO()):
                mkpayload.main(["mkpayload"] + args)


class WhenItRuns(Card):
    def test_pending_only_for_a_card_with_a_payload_that_is_not_installed(self):
        self.assertEqual(installer.pending(self.boot), self.pdir)
        self.assertIsNone(installer.pending(os.path.join(self.tmp, "nothing")))
        with open(os.path.join(self.boot, installer.OPTIONS_FILE), "w") as f:
            f.write("skip_install=1\n")
        self.assertIsNone(installer.pending(self.boot))
        os.remove(os.path.join(self.boot, installer.OPTIONS_FILE))
        with open(os.path.join(self.boot, installer.DONE_FILE), "w") as f:
            f.write("{}")
        self.assertIsNone(installer.pending(self.boot))

    def test_options_file(self):
        with open(os.path.join(self.boot, installer.OPTIONS_FILE), "w", encoding="utf-8-sig") as f:
            f.write("# comment\r\nKeep_Payload = YES\r\nskip = cores , extras\r\njunk\r\nskip_install=0\r\n")
        o = installer.read_options(self.boot)
        self.assertEqual((o["keep_payload"], o["skip_install"], o["skip"]), (True, False, {"cores", "extras"}))
        self.assertEqual(installer.read_options(os.path.join(self.tmp, "none")), {"skip_install": False, "keep_payload": False, "skip": set()})


class Install(Card):
    def test_full_install(self):
        inst = self.make()
        self.assertTrue(inst.run(), inst.error)
        self.assertTrue(os.path.isfile(self.p("cores", "mgba_libretro.so")))
        self.assertTrue(os.path.isfile(self.p("cores", "snes9x_libretro.so")))
        self.assertTrue(os.path.isfile(self.p("roms", "ports", "PortMaster", "PortMaster.sh")))
        self.assertTrue(os.path.isfile(self.p("roms", "ports", "PortMaster", "pylibs", "harness.py")))
        self.assertTrue(os.access(self.p("roms", "ports", "PortMaster", "PortMaster.sh"), os.X_OK))
        for d in ("bios", "config", "cores", "music", "screenshots", "update", "roms/gba", "roms/psx", "roms/ports", "saves/gba",
                  "states/psx", "saves/gc"):
            self.assertTrue(os.path.isdir(self.p(*d.split("/"))), d)
        self.assertFalse(os.path.exists(self.p("saves", "ports")))
        # rgos-session only copies the boot settings to ROMS when this folder is missing: the installer must not pre-create it
        self.assertFalse(os.path.exists(self.p("rgos-data")))
        with open(os.path.join(self.boot, installer.DONE_FILE)) as f:
            stamp = json.load(f)
        self.assertEqual((stamp["id"], stamp["device"], stamp["components"]), ("test-1", "rg34xxsp", ["cores", "portmaster"]))
        self.assertFalse(os.path.exists(self.pdir), "payload is removed to give the boot partition its space back")
        self.assertFalse(os.path.exists(os.path.join(self.boot, installer.STATE_FILE)))
        self.assertIsNone(installer.pending(self.boot))
        snap = inst.snapshot()
        self.assertEqual((snap["finished"], snap["ok"], snap["error"], snap["fraction"]), (True, True, "", 1.0))
        self.assertTrue(all(s["status"] == "done" for s in snap["steps"]), snap["steps"])
        self.assertEqual([s["id"] for s in snap["steps"]], ["partition", "folders", "cores", "portmaster", "finish"])
        self.assertTrue(os.path.isfile(os.path.join(self.boot, installer.LOG_COPY)))

    def test_keep_payload_option(self):
        with open(os.path.join(self.boot, installer.OPTIONS_FILE), "w") as f:
            f.write("keep_payload=1\n")
        self.assertTrue(self.make().run())
        self.assertTrue(os.path.isfile(os.path.join(self.pdir, installer.MANIFEST)))

    def test_skip_option_leaves_a_component_out(self):
        with open(os.path.join(self.boot, installer.OPTIONS_FILE), "w") as f:
            f.write("skip=cores\n")
        inst = self.make()
        self.assertTrue(inst.run(), inst.error)
        self.assertFalse(os.path.exists(self.p("cores", "mgba_libretro.so")))
        self.assertTrue(os.path.isdir(self.p("cores")), "the folder is still created for the Core Installer")
        self.assertTrue(os.path.isfile(self.p("roms", "ports", "PortMaster", "PortMaster.sh")))
        self.assertNotIn("cores", [s["id"] for s in inst.snapshot()["steps"]])

    def test_an_existing_portmaster_is_never_replaced(self):
        os.makedirs(self.p("roms", "ports", "PortMaster"))
        with open(self.p("roms", "ports", "PortMaster", "PortMaster.sh"), "w") as f:
            f.write("updated by the user\n")
        inst = self.make()
        self.assertTrue(inst.run(), inst.error)
        with open(self.p("roms", "ports", "PortMaster", "PortMaster.sh")) as f:
            self.assertEqual(f.read(), "updated by the user\n")
        self.assertFalse(os.path.exists(self.p("roms", "ports", "PortMaster", "pylibs")))
        self.assertEqual({s["id"]: s["status"] for s in inst.snapshot()["steps"]}["portmaster"], "skip")

    def test_existing_roms_content_survives(self):
        os.makedirs(self.p("roms", "gba"))
        with open(self.p("roms", "gba", "game.gba"), "wb") as f:
            f.write(b"rom")
        self.assertTrue(self.make().run())
        with open(self.p("roms", "gba", "game.gba"), "rb") as f:
            self.assertEqual(f.read(), b"rom")

    def test_progress_never_goes_backwards_and_ends_at_one(self):
        seen = []
        orig = installer.Installer._recalc

        def spy(inst, frac):
            orig(inst, frac)
            seen.append(inst.fraction)
        with mock.patch.object(installer.Installer, "_recalc", spy):
            self.assertTrue(self.make().run())
        self.assertGreater(len(seen), 5)
        self.assertEqual(seen, sorted(seen))
        self.assertTrue(all(0.0 <= x <= 1.0 for x in seen))
        self.assertEqual(seen[-1], 1.0)

    def test_a_damaged_archive_fails_cleanly_and_the_retry_resumes(self):
        arch = os.path.join(self.pdir, "portmaster.tar.gz")
        with open(arch, "rb") as f:
            good = f.read()
        bad = bytearray(good)
        bad[len(bad) // 2] ^= 0xFF
        with open(arch, "wb") as f:
            f.write(bytes(bad))
        inst = self.make()
        self.assertFalse(inst.run())
        snap = inst.snapshot()
        self.assertTrue(snap["finished"] and not snap["ok"] and snap["error"])
        self.assertEqual({s["id"]: s["status"] for s in snap["steps"]}["portmaster"], "fail")
        self.assertFalse(os.path.exists(os.path.join(self.boot, installer.DONE_FILE)))
        self.assertTrue(os.path.isdir(self.pdir), "the payload stays so the next boot can try again")
        with open(os.path.join(self.boot, installer.STATE_FILE)) as f:
            self.assertEqual(json.load(f)["done"], ["cores"])
        self.assertTrue(os.path.isfile(os.path.join(self.boot, installer.LOG_COPY)))
        with open(arch, "wb") as f:
            f.write(good)
        again = self.make()
        self.assertTrue(again.run(), again.error)
        self.assertEqual({s["id"]: s["status"] for s in again.snapshot()["steps"]}["cores"], "skip")
        self.assertTrue(os.path.isfile(self.p("roms", "ports", "PortMaster", "PortMaster.sh")))

    def test_a_missing_archive_is_reported(self):
        os.remove(os.path.join(self.pdir, "cores.tar.gz"))
        inst = self.make()
        self.assertFalse(inst.run())
        self.assertIn("cores.tar.gz", inst.error)

    def test_wrong_device_stops_before_touching_the_card(self):
        called = []
        inst = installer.Installer(boot=self.boot, roms=self.roms, partition=lambda: called.append("partition"),
                                   mount=lambda d: called.append("mount"), device="rg35xxh")
        self.assertFalse(inst.run())
        self.assertIn("rg34xxsp", inst.error)
        self.assertEqual(called, [])

    def test_partition_failure_shows_its_message(self):
        def boom():
            raise installer.InstallError("the ROMS partition was not created")
        inst = installer.Installer(boot=self.boot, roms=self.roms, partition=boom, mount=lambda d: None, device="rg34xxsp")
        self.assertFalse(inst.run())
        self.assertEqual(inst.error, "the ROMS partition was not created")
        self.assertEqual(inst.snapshot()["steps"][0]["status"], "fail")

    def test_unexpected_exceptions_become_a_screen_message(self):
        def boom():
            raise RuntimeError("kaboom")
        inst = installer.Installer(boot=self.boot, roms=self.roms, partition=boom, mount=lambda d: None, device="rg34xxsp")
        self.assertFalse(inst.run())
        self.assertIn("kaboom", inst.error)

    def test_too_small_a_roms_partition_is_refused(self):
        usage = namedtuple("usage", "total used free")
        with mock.patch.object(installer.shutil, "disk_usage", return_value=usage(10 << 20, 0, 1 << 20)):
            inst = self.make()
            self.assertFalse(inst.run())
        self.assertIn("too small", inst.error)
        self.assertFalse(os.path.exists(self.p("cores", "mgba_libretro.so")))


class Extract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rgos-ext-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(installer, "LOG_FILE", os.path.join(self.tmp, "l.log"))
        p.start()
        self.addCleanup(p.stop)

    def tar(self, members):
        path = os.path.join(self.tmp, "a.tar.gz")
        with tarfile.open(path, "w:gz") as tf:
            for name, kind, data in members:
                ti = tarfile.TarInfo(name)
                if kind == "file":
                    ti.size = len(data)
                    tf.addfile(ti, io.BytesIO(data))
                elif kind == "dir":
                    ti.type = tarfile.DIRTYPE
                    tf.addfile(ti)
                elif kind == "symlink":
                    ti.type, ti.linkname = tarfile.SYMTYPE, "/etc/passwd"
                    tf.addfile(ti)
        with open(path, "rb") as f:
            return path, hashlib.sha256(f.read()).hexdigest()

    def test_paths_that_leave_the_target_are_refused(self):
        for name in ("../evil", "a/../../evil", "/etc/evil", "a\\b"):
            arch, sha = self.tar([(name, "file", b"x")])
            root = os.path.join(self.tmp, "root")
            with self.assertRaises(installer.InstallError, msg=name):
                installer.extract(arch, root, sha)
            self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil")))
            self.assertFalse(os.path.exists("/etc/evil"))

    def test_symlinks_are_not_created(self):
        arch, sha = self.tar([("ok.txt", "file", b"ok"), ("link", "symlink", b"")])
        root = os.path.join(self.tmp, "root")
        files, _ = installer.extract(arch, root, sha)
        self.assertEqual(files, 1)
        self.assertFalse(os.path.lexists(os.path.join(root, "link")))

    def test_a_write_through_an_existing_symlink_is_refused(self):
        root = os.path.join(self.tmp, "root")
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(root)
        os.makedirs(outside)
        os.symlink(outside, os.path.join(root, "d"))
        arch, sha = self.tar([("d/x.txt", "file", b"x")])
        with self.assertRaises(installer.InstallError):
            installer.extract(arch, root, sha)
        self.assertFalse(os.path.exists(os.path.join(outside, "x.txt")))

    def test_wrong_checksum_is_reported_after_the_stream_ends(self):
        arch, _ = self.tar([("a.txt", "file", b"hello")])
        with self.assertRaises(installer.InstallError) as cm:
            installer.extract(arch, os.path.join(self.tmp, "root"), "0" * 64)
        self.assertIn("checksum", str(cm.exception))

    def test_dot_entries_and_folders(self):
        arch, sha = self.tar([(".", "dir", b""), ("sub", "dir", b""), ("sub/f.txt", "file", b"1")])
        root = os.path.join(self.tmp, "root")
        installer.extract(arch, root, sha)
        self.assertTrue(os.path.isfile(os.path.join(root, "sub", "f.txt")))

    def test_progress_reports_fractions(self):
        arch, sha = self.tar([("a.bin", "file", os.urandom(300000))])
        seen = []
        installer.extract(arch, os.path.join(self.tmp, "root"), sha, seen.append)
        self.assertEqual(seen, sorted(seen))
        self.assertAlmostEqual(seen[-1], 1.0)

    def test_safe_rel(self):
        for ok, want in (("a", "a"), ("./a/b", "a/b"), ("a//b", "a/b"), ("roms/ports", "roms/ports")):
            self.assertEqual(installer.safe_rel(ok), want)
        for bad in ("", ".", "..", "../a", "a/../..", "/a", "a\\b", "a\0b", None, 5):
            self.assertIsNone(installer.safe_rel(bad), repr(bad))


class Wiring(unittest.TestCase):
    def test_canvas_table_matches_the_menu(self):
        self.assertEqual(installer.CANVAS, helpers.load_menu().CANVAS)

    def test_every_menu_system_gets_a_folder_with_saves_and_states(self):
        menu = helpers.load_menu()
        dirs = set(installer.folder_list("/r"))
        for sy in menu.SYSTEMS:
            self.assertIn("/r/roms/%s" % sy[0], dirs, sy[0])
            if sy[2] == "retroarch":
                self.assertIn("/r/saves/%s" % sy[0], dirs)
                self.assertIn("/r/states/%s" % sy[0], dirs)

    def test_devices_known_to_the_installer_are_the_build_devices(self):
        m = re.search(r"^ALL_DEVICES=\(([^)]*)\)", read("build.sh"), re.M)
        self.assertEqual(set(m.group(1).split()), set(installer.DEVICES))
        self.assertEqual(set(installer.DEVICE_NAMES), set(installer.DEVICES))

    def test_session_runs_the_installer_after_the_update_and_before_the_roms_partition_is_made(self):
        s = read("rgos", "rgos-session")
        i_upd, i_inst, i_roms = s.index("rgos-update boot"), s.index("rgos-installer 2>>"), s.index("sh /opt/rgos/rgos-roms")
        self.assertLess(i_upd, i_inst)
        self.assertLess(i_inst, i_roms)
        self.assertIn("[ -f /boot/rgos-payload/manifest.json ] && [ ! -f /boot/rgos-installed.json ]", s)
        self.assertIn("[ $? -eq 10 ] && { sync; reboot -f; sleep 60; }", s[i_inst:i_roms])
        self.assertIn("/var/log/rgos-installer.log", s[s.index("for f in /var/log/rgos-menu.log"):])

    def test_session_hook_and_installer_agree_on_the_file_names(self):
        s = read("rgos", "rgos-session")
        self.assertIn("/boot/%s/%s" % (installer.PAYLOAD, installer.MANIFEST), s)
        self.assertIn("/boot/%s" % installer.DONE_FILE, s)
        self.assertEqual(installer.EXIT_REBOOT, 10)

    def test_build_has_an_installer_mode(self):
        b = read("build.sh")
        self.assertIn('"$MODE" == "installer"', b)
        self.assertIn("tools/mkpayload.py", b)
        self.assertIn("rgos-payload", b)
        self.assertIn('IMG="$OUT/$DEVICE-rgos-installer.img"', b)
        self.assertIn("[image|installer|update]", b)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "tools", "mkpayload.py")))

    def test_installer_script_compiles_and_is_copied_by_the_build(self):
        compile(read("rgos", "rgos-installer"), "rgos-installer", "exec")
        self.assertIn('find "$HERE_RGOS" -maxdepth 1 -type f -exec cp {} "$ROOTFS/opt/rgos/" \\;', read("build.sh"))

    def test_docs_and_ci_mention_the_installer(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "docs", "INSTALLER.md")))
        self.assertIn("INSTALLER.md", read("docs", "README.md"))
        wf = read(".github", "workflows", "build-rgos.yml")
        self.assertIn("- installer", wf)
        self.assertIn("rgos-installer.img", wf)


class FakeFont:
    def size(self, text):
        return (8 * len(text), 16)

    def render(self, text, aa, color):
        s = mock.MagicMock()
        s.get_width.return_value = 8 * len(text)
        return s


class Screen(unittest.TestCase):
    """The drawing code runs against a mocked pygame: no layout error, no crash in any state."""

    def snap(self, **kw):
        base = {"steps": [{"id": "partition", "name": "Partitioning the SD card", "weight": 10, "status": "done"},
                          {"id": "cores", "name": "Installing Emulator cores", "weight": 50, "status": "run"},
                          {"id": "portmaster", "name": "Installing PortMaster", "weight": 30, "status": "pending"},
                          {"id": "x", "name": "Skipped one", "weight": 1, "status": "skip"},
                          {"id": "finish", "name": "Finishing up", "weight": 3, "status": "pending"}],
                "current": 1, "fraction": 0.42, "detail": "Emulator cores  71%", "error": "", "finished": False, "ok": False,
                "indeterminate": False, "device": "rg34xxsp", "id": "t"}
        base.update(kw)
        return base

    def test_every_state_draws(self):
        ui = load_ui()
        pg, canvas = mock.MagicMock(), mock.MagicMock()
        fonts = (FakeFont(), FakeFont(), FakeFont())
        for dev, size in installer.CANVAS.items():
            for snap, cd in ((self.snap(), None), (self.snap(indeterminate=True, fraction=0.0), None),
                             (self.snap(fraction=1.0, finished=True, ok=True), 3.2),
                             (self.snap(error="the ROMS partition was not created (see /var/log/rgos-roms.log) " * 3, finished=True),
                              None),
                             (self.snap(device="", steps=[]), None)):
                ui.draw(pg, canvas, size, fonts, snap, 1.5, cd)
        self.assertTrue(canvas.blit.called)

    def test_wrap(self):
        ui = load_ui()
        lines = ui.wrap(FakeFont(), "one two three four five six", 8 * 10)
        self.assertTrue(all(len(x) <= 10 or " " not in x for x in lines))
        self.assertEqual(" ".join(lines), "one two three four five six")
        self.assertEqual(ui.wrap(FakeFont(), "averyveryverylongwordwithoutspaces", 8 * 5), ["averyveryverylongwordwithoutspaces"])

    def test_nothing_to_do_exits_zero_without_a_screen(self):
        ui = load_ui()
        with mock.patch.object(ui.installer, "pending", return_value=None):
            self.assertEqual(ui.main(), 0)

    def test_without_a_working_screen_the_install_still_runs(self):
        ui = load_ui()
        inst = mock.MagicMock()
        inst.snapshot.return_value = {"ok": True, "error": ""}
        with mock.patch.object(ui, "open", mock.mock_open(), create=True):
            self.assertEqual(ui.show_headless(inst), installer.EXIT_REBOOT)
        inst.snapshot.return_value = {"ok": False, "error": "x"}
        with mock.patch.object(ui, "open", mock.mock_open(), create=True):
            self.assertEqual(ui.show_headless(inst), 0)


if __name__ == "__main__":
    unittest.main()
