import importlib.machinery
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIB = 1 << 20


def load_update():
    path = os.path.join(ROOT, "rgos", "rgos-update")
    loader = importlib.machinery.SourceFileLoader("rgos_update", path)
    spec = importlib.util.spec_from_loader("rgos_update", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


U = load_update()


def plan(new, old, free_mib):
    order = sorted(new, key=lambda n: (new[n], n))
    return U.plan_inplace(order, {k: v * MIB for k, v in new.items()}, {k: v * MIB for k, v in old.items()}, free_mib * MIB)


class PlanInplace(unittest.TestCase):
    def test_everything_fits_next_to_the_old_files(self):
        self.assertEqual(plan({"SYSTEM": 700, "rgos-initrd.cpio": 9}, {"SYSTEM": 690, "rgos-initrd.cpio": 9}, 800), set())

    def test_system_replaces_in_place_when_only_the_old_copy_makes_room(self):
        self.assertEqual(plan({"SYSTEM": 700, "rgos-initrd.cpio": 9}, {"SYSTEM": 690, "rgos-initrd.cpio": 9}, 64), {"SYSTEM"})

    def test_growth_beyond_the_headroom_is_reported_with_numbers(self):
        # new SYSTEM is 80 MiB bigger, only 64 MiB free: the old initrd copy is freed too, still short
        with self.assertRaises(U.UpdateError) as cm:
            plan({"SYSTEM": 770, "rgos-initrd.cpio": 9}, {"SYSTEM": 690, "rgos-initrd.cpio": 9}, 64)
        self.assertIn("MiB short", str(cm.exception))

    def test_earlier_files_are_switched_to_in_place_when_that_is_what_makes_it_fit(self):
        # 64 free - 2 margin = 62; the 20 MiB kernel is staged (42 left). SYSTEM (130) with its own old 85 freed gives 127:
        # still short, so the old kernel's 20 MiB must be freed first as well.
        got = plan({"KERNEL": 20, "SYSTEM": 130}, {"KERNEL": 20, "SYSTEM": 85}, 64)
        self.assertEqual(got, {"KERNEL", "SYSTEM"})

    def test_a_file_with_no_old_copy_never_counts_as_in_place(self):
        self.assertEqual(plan({"SYSTEM": 10}, {}, 100), set())

    def test_too_big_even_with_no_old_files(self):
        with self.assertRaises(U.UpdateError):
            plan({"SYSTEM": 700}, {}, 64)


class BootCleanup(unittest.TestCase):
    """The updater mounts the ROMS partition read-only to look for a tar. It must always let go again, or the session's own
    read-write mount of that partition fails and ROMS silently falls back to the FAT partition."""

    def run_boot(self, apply_exc):
        import tempfile
        d = tempfile.mkdtemp()
        upd = os.path.join(d, "update")
        os.makedirs(upd)
        tar = os.path.join(upd, "rgos-update-rg35xxh-x.tar")
        open(tar, "wb").close()
        calls = []
        saved = {k: getattr(U, k) for k in ("partitions", "ensure_fs", "find_boot", "find_update", "apply_tar", "sh", "LOG_FILE", "TTY", "time")}
        try:
            U.partitions = lambda: ["/dev/mmcblk0p3"]
            U.ensure_fs = lambda: None
            U.find_boot = lambda parts: ("/boot", None)
            U.find_update = lambda parts: ("/dev/mmcblk0p3", d, True, upd, tar)
            U.sh = lambda args, timeout=30: (calls.append(args) or (0, ""))
            U.LOG_FILE, U.TTY = os.path.join(d, "log"), os.devnull

            def boom(*a):
                raise apply_exc
            U.apply_tar = boom
            U.time = type("T", (), {"sleep": staticmethod(lambda s: None), "strftime": staticmethod(__import__("time").strftime)})
            rc = U.cmd_boot()
        finally:
            for k, v in saved.items():
                setattr(U, k, v)
        return rc, calls, d, upd

    def test_unexpected_error_still_unmounts_and_marks_the_tar_failed(self):
        rc, calls, d, upd = self.run_boot(KeyError("SYSTEM"))
        self.assertEqual(rc, 0)
        self.assertIn(["umount", d], calls)
        self.assertTrue(os.path.exists(os.path.join(upd, "rgos-update-rg35xxh-x.tar.failed")))
        with open(os.path.join(upd, "rgos-update.log")) as f:
            self.assertIn("FAILED: unexpected KeyError", f.read())

    def test_update_error_still_unmounts(self):
        rc, calls, d, upd = self.run_boot(U.UpdateError("nope"))
        self.assertEqual(rc, 0)
        self.assertIn(["umount", d], calls)


class StaleTars(unittest.TestCase):
    """A finished tar left on the small FAT boot partition (as .applied / .failed) is as big as SYSTEM and eats the free space
    the next update needs. They are deleted before every update, and a tar that was applied from the boot partition is deleted."""

    def setUp(self):
        import tempfile
        self.d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.d, True)
        self.boot = os.path.join(self.d, "boot")
        os.makedirs(os.path.join(self.boot, "update"))
        os.makedirs(os.path.join(self.boot, "roms", "update"))
        saved = (U.LOG_FILE, U.TTY, U.DEVICE_FILE)
        self.addCleanup(lambda: (setattr(U, "LOG_FILE", saved[0]), setattr(U, "TTY", saved[1]), setattr(U, "DEVICE_FILE", saved[2])))
        U.LOG_FILE, U.TTY = os.path.join(self.d, "log"), os.devnull
        U.DEVICE_FILE = os.path.join(self.d, "device")
        with open(U.DEVICE_FILE, "w") as f:
            f.write("rg35xxh\n")

    def touch(self, rel, size=10):
        path = os.path.join(self.boot, rel)
        with open(path, "wb") as f:
            f.write(b"x" * size)
        return path

    def make_tar(self, uid="new"):
        import hashlib, io, json, tarfile
        system = b"hsqs" + b"\0" * 4096
        man = json.dumps({"format": 1, "id": uid, "device": "rg35xxh", "files": {"SYSTEM": hashlib.sha256(system).hexdigest()}}).encode()
        path = os.path.join(self.boot, "update", "rgos-update-rg35xxh-%s.tar" % uid)
        with tarfile.open(path, "w") as tf:
            for name, data in (("manifest.json", man), ("boot/SYSTEM", system)):
                ti = tarfile.TarInfo(name)
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
        return path

    def test_reclaim_removes_only_finished_tars(self):
        gone = [self.touch("update/a.tar.applied", 2 << 20), self.touch("update/b.tar.failed"), self.touch("roms/update/c.tgz.applied"),
                self.touch("update/D.TAR.APPLIED")]
        kept = [self.touch("update/live.tar"), self.touch("update/rgos-update.log"), self.touch("SYSTEM"), self.touch("roms/zelda.applied")]
        self.assertGreaterEqual(U.reclaim_stale_tars(self.boot), 2 << 20)
        for g in gone:
            self.assertFalse(os.path.exists(g), g)
        for k in kept:
            self.assertTrue(os.path.exists(k), k)

    def test_reclaim_without_update_folders_is_harmless(self):
        import shutil
        shutil.rmtree(os.path.join(self.boot, "update"))
        shutil.rmtree(os.path.join(self.boot, "roms"))
        self.assertEqual(U.reclaim_stale_tars(self.boot), 0)

    def test_apply_frees_old_tars_first(self):
        old = self.touch("update/rgos-update-rg35xxh-old.tar.applied", 1 << 20)
        self.touch("SYSTEM", 100)
        tar = self.make_tar("new")
        status, uid = U.apply_tar(tar, self.boot)
        self.assertEqual((status, uid), ("installed", "new"))
        self.assertFalse(os.path.exists(old))
        with open(os.path.join(self.boot, "SYSTEM"), "rb") as f:
            self.assertEqual(f.read(4), b"hsqs")

    def boot_run(self, tar, apply_result):
        calls = []
        saved = {k: getattr(U, k) for k in ("partitions", "ensure_fs", "find_boot", "find_update", "apply_tar", "sh", "time")}
        try:
            U.partitions = lambda: ["/dev/mmcblk0p1"]
            U.ensure_fs = lambda: None
            U.find_boot = lambda parts: (self.boot, None)
            U.find_update = lambda parts: ("/dev/mmcblk0p1", self.boot, False, os.path.dirname(tar), tar)
            U.sh = lambda args, timeout=30: (calls.append(args) or (0, ""))

            def fake(*a):
                if isinstance(apply_result, Exception):
                    raise apply_result
                return apply_result
            U.apply_tar = fake
            U.time = type("T", (), {"sleep": staticmethod(lambda s: None), "strftime": staticmethod(__import__("time").strftime)})
            return U.cmd_boot()
        finally:
            for k, v in saved.items():
                setattr(U, k, v)

    def test_tar_applied_from_the_boot_partition_is_deleted(self):
        tar = self.touch("update/rgos-update-rg35xxh-new.tar", 1 << 20)
        self.assertEqual(self.boot_run(tar, ("installed", "new")), 10)
        self.assertFalse(os.path.exists(tar))
        self.assertFalse(os.path.exists(tar + ".applied"))
        with open(os.path.join(self.boot, "update", "rgos-update.log")) as f:
            text = f.read()
        self.assertIn("build new installed", text)
        self.assertIn("deleted from the boot partition", text)

    def test_already_installed_tar_on_the_boot_partition_is_deleted_too(self):
        tar = self.touch("update/rgos-update-rg35xxh-new.tar")
        self.assertEqual(self.boot_run(tar, ("same", "new")), 0)
        self.assertFalse(os.path.exists(tar) or os.path.exists(tar + ".applied"))

    def test_failed_tar_on_the_boot_partition_is_kept_as_failed_with_a_hint(self):
        tar = self.touch("update/rgos-update-rg35xxh-new.tar")
        self.assertEqual(self.boot_run(tar, U.UpdateError("nope")), 0)
        self.assertTrue(os.path.exists(tar + ".failed"))
        with open(os.path.join(self.boot, "update", "rgos-update.log")) as f:
            self.assertIn("delete it from a PC", f.read())


if __name__ == "__main__":
    unittest.main()
