import os, struct, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rgos"))
import nativebin as nb


def elf(machine=nb.EM_AARCH64, etype=nb.ET_DYN, interp=b"/lib/ld-linux-aarch64.so.1\0", bits=64):
    """Minimal ELF64 little-endian with one PT_INTERP header."""
    ph_off = 64
    data_off = ph_off + 56
    hdr = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\0" * 8
    hdr += struct.pack("<HHIQQQIHHHHHH", etype, machine, 1, 0, ph_off, 0, 0, 64, 56, 1 if interp else 0, 0, 0, 0)
    ph = struct.pack("<IIQQQQQQ", nb.PT_INTERP, 4, data_off, 0, 0, len(interp), len(interp), 1) if interp else b""
    return hdr + ph + interp


class NativeBinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rgos-nb-")

    def put(self, name, data, mode=0o644):
        p = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        os.chmod(p, mode)
        return p

    def test_reads_arch_type_and_interpreter(self):
        i = nb.read_elf(self.put("g", elf()))
        self.assertEqual((i["bits"], i["machine"], i["interp"]), (64, nb.EM_AARCH64, "/lib/ld-linux-aarch64.so.1"))

    def test_non_elf_is_none(self):
        self.assertIsNone(nb.read_elf(self.put("t", b"hello world, not elf at all, long enough to pass 64 bytes.......")))

    def test_any_file_name_counts_as_a_port_binary(self):
        for n in ("game", "game.aarch64", "Game.ARM64", "game.bin", "game.x"):
            self.assertTrue(nb.is_port_binary(self.put(n, elf())), n)

    def test_libraries_data_and_other_cpus_are_not_ports(self):
        self.assertFalse(nb.is_port_binary(self.put("libfoo.so", elf())))
        self.assertFalse(nb.is_port_binary(self.put("libfoo.so.1.2", elf())))
        self.assertFalse(nb.is_port_binary(self.put("x86game", elf(machine=nb.EM_X86_64))))
        self.assertFalse(nb.is_port_binary(self.put(".hidden", elf())))
        self.assertFalse(nb.is_port_binary(self.put("readme.txt", elf())))

    def test_wrong_cpu_gets_a_clear_message(self):
        r = nb.plan(self.put("x", elf(machine=nb.EM_X86_64)))
        self.assertFalse(r["cmd"])
        self.assertIn("x86-64", r["error"])

    def test_script_without_extension_uses_its_interpreter(self):
        r = nb.plan(self.put("run", b"#!/bin/sh\necho hi\n"))
        self.assertEqual(r["cmd"][1], os.path.join(self.tmp, "run"))
        self.assertTrue(r["cmd"][0].endswith("sh"))

    def test_garbage_is_rejected(self):
        self.assertFalse(nb.plan(self.put("junk", b"\0\1\2 binary junk"))["cmd"])

    def test_lib_folders_next_to_the_port_are_found_and_foreign_arch_ones_ignored(self):
        p = self.put("game", elf())
        for d in ("lib", "libs.aarch64", "libs.armhf"):
            os.makedirs(os.path.join(self.tmp, d))
        dirs = nb.lib_dirs(p)
        self.assertIn(os.path.join(self.tmp, "libs.aarch64"), dirs)
        self.assertIn(os.path.join(self.tmp, "lib"), dirs)
        self.assertNotIn(os.path.join(self.tmp, "libs.armhf"), dirs)

    def test_armhf_port_without_loader_is_explained(self):
        p = self.put("g32", elf(machine=nb.EM_ARM, interp=b"/nonexistent/ld-linux-armhf.so.3\0"))
        r = nb.plan(p)
        if not nb.find_loader(nb.read_elf(p)):
            self.assertFalse(r["cmd"])
            self.assertIn("loader", r["title"])

    def test_armhf_port_uses_a_loader_it_ships(self):
        p = self.put("g32", elf(machine=nb.EM_ARM, interp=b"/nonexistent/ld-linux-armhf.so.3\0"))
        ld = self.put("libs.armhf/ld-linux-armhf.so.3", b"x")
        if os.path.isfile("/lib/ld-linux-armhf.so.3"):
            self.skipTest("host has an armhf loader")
        self.assertEqual(nb.plan(p, chmod=False)["cmd"], [ld, p])

    def test_binary_without_exec_bit_runs_through_the_loader(self):
        ld = self.put("ldso", b"x")
        p = self.put("game", elf(interp=ld.encode() + b"\0"), mode=0o644)
        r = nb.plan(p, chmod=False)
        self.assertEqual(r["cmd"], [ld, p])
        self.assertTrue(r["note"])

    def test_executable_binary_runs_directly_with_lib_path(self):
        ld = self.put("ldso", b"x")
        p = self.put("game", elf(interp=ld.encode() + b"\0"), mode=0o755)
        os.makedirs(os.path.join(self.tmp, "libs"))
        r = nb.plan(p)
        self.assertEqual(r["cmd"], [p])
        self.assertIn(os.path.join(self.tmp, "libs"), r["env"]["LD_LIBRARY_PATH"])


if __name__ == "__main__":
    unittest.main()
