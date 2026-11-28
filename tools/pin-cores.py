#!/usr/bin/env python3
"""Fill cores.conf with real versions: the commit each core's upstream repo is at right now.

usage: tools/pin-cores.py [--all] [--unpin] [--dry-run] [--conf PATH] [CORE_REF ...]
  (no option)  every empty <CORE>_REF= gets the current commit hash of its repo (settings that already have a value are kept)
  --all        also replace values that are already set (re-pin everything to what upstream is at now)
  --unpin      clear every value again (the build follows the latest source)
  --dry-run    print what would change, write nothing
  CORE_REF     only these settings, e.g.  tools/pin-cores.py N64_REF PSX_REF
Needs git and network access. A commit hash is used (not a tag) because most libretro cores have no release tags; the build
fetches it directly, see git_fetch in tools/cores-lib.sh. Repos honour the same <CORE>_REPO overrides as build.sh.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = "https://github.com/"
# setting -> (repo variable, default repo, ref to ask git about). Same repos as build.sh / build-cores.sh.
SOURCES = {
    "NGP_REF": ("NGP_REPO", GH + "libretro/beetle-ngp-libretro.git", "refs/heads/master"),
    "GENESIS_REF": ("GENESIS_REPO", GH + "libretro/Genesis-Plus-GX.git", "HEAD"),
    "PSX_REF": ("PSX_REPO", GH + "libretro/pcsx_rearmed.git", "HEAD"),
    "GC_REF": ("GC_REPO", GH + "libretro/dolphin.git", "HEAD"),
    "DC_REF": ("DC_REPO", GH + "flyinghead/flycast.git", "HEAD"),
    "N64_REF": ("N64_REPO", GH + "libretro/mupen64plus-libretro-nx.git", "HEAD"),
    "SATURN_REF": ("SATURN_REPO", GH + "libretro/yabause.git", "refs/heads/yabasanshiro"),
    "PICO8_REF": ("PICO8_REPO", GH + "jtothebell/fake-08.git", "HEAD"),
    "PICO8_ALT_REF": ("PICO8_ALT_REPO", GH + "libretro/retro8.git", "HEAD"),
    "STELLA_REF": ("STELLA_REPO", GH + "libretro/stella2014-libretro.git", "HEAD"),
    "ATARI800_REF": ("ATARI800_REPO", GH + "libretro/libretro-atari800.git", "HEAD"),
    "PROSYSTEM_REF": ("PROSYSTEM_REPO", GH + "libretro/prosystem-libretro.git", "HEAD"),
    "MAME2003_REF": ("MAME2003_REPO", GH + "libretro/mame2003-plus-libretro.git", "HEAD"),
    "MAME_REF": ("MAME_REPO", GH + "libretro/mame.git", "HEAD"),
}
COMMENT_COL = 20   # the "# description" column of an empty setting in cores.conf; a long hash pushes it right
LINE_RE = re.compile(r"^(?P<key>[A-Z0-9_]+_REF)(?P<eq>\s*=)\s*(?P<val>[^\s#]*)(?P<rest>.*)$")


def current_commit(setting, env=os.environ):
    """The commit hash `setting`'s repo is at now (raises RuntimeError when it cannot be read)."""
    var, default, ref = SOURCES[setting]
    repo = env.get(var) or default
    try:
        out = subprocess.run(["git", "ls-remote", repo, ref, ref + "^{}"], capture_output=True, text=True, timeout=90).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("%s: cannot run git ls-remote (%s)" % (setting, e))
    rows = [ln.split("\t") for ln in out.splitlines() if "\t" in ln]
    if not rows or not re.fullmatch(r"[0-9a-f]{40}", rows[-1][0]):
        raise RuntimeError("%s: cannot read %s of %s (offline, or the repo moved?)" % (setting, ref, repo))
    return rows[-1][0]


def update(text, wanted=None, replace_all=False, unpin=False, lookup=current_commit):
    """Return (new text, [(setting, old, new)]). Comments and line endings stay as they are; the '# description' stays in its column
    (pushed right by a hash). `lookup(setting)` gives the commit for one setting."""
    changes, out = [], []
    for raw in text.splitlines(keepends=True):
        body = raw.rstrip("\r\n")
        end = raw[len(body):]
        m = LINE_RE.match(body)
        if not m or m.group("key") not in SOURCES or (wanted and m.group("key") not in wanted):
            out.append(raw)
            continue
        key, old = m.group("key"), m.group("val")
        if unpin:
            new = ""
        elif old and not replace_all:
            new = old
        else:
            new = lookup(key)
        if new == old:
            out.append(raw)
            continue
        head, comment = key + m.group("eq") + new, m.group("rest").lstrip()
        out.append(head + (" " * max(1, COMMENT_COL - len(head)) + comment if comment else "") + end)
        changes.append((key, old, new))
    return "".join(out), changes


def main(argv):
    conf, wanted, flags = os.path.join(HERE, "cores.conf"), [], set()
    it = iter(argv)
    for a in it:
        if a == "--conf":
            conf = next(it, "")
        elif a in ("--all", "--unpin", "--dry-run"):
            flags.add(a)
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        elif a in SOURCES:
            wanted.append(a)
        else:
            print("unknown argument '%s' (see --help)" % a, file=sys.stderr)
            return 2
    with open(conf, newline="") as f:
        text = f.read()
    failed = []

    def lookup(setting):
        try:
            v = current_commit(setting)
            print("   %-14s %s" % (setting, v))
            return v
        except RuntimeError as e:
            failed.append(str(e))
            return ""
    new, changes = update(text, wanted, "--all" in flags, "--unpin" in flags, lookup)
    for msg in failed:
        print("!! " + msg, file=sys.stderr)
    if "--dry-run" in flags:
        print("%d setting(s) would change" % len(changes))
        return 1 if failed else 0
    if changes:
        with open(conf, "w", newline="") as f:
            f.write(new)
    print("%s: %d setting(s) changed%s" % (conf, len(changes), ", %d could not be read and were left as they were" % len(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
