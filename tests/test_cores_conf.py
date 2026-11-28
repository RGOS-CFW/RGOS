import os
import re
import subprocess
import tempfile
import unittest

from tests import helpers


def read(*parts):
    with open(os.path.join(helpers.ROOT, *parts), newline="") as f:
        return f.read()


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=n", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


class CoresConfWiringTests(unittest.TestCase):
    def test_every_setting_in_cores_conf_is_known_to_the_lib(self):
        lib = read("tools", "cores-lib.sh")
        keys = re.findall(r"^([A-Z0-9_]+_REF)=", read("cores.conf"), re.M)
        self.assertEqual(len(keys), 14)
        for k in keys:
            self.assertIn(k, lib, k)

    def test_cores_conf_defaults_to_the_latest_source(self):
        for line in read("cores.conf").splitlines():
            if re.match(r"[A-Z0-9_]+_REF=", line):
                self.assertEqual(line.split("=", 1)[1].split("#")[0].strip(), "", line)

    def test_the_build_scripts_no_longer_clone_directly(self):
        for f in ("build.sh", "build-cores.sh"):
            self.assertNotIn("git clone", read(f), f)
            self.assertIn("cores-lib.sh", read(f), f)

    def test_the_image_records_what_was_built(self):
        self.assertIn("/etc/rgos/cores-built.txt", read("build.sh"))

    def test_scripts_are_valid_shell(self):
        for f in ("build.sh", "build-cores.sh", os.path.join("tools", "cores-lib.sh")):
            self.assertEqual(subprocess.run(["bash", "-n", os.path.join(helpers.ROOT, f)]).returncode, 0, f)


class GitFetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.up = os.path.join(t, "up")
        os.makedirs(self.up)
        git(self.up, "init", "-q")
        for n, tag in (("one", "v1"), ("two", None)):
            with open(os.path.join(self.up, "f"), "w") as f:
                f.write(n)
            git(self.up, "add", "f")
            git(self.up, "commit", "-qm", n)
            if tag:
                git(self.up, "tag", tag)
                self.c1 = git(self.up, "rev-parse", "HEAD")
        self.conf = os.path.join(t, "cores.conf")

    def tearDown(self):
        self.tmp.cleanup()

    def run_lib(self, conf, script, env=None):
        with open(self.conf, "w") as f:
            f.write(conf)
        full = 'set -e; HERE=%s; CORES_CONF=%s; source "$HERE/tools/cores-lib.sh"; load_cores_conf; CORES_LOG=%s/log\n%s' % (
            helpers.ROOT, self.conf, self.tmp.name, script)
        return subprocess.run(["bash", "-c", full], capture_output=True, text=True, env=dict(os.environ, **(env or {})))

    def content(self, name):
        with open(os.path.join(self.tmp.name, name, "f")) as f:
            return f.read()

    def test_tag_commit_and_latest(self):
        r = self.run_lib("N64_REF = v1  # tag\nPSX_REF=%s\n" % self.c1,
                         'git_fetch n64 %s %s/a 1; git_fetch psx %s %s/b 1; git_fetch genesis %s %s/c 0' % ((self.up, self.tmp.name) * 3))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.content("a"), self.content("b"), self.content("c")), ("one", "one", "two"))
        log = open(os.path.join(self.tmp.name, "log")).read()
        self.assertIn("n64|%s|v1|%s" % (self.up, self.c1), log)
        self.assertIn("genesis|%s|latest|" % self.up, log)

    def test_a_missing_ref_fails_instead_of_using_the_latest(self):
        r = self.run_lib("DC_REF=nope\n", "git_fetch flycast %s %s/d 1" % (self.up, self.tmp.name))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("cannot fetch 'nope'", r.stderr)

    def test_environment_overrides_the_file_even_when_empty(self):
        r = self.run_lib("N64_REF=v1\n", 'git_fetch n64 %s %s/e 1' % (self.up, self.tmp.name), env={"N64_REF": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.content("e"), "two")

    def test_unknown_keys_and_odd_characters_are_ignored(self):
        r = self.run_lib("BOGUS=1\nN64_REF=$(touch /tmp/pwned)\n", "echo \"[${N64_REF}]\"")
        self.assertEqual(r.stdout.strip(), "[]")
        self.assertIn("unknown setting 'BOGUS'", r.stderr)
        self.assertFalse(os.path.exists("/tmp/pwned"))


if __name__ == "__main__":
    unittest.main()
