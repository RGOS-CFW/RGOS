import importlib.machinery
import importlib.util
import os
import sys
import tempfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RGOS = os.path.join(ROOT, "rgos")

_STUBS = ("pygame", "evpad", "fbout", "splash", "wifictl", "btctl", "sshctl", "filemanager", "sdcard", "hwctl")
_cache = {}


def sandbox():
    return tempfile.mkdtemp(prefix="rgos-test-")


def load_menu():
    if "menu" in _cache:
        return _cache["menu"]
    tmp = sandbox()
    os.environ.setdefault("RGOS_RUN", os.path.join(tmp, "run"))
    os.environ.setdefault("RGOS_BTNMAP", os.path.join(tmp, "button-map.json"))
    os.environ.setdefault("RGOS_ROMS", os.path.join(tmp, "roms"))
    os.environ.setdefault("RGOS_STATE", os.path.join(tmp, "state.json"))
    os.environ.setdefault("RGOS_CALIBDONE", os.path.join(tmp, "calibrated"))
    saved = {n: sys.modules.get(n) for n in _STUBS}
    for n in _STUBS:
        sys.modules[n] = mock.MagicMock(name=n)
    sys.path.insert(0, RGOS)
    try:
        spec = importlib.util.spec_from_file_location("rgos_menu", os.path.join(RGOS, "menu.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(RGOS)
        for n, old in saved.items():
            if old is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = old
    _cache["menu"] = mod
    return mod


def fresh_wizard_env(menu):
    tmp = sandbox()
    run = os.path.join(tmp, "run")
    os.makedirs(run)
    menu.RUN_DIR = run
    menu.BTN_MAP = os.path.join(tmp, "button-map.json")
    menu.set_swap_ab = lambda on: None
    menu.restart_hub = lambda: None
    return run, menu.BTN_MAP


def load_hub():
    if "hub" not in _cache:
        loader = importlib.machinery.SourceFileLoader("rgos_input", os.path.join(RGOS, "rgos-input"))
        spec = importlib.util.spec_from_loader("rgos_input", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        _cache["hub"] = mod
    return _cache["hub"]
