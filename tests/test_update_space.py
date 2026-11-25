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


if __name__ == "__main__":
    unittest.main()
