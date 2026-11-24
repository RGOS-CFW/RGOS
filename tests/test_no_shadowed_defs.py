import ast
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ShadowedDefinitionTests(unittest.TestCase):
    def test_no_module_defines_the_same_function_twice(self):
        dups = []
        for p in glob.glob(os.path.join(ROOT, "rgos", "*.py")) + [os.path.join(ROOT, "rgos", "rgos-launch")]:
            with open(p) as f:
                tree = ast.parse(f.read())
            seen = {}
            for n in tree.body:
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                    if n.name in seen:
                        dups.append("%s: %s (lines %d and %d)" % (os.path.basename(p), n.name, seen[n.name], n.lineno))
                    seen[n.name] = n.lineno
        self.assertEqual(dups, [], "a later def silently replaces the earlier one")


if __name__ == "__main__":
    unittest.main()
