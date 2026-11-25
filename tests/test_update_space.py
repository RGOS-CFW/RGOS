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


if __name__ == "__main__":
    unittest.main()
