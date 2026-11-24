import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ScriptLineEndingTests(unittest.TestCase):
    def test_no_script_has_windows_line_endings(self):
        bad = []
        for dp, dn, fn in os.walk(ROOT):
            if ".git" in dp.split(os.sep) or os.path.relpath(dp, ROOT).startswith("tests"):
                continue
            for f in fn:
                p = os.path.join(dp, f)
                with open(p, "rb") as fh:
                    b = fh.read()
                if (b[:2] == b"#!" or f == "rgos-wifi-dhcp") and b"\r\n" in b:
                    bad.append(os.path.relpath(p, ROOT))
        self.assertEqual(bad, [], "CRLF breaks '#!/bin/sh\\r' on the device: convert to LF")


if __name__ == "__main__":
    unittest.main()
