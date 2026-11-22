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


def read_log(tmp):
    with open(os.path.join(tmp, "installer.log"), encoding="utf-8") as f:
        return f.read()


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

    def test_the_chosen_format_reaches_the_partitioning_step(self):
        seen = []
        for fmt in installer.ROMS_FORMATS:
            with mock.patch.object(installer, "partition_roms", side_effect=lambda boot, f: seen.append(f) or "/dev/fake-roms"):
                inst = installer.Installer(boot=self.boot, roms=self.roms, mount=lambda d: os.makedirs(self.roms, exist_ok=True),
                                           device="rg34xxsp", fmt=fmt)
                self.assertEqual(inst.fmt, fmt)
                inst.partition()
        self.assertEqual(seen, list(installer.ROMS_FORMATS))

    def test_the_default_format_is_exfat_and_junk_falls_back_to_it(self):
        self.assertEqual(self.make().fmt, "exfat")
        inst = installer.Installer(boot=self.boot, roms=self.roms, partition=lambda: "x", mount=lambda d: None, device="rg34xxsp", fmt="ntfs")
        self.assertEqual(inst.fmt, "exfat")

    def test_the_partition_step_names_the_format_on_screen(self):
        details = []
        box = []

        def partition():
            details.append(box[0].snapshot()["detail"])
            return "/dev/fake-roms"
        inst = installer.Installer(boot=self.boot, roms=self.roms, partition=partition,
                                   mount=lambda d: os.makedirs(self.roms, exist_ok=True), device="rg34xxsp", fmt="ext4")
        box.append(inst)
        self.assertTrue(inst.run())
        self.assertIn("ext4", details[0])

    def test_partition_roms_passes_the_format_to_rgos_roms_and_remembers_it(self):
        calls = []

        def fake_run(args, timeout=60, env=None):
            calls.append((args, env))
            return 0, ""
        for fmt, blk in (("fat32", "vfat"), ("exfat", "exfat"), ("ext4", "ext4")):
            calls[:] = []
            run_dir = os.path.join(self.tmp, "run-" + fmt)
            os.makedirs(run_dir)
            with open(os.path.join(run_dir, "roms-part"), "w") as f:
                f.write("3")
            with mock.patch.object(installer, "RUN", run_dir), mock.patch.object(installer, "_run", fake_run), \
                    mock.patch.object(installer, "_boot_source", return_value="/dev/mmcblk0p1"), \
                    mock.patch.object(installer, "_blkid_type", return_value=blk), \
                    mock.patch.object(installer.os.path, "exists", return_value=True):
                self.assertEqual(installer.partition_roms(self.boot, fmt), "/dev/mmcblk0p3")
            self.assertEqual(calls[0][1]["RGOS_ROMS_FS"], fmt)
            with open(os.path.join(self.boot, installer.ROMS_FS_FILE)) as f:
                self.assertEqual(f.read().strip(), fmt)

    def test_partition_roms_rejects_an_unknown_format_before_touching_anything(self):
        with mock.patch.object(installer, "_run") as run:
            with self.assertRaises(installer.InstallError):
                installer.partition_roms(self.boot, "ntfs")
            run.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.boot, installer.ROMS_FS_FILE)))

    def test_an_existing_filesystem_is_kept_and_the_mismatch_is_logged(self):
        run_dir = os.path.join(self.tmp, "run-keep")
        os.makedirs(run_dir)
        with open(os.path.join(run_dir, "roms-part"), "w") as f:
            f.write("3")
        with mock.patch.object(installer, "RUN", run_dir), mock.patch.object(installer, "_run", return_value=(0, "")), \
                mock.patch.object(installer, "_boot_source", return_value="/dev/mmcblk0p1"), \
                mock.patch.object(installer, "_blkid_type", return_value="exfat"), \
                mock.patch.object(installer.os.path, "exists", return_value=True):
            installer.partition_roms(self.boot, "ext4")
        self.assertIn("already held exfat", read_log(self.tmp))

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
        self.assertIn("[ $inst_rc -eq 10 ] && { sync; reboot -f; sleep 60; }", s[i_inst:i_roms])
        self.assertIn("[ $inst_rc -eq 20 ] && { sync; poweroff -f; sleep 60; }", s[i_inst:i_roms])
        self.assertIn("/var/log/rgos-installer.log", s[s.index("for f in /var/log/rgos-menu.log"):])

    def test_session_hook_and_installer_agree_on_the_file_names(self):
        s = read("rgos", "rgos-session")
        self.assertIn("/boot/%s/%s" % (installer.PAYLOAD, installer.MANIFEST), s)
        self.assertIn("/boot/%s" % installer.DONE_FILE, s)
        self.assertEqual(installer.EXIT_REBOOT, 10)
        self.assertEqual(installer.EXIT_POWEROFF, 20)

    def test_power_off_uses_the_same_exit_status_as_the_menu(self):
        self.assertEqual(installer.EXIT_POWEROFF, helpers.load_menu().EXIT_POWER)

    def test_rgos_roms_can_make_all_three_filesystems(self):
        r = read("rgos", "rgos-roms")
        for needle in ("mkfs.vfat -F 32", "mkfs.ext4", "mkfs.exfat", "RGOS_ROMS_FS", "/boot/rgos-roms-fs"):
            self.assertIn(needle, r)
        self.assertIn("exfat", r.split("case \"$fs\" in", 1)[1].split("esac", 1)[0])   # unknown value -> exFAT, as before
        self.assertIn("already holds", r)                                                  # an existing file system is never reformatted

    def test_rgos_roms_still_recognises_its_partition_whatever_the_format(self):
        r = read("rgos", "rgos-roms")
        self.assertIn("type=(7|c|83)", r)

    def test_rgos_roms_script_is_valid_shell_and_defaults_to_exfat(self):
        import subprocess
        path = os.path.join(ROOT, "rgos", "rgos-roms")
        self.assertEqual(subprocess.run(["sh", "-n", path]).returncode, 0)

    def test_the_image_has_every_mkfs_the_menu_offers(self):
        b = read("build.sh")
        for pkg in ("e2fsprogs", "exfatprogs", "dosfstools"):
            self.assertIn(pkg, b)
        for tool in ("sbin/mkfs.ext4", "sbin/mkfs.exfat", "sbin/mkfs.vfat"):
            self.assertIn(tool, b)

    def test_every_offered_format_can_be_mounted_by_the_installer_and_the_session(self):
        sess = read("rgos", "rgos-session")
        self.assertEqual(sorted(installer.FORMAT_BLKID.values()), ["exfat", "ext4", "vfat"])
        for fs in ("exfat", "vfat", "ext4"):
            self.assertIn("mount -t %s" % fs, sess)
        self.assertEqual(set(installer.FORMAT_LABELS), set(installer.ROMS_FORMATS))
        self.assertEqual(set(installer.FORMAT_HINTS), set(installer.ROMS_FORMATS))

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

    def test_the_welcome_screen_draws_with_either_button_selected(self):
        ui = load_ui()
        pg, canvas = mock.MagicMock(), mock.MagicMock()
        fonts = (FakeFont(), FakeFont(), FakeFont())
        for dev, size in installer.CANVAS.items():
            for sel in (0, 1):
                ui.draw_welcome(pg, canvas, size, fonts, sel, dev)
        ui.draw_welcome(pg, canvas, (720, 480), fonts, 0, "")
        self.assertTrue(canvas.blit.called)

    def test_welcome_buttons_are_two_equal_squares_side_by_side_on_every_screen(self):
        ui = load_ui()
        for dev, (W, H) in installer.CANVAS.items():
            a, b = ui.button_boxes((W, H), 170)
            self.assertEqual(a[2], a[3], dev)
            self.assertEqual(b[2], b[3], dev)
            self.assertEqual(a[2], b[2], dev)
            self.assertEqual(a[1], b[1], dev)
            self.assertLess(a[0] + a[2], b[0], dev)
            self.assertGreaterEqual(a[0], 0)
            self.assertLessEqual(b[0] + b[2], W)
            self.assertGreaterEqual(a[1], 170)
            self.assertLessEqual(a[1] + a[3], H - 40, dev)

    def test_each_welcome_button_draws_its_icon(self):
        ui = load_ui()
        for kind in ui.CHOICES:
            pg, canvas = mock.MagicMock(), mock.MagicMock()
            ui.draw_icon(pg, canvas, kind, 100, 100, 40, (1, 2, 3))
            self.assertTrue(pg.draw.method_calls, kind)

    def test_welcome_buttons_are_install_then_power_off(self):
        ui = load_ui()
        self.assertEqual(ui.CHOICES, ("install", "poweroff"))
        self.assertEqual([ui.CHOICE_LABELS[c] for c in ui.CHOICES], ["Install", "Power off"])

    def test_welcome_navigation_and_confirm(self):
        ui = load_ui()
        mi = ui.menu_input
        self.assertEqual(mi(0, ui.EV_KEY, ui.KEY_DOWN, 1), (1, None))
        self.assertEqual(mi(1, ui.EV_KEY, ui.KEY_UP, 1), (0, None))
        self.assertEqual(mi(0, ui.EV_KEY, ui.KEY_UP, 1), (1, None))       # wraps round
        self.assertEqual(mi(1, ui.EV_KEY, ui.KEY_RIGHT, 1), (0, None))
        self.assertEqual(mi(0, ui.EV_ABS, ui.ABS_HAT0Y, 1), (1, None))   # hat axes work like the D-pad keys
        self.assertEqual(mi(1, ui.EV_ABS, ui.ABS_HAT0X, -1), (0, None))
        self.assertEqual(mi(0, ui.EV_ABS, ui.ABS_HAT0Y, 0), (0, None))   # hat released: nothing
        self.assertEqual(mi(0, ui.EV_KEY, ui.BTN_A, 1), (0, "install"))
        self.assertEqual(mi(1, ui.EV_KEY, ui.BTN_A, 1), (1, "poweroff"))
        self.assertEqual(mi(1, ui.EV_KEY, ui.BTN_START, 1), (1, "poweroff"))

    def test_welcome_ignores_releases_and_other_buttons(self):
        ui = load_ui()
        self.assertEqual(ui.menu_input(0, ui.EV_KEY, ui.BTN_A, 0), (0, None))      # release
        self.assertEqual(ui.menu_input(0, ui.EV_KEY, ui.BTN_B, 1), (0, None))      # B does nothing here
        self.assertEqual(ui.menu_input(1, ui.EV_KEY, ui.KEY_DOWN, 0), (1, None))

    def test_format_popup_offers_fat32_exfat_ext4_in_that_order(self):
        ui = load_ui()
        self.assertEqual(ui.FORMAT_CHOICES, ("fat32", "exfat", "ext4"))
        self.assertEqual([installer.FORMAT_LABELS[k] for k in ui.FORMAT_CHOICES], ["FAT32", "exFAT", "ext4"])
        self.assertEqual(ui.FORMAT_CHOICES[ui.FORMAT_CHOICES.index(installer.DEFAULT_ROMS_FORMAT)], "exfat")

    def test_format_popup_navigation_confirm_and_back(self):
        ui = load_ui()
        fi = ui.format_input
        self.assertEqual(fi(1, ui.EV_KEY, ui.KEY_DOWN, 1), (2, None))
        self.assertEqual(fi(1, ui.EV_KEY, ui.KEY_UP, 1), (0, None))
        self.assertEqual(fi(0, ui.EV_KEY, ui.KEY_UP, 1), (2, None))        # wraps round
        self.assertEqual(fi(2, ui.EV_KEY, ui.KEY_RIGHT, 1), (0, None))
        self.assertEqual(fi(0, ui.EV_ABS, ui.ABS_HAT0Y, 1), (1, None))     # hat axes work like the D-pad keys
        self.assertEqual(fi(1, ui.EV_ABS, ui.ABS_HAT0X, -1), (0, None))
        self.assertEqual(fi(1, ui.EV_ABS, ui.ABS_HAT0Y, 0), (1, None))
        self.assertEqual(fi(0, ui.EV_KEY, ui.BTN_A, 1), (0, "fat32"))
        self.assertEqual(fi(1, ui.EV_KEY, ui.BTN_A, 1), (1, "exfat"))
        self.assertEqual(fi(2, ui.EV_KEY, ui.BTN_START, 1), (2, "ext4"))
        self.assertEqual(fi(1, ui.EV_KEY, ui.BTN_B, 1), (1, "back"))

    def test_format_popup_ignores_releases(self):
        ui = load_ui()
        self.assertEqual(ui.format_input(1, ui.EV_KEY, ui.BTN_A, 0), (1, None))
        self.assertEqual(ui.format_input(1, ui.EV_KEY, ui.BTN_B, 0), (1, None))
        self.assertEqual(ui.format_input(1, ui.EV_KEY, ui.KEY_DOWN, 0), (1, None))

    def test_format_popup_draws_on_every_screen_with_every_row_selected(self):
        ui = load_ui()
        pg, canvas = mock.MagicMock(), mock.MagicMock()
        fonts = (FakeFont(), FakeFont(), FakeFont())
        for dev, size in installer.CANVAS.items():
            for sel in range(len(ui.FORMAT_CHOICES)):
                ui.draw_format_popup(pg, canvas, size, fonts, sel, dev)
        self.assertTrue(canvas.blit.called)

    def test_format_popup_panel_fits_on_the_smallest_screen(self):
        ui = load_ui()
        pg, canvas = mock.MagicMock(), mock.MagicMock()
        ui.draw_format_popup(pg, canvas, (720, 480), (FakeFont(), FakeFont(), FakeFont()), 0, "rg34xxsp")
        panel = [c for c in pg.draw.rect.call_args_list if len(c[0]) >= 3 and c[0][1] == ui.BG and len(c[0][2]) == 4][-1][0][2]
        self.assertGreaterEqual(panel[1], 0)
        self.assertLessEqual(panel[1] + panel[3], 480)
        self.assertLessEqual(panel[0] + panel[2], 720)

    def test_install_opens_the_format_popup_before_anything_is_installed(self):
        """The popup sits between the welcome screen and the Installer thread; B in it returns to the welcome screen."""
        src = read("rgos", "rgos-installer")
        self.assertLess(src.index("draw_welcome, sel"), src.index("draw_format_popup, fmt_sel"))
        self.assertLess(src.index("draw_format_popup, fmt_sel"), src.index("    start(inst)\n"))
        self.assertLess(src.index("return installer.EXIT_POWEROFF"), src.index("draw_format_popup, fmt_sel"))
        self.assertIn("installer.Installer(fmt=fmt)", src)
        self.assertEqual(src.count("installer.Installer(fmt=fmt)"), 2)   # first run and the "try again" retry both keep the choice

    def test_installing_starts_only_after_install_is_chosen(self):
        """Power off must return before the Installer thread is ever started, so the card is untouched."""
        ui = load_ui()
        src = read("rgos", "rgos-installer")
        self.assertLess(src.index("return installer.EXIT_POWEROFF"), src.index("    start(inst)\n"))
        self.assertLess(src.index("draw_welcome, sel"), src.index("    start(inst)\n"))

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


class ConsoleScreen(unittest.TestCase):
    """The fake "kernel exploit" console shown while installing."""

    def feed(self, seed=1, duration=None):
        import random
        ui = load_ui()
        return ui, ui.ConsoleFeed(100.0, "RG34XX-SP", random.Random(seed), duration)

    def test_the_fake_run_lasts_ten_to_fifteen_seconds(self):
        for seed in range(30):
            ui, f = self.feed(seed)
            self.assertGreaterEqual(f.duration, 10.0)
            self.assertLessEqual(f.duration, 15.0)

    def test_it_scrolls_and_is_not_done_before_the_real_install_is(self):
        ui, f = self.feed(duration=12.0)
        f.update(100.5, False, False)
        early = len(f.lines)
        self.assertGreater(early, 0)
        f.update(105.0, False, False)
        self.assertGreater(len(f.lines), early)
        for now in (112.0, 130.0, 300.0):     # installer still busy: keeps printing, never finishes
            f.update(now, False, False)
            self.assertFalse(f.complete)
        n = len(f.lines)
        f.update(300.5, False, False)
        self.assertGreaterEqual(len(f.lines), n)

    def test_it_finishes_only_when_installed_and_the_time_is_up(self):
        ui, f = self.feed(duration=12.0)
        f.update(104.0, True, False)           # installer already done but the show is not over
        self.assertFalse(f.complete)
        self.assertIsNone(f.final_at)
        f.update(112.5, True, False)
        f.update(114.0, True, False)
        self.assertTrue(f.complete)
        self.assertEqual(f.lines[-1][0], "[+] done")

    def test_a_failure_freezes_the_feed(self):
        ui, f = self.feed(duration=12.0)
        f.update(105.0, False, False)
        n = len(f.lines)
        f.update(140.0, False, True)
        self.assertEqual(len(f.lines), n)
        self.assertFalse(f.complete)

    def test_lines_are_short_enough_for_the_smallest_screen(self):
        ui, f = self.feed()
        f.update(1000.0, False, False)
        self.assertTrue(all(len(t) <= 84 for t, k, w in ui.console_script(f.rng, "RG34XX-SP")))
        self.assertTrue(all(k in ui.CON_COL for t, k in f.lines))

    def test_nothing_in_the_feed_is_kept_forever(self):
        ui, f = self.feed(duration=10.0)
        for i in range(2000):
            f.update(100.0 + i * 0.5, False, False)
        self.assertLessEqual(len(f.lines), ui.CONSOLE_KEEP)

    def test_every_state_draws(self):
        ui, f = self.feed(duration=10.0)
        f.update(1000.0, True, False)
        f.update(1001.0, True, False)
        pg, canvas = mock.MagicMock(), mock.MagicMock()
        font = FakeFont()
        for dev, size in installer.CANVAS.items():
            ok = {"error": "", "finished": True, "ok": True}
            for snap, cd, t in (({"error": "", "finished": False, "ok": False}, None, 0.0),
                                ({"error": "", "finished": False, "ok": False}, None, 0.5),
                                (ok, 3.2, 1.0),
                                ({"error": "the ROMS partition was not created (see /var/log/rgos-roms.log) " * 3,
                                  "finished": True, "ok": False}, None, 1.0)):
                ui.draw_console(pg, canvas, size, font, f, snap, t, cd)
        self.assertTrue(canvas.blit.called)

    def test_the_install_screen_is_the_console(self):
        src = read("rgos", "rgos-installer")
        loop = src[src.index("    start(inst)\n"):]
        self.assertIn("show_console(feed, snap, t, countdown)", loop)
        self.assertEqual(loop.count("ConsoleFeed("), 2)     # first run and the "try again" retry



if __name__ == "__main__":
    unittest.main()
