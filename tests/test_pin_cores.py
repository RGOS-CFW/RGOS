import importlib.util
import os
import re
import subprocess
import tempfile
import unittest

from tests import helpers

spec = importlib.util.spec_from_file_location("pin_cores", os.path.join(helpers.ROOT, "tools", "pin-cores.py"))
pin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin)


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=n", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def conf_text():
    with open(os.path.join(helpers.ROOT, "cores.conf"), newline="") as f:
        return f.read()


class PinCoresTests(unittest.TestCase):
    def test_every_setting_in_cores_conf_has_a_source(self):
        keys = re.findall(r"^([A-Z0-9_]+_REF)=", conf_text(), re.M)
        self.assertEqual(sorted(keys), sorted(pin.SOURCES))

    def test_fills_empty_settings_and_keeps_the_rest_of_the_file(self):
        text = conf_text()
        new, changes = pin.update(text, lookup=lambda k: "a" * 40)
        self.assertEqual(len(changes), len(pin.SOURCES))
        self.assertEqual(len(re.findall(r"^[A-Z0-9_]+_REF=a{40} +# ", new, re.M)), len(pin.SOURCES))
        self.assertEqual(new.count("\n"), text.count("\n"))
        self.assertEqual(new.split("\n\n")[0], text.split("\n\n")[0])

    def test_existing_values_are_kept_unless_all(self):
        new, _ = pin.update(conf_text(), lookup=lambda k: "a" * 40)
        again, changes = pin.update(new, lookup=lambda k: "b" * 40)
        self.assertEqual((again, changes), (new, []))
        replaced, changes = pin.update(new, replace_all=True, lookup=lambda k: "b" * 40)
        self.assertEqual(len(changes), len(pin.SOURCES))
        self.assertNotIn("a" * 40, replaced)

    def test_unpin_restores_the_original_file(self):
        text = conf_text()
        new, _ = pin.update(text, lookup=lambda k: "a" * 40)
        self.assertEqual(pin.update(new, unpin=True)[0], text)

    def test_only_the_named_settings_change(self):
        _, changes = pin.update(conf_text(), wanted=["N64_REF"], lookup=lambda k: "c" * 40)
        self.assertEqual([c[0] for c in changes], ["N64_REF"])

    def test_pinned_file_is_accepted_by_the_build_loader(self):
        new, _ = pin.update(conf_text(), lookup=lambda k: "d" * 40)
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "cores.conf")
            with open(p, "w") as f:
                f.write(new)
            r = subprocess.run(["bash", "-c", 'HERE=%s; CORES_CONF=%s; source "$HERE/tools/cores-lib.sh"; load_cores_conf; echo "$N64_REF $MAME_REF"' % (helpers.ROOT, p)],
                               capture_output=True, text=True)
            self.assertEqual(r.stdout.split(), ["d" * 40, "d" * 40], r.stderr)

    def test_reads_the_real_commit_of_a_repo(self):
        with tempfile.TemporaryDirectory() as t:
            git(t, "init", "-q", "-b", "master")
            open(os.path.join(t, "f"), "w").write("x")
            git(t, "add", "f")
            git(t, "commit", "-qm", "one")
            want = git(t, "rev-parse", "HEAD")
            env = {"N64_REPO": t, "NGP_REPO": t}
            self.assertEqual(pin.current_commit("N64_REF", env), want)
            self.assertEqual(pin.current_commit("NGP_REF", env), want)
            with self.assertRaises(RuntimeError):
                pin.current_commit("SATURN_REF", {"SATURN_REPO": t})


if __name__ == "__main__":
    unittest.main()
