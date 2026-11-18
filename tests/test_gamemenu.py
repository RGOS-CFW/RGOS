import importlib.machinery
import importlib.util
import os
import signal
import struct
import sys
import tempfile
import unittest

from tests import helpers

sys.path.insert(0, helpers.RGOS)
import gamemenu as gm  # noqa: E402


def load_launch():
    loader = importlib.machinery.SourceFileLoader("rgos_launch_gm", os.path.join(helpers.RGOS, "rgos-launch"))
    spec = importlib.util.spec_from_loader("rgos_launch_gm", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def measure(text, size, bold=False):
    return int(len(text) * size * 0.6)


class ModelTests(unittest.TestCase):
    def test_items_per_kind(self):
        ids = lambda m: [i for i, _ in m.items()]
        self.assertEqual(ids(gm.MenuModel("retroarch")), ["resume", "restart", "save", "load", "exit"])
        self.assertEqual(ids(gm.MenuModel("native")), ["resume", "restart", "exit"])

    def test_navigation_wraps(self):
        m = gm.MenuModel("native")
        m.press("up")
        self.assertEqual(m.items()[m.sel][0], "exit")
        m.press("down")
        self.assertEqual(m.items()[m.sel][0], "resume")

    def test_resume_and_back(self):
        m = gm.MenuModel("native")
        self.assertEqual(m.press("ok"), "resume")
        self.assertEqual(gm.MenuModel("native").press("back"), "resume")
        self.assertEqual(gm.MenuModel("native").press("close"), "resume")

    def test_restart_asks_first_and_cancel_returns_to_the_row(self):
        m = gm.MenuModel("retroarch")
        m.press("down")
        self.assertIsNone(m.press("ok"))
        self.assertEqual(m.confirm, "restart")
        self.assertEqual(m.sel, 0)                       # defaults to Cancel
        self.assertEqual(m.header()[1], "Restart game?")
        self.assertIsNone(m.press("back"))
        self.assertIsNone(m.confirm)
        self.assertEqual(m.items()[m.sel][0], "restart")

    def test_confirm_yes_runs_the_action(self):
        for ident, steps in (("restart", 1), ("exit", 4)):
            m = gm.MenuModel("retroarch")
            for _ in range(steps):
                m.press("down")
            m.press("ok")
            m.press("down")
            self.assertEqual(m.press("ok"), ident)
            self.assertIsNone(m.confirm)

    def test_save_and_load_are_direct(self):
        m = gm.MenuModel("retroarch")
        m.sel = 2
        self.assertEqual(m.press("ok"), "save")
        m.sel = 3
        self.assertEqual(m.press("ok"), "load")

    def test_status_expires(self):
        m = gm.MenuModel()
        m.say("State saved", 5.0)
        self.assertEqual(m.status_now(4.9), "State saved")
        self.assertEqual(m.status_now(5.0), "")


class InputTests(unittest.TestCase):
    def ev(self, t, c, v):
        return struct.pack("llHHi", 0, 0, t, c, v)

    def test_parse_and_translate(self):
        data = self.ev(1, gm.BTN_A, 1) + self.ev(3, gm.ABS_HAT0Y, -1)
        evs = gm.parse_events(data)
        self.assertEqual([gm.translate(*e) for e in evs], ["ok", "up"])
        self.assertEqual(gm.translate(1, gm.BTN_B, 1), "back")
        self.assertEqual(gm.translate(1, gm.BTN_MODE, 1), "close")
        self.assertEqual(gm.translate(1, gm.DPAD_DOWN, 1), "down")
        self.assertIsNone(gm.translate(1, gm.BTN_A, 0))   # releases do nothing
        self.assertIsNone(gm.translate(3, gm.ABS_HAT0Y, 0))

    def test_tap_opens_on_release(self):
        t = gm.TapDetector()
        self.assertFalse(t.feed(1, gm.BTN_MODE, 1, 10.0))
        self.assertTrue(t.feed(1, gm.BTN_MODE, 0, 10.1))

    def test_hold_is_not_a_tap(self):
        t = gm.TapDetector()
        t.feed(1, gm.BTN_MODE, 1, 10.0)
        self.assertFalse(t.feed(1, gm.BTN_MODE, 0, 11.5))

    def test_combo_is_not_a_tap(self):
        t = gm.TapDetector()
        t.feed(1, gm.BTN_MODE, 1, 10.0)
        t.feed(1, gm.BTN_B, 1, 10.05)
        self.assertFalse(t.feed(1, gm.BTN_MODE, 0, 10.1))
        self.assertFalse(t.feed(1, gm.BTN_MODE, 0, 10.2))   # stray release without a press
        t.feed(1, gm.BTN_MODE, 1, 12.0)
        self.assertTrue(t.feed(1, gm.BTN_MODE, 0, 12.1))    # and the next clean tap still works


class Recorder:
    def __init__(self, reply=None):
        self.cmds, self.reply = [], reply

    def __call__(self, cmd, wait=False, **kw):
        self.cmds.append(cmd)
        return self.reply if wait else None


class ControlTests(unittest.TestCase):
    def make(self, info, reply=None, alive=lambda: False):
        udp, sigs = Recorder(reply), []
        tmp = tempfile.mkdtemp()
        c = gm.GameControl(info, alive, udp=udp, killpg=lambda p, s: sigs.append((p, s)), kill=lambda p, s: sigs.append((p, s)),
                           pids=lambda n: [99], sleep=lambda s: None, restart_flag=os.path.join(tmp, "run", "restart"), reaper=False)
        return c, udp, sigs

    def test_retroarch_pause_resume_toggles_once(self):
        c, udp, _ = self.make({"kind": "retroarch"}, reply="GET_STATUS PLAYING snes,x,crc32=0")
        c.pause()
        c.resume()
        c.resume()
        self.assertEqual(udp.cmds, ["GET_STATUS", "PAUSE_TOGGLE", "PAUSE_TOGGLE"])

    def test_retroarch_already_paused_stays_paused(self):
        c, udp, _ = self.make({"kind": "retroarch"}, reply="GET_STATUS PAUSED snes,x,crc32=0")
        c.pause()
        c.resume()
        self.assertEqual(udp.cmds, ["GET_STATUS"])

    def test_retroarch_restart_load_save_exit(self):
        c, udp, _ = self.make({"kind": "retroarch"}, reply="GET_STATUS PLAYING a,b")
        c.pause()
        udp.cmds.clear()
        self.assertEqual(c.save(), "State saved")
        c.perform("restart")
        self.assertEqual(udp.cmds, ["SAVE_STATE", "RESET", "PAUSE_TOGGLE"])
        c.pause()
        udp.cmds.clear()
        c.perform("load")
        self.assertEqual(udp.cmds, ["LOAD_STATE", "PAUSE_TOGGLE"])
        c.pause()
        udp.cmds.clear()
        c.perform("exit")
        self.assertEqual(udp.cmds, ["PAUSE_TOGGLE", "QUIT"])

    def test_retroarch_exit_kills_a_hung_retroarch(self):
        c, udp, sigs = self.make({"kind": "retroarch"}, alive=lambda: True)
        c.clock = iter([0.0, 0.0, 10.0, 10.0, 10.0]).__next__
        c.exit()
        self.assertIn((99, signal.SIGKILL), sigs)

    def test_native_pause_uses_stop_and_cont(self):
        c, _, sigs = self.make({"kind": "native", "pid": 4242})
        c.pause()
        c.resume()
        self.assertEqual(sigs, [(4242, signal.SIGSTOP), (4242, signal.SIGCONT)])

    def test_native_restart_writes_flag_and_stops_the_group(self):
        c, _, sigs = self.make({"kind": "native", "pid": 4242})
        c.pause()
        c.perform("restart")
        self.assertTrue(os.path.exists(c.restart_flag))
        self.assertIn((4242, signal.SIGTERM), sigs)
        self.assertLess(sigs.index((4242, signal.SIGCONT)), sigs.index((4242, signal.SIGTERM)))

    def test_native_without_pid_is_harmless(self):
        c, _, sigs = self.make({"kind": "native"})
        c.pause()
        c.perform("exit")
        self.assertEqual(sigs, [])

    def test_kind_guessed_when_flag_is_empty(self):
        c, _, _ = self.make({})
        self.assertEqual(c.kind, "retroarch")            # the stub finds a retroarch pid


class FakeCanvas:
    measure = staticmethod(measure)

    def render(self, ops, w, h):
        return ("layer", len(ops))


class FakeScreen:
    rw, rh, s, canvas = 300, 480, 1.0, FakeCanvas()

    def __init__(self, log):
        self.log, self.dirty = log, False

    def theme(self):
        return dict(gm.DEFAULT_THEME)

    def open(self):
        self.log.append("open")

    def draw(self, layer, x):
        self.log.append(("draw", x))

    def repainted(self):
        return self.dirty

    def rebase(self):
        self.log.append("rebase")
        self.dirty = False

    def close(self):
        self.log.append("close")


class SessionTests(unittest.TestCase):
    def run_session(self, script, kind="retroarch", alive=lambda: True):
        log, now = [], [0.0]
        udp = Recorder("GET_STATUS PLAYING a,b")
        control = gm.GameControl({"kind": kind, "pid": 7}, alive, udp=udp, killpg=lambda p, s: log.append(("sig", s)),
                                 kill=lambda *a: None, pids=lambda n: [], sleep=lambda s: None,
                                 restart_flag=os.path.join(tempfile.mkdtemp(), "restart"), reaper=False)
        queue = list(script)

        def read(dt):
            now[0] += dt
            return [queue.pop(0)] if queue else []

        def sleep(s):
            now[0] += s

        orig = control.perform
        control.perform = lambda a: (log.append(("perform", a)), orig(a))[1]
        sess = gm.MenuSession(FakeScreen(log), control, gm.MenuModel(kind, "Sonic"), read, clock=lambda: now[0], sleep=sleep, alive=alive)
        return sess.run(), log, udp

    def test_open_use_close_order(self):
        result, log, udp = self.run_session(["close"])
        self.assertEqual(result, "resume")
        self.assertEqual(log[0], "open")
        draws = [x for k, x in (e for e in log if isinstance(e, tuple) and e[0] == "draw")]
        self.assertEqual(draws[0], 300)                  # starts fully off screen
        self.assertEqual(draws.count(0) >= 1, True)      # reaches fully in
        self.assertLess(log.index("close"), log.index(("perform", "resume")))   # pixels restored before the game runs
        self.assertEqual(udp.cmds, ["GET_STATUS", "PAUSE_TOGGLE", "PAUSE_TOGGLE"])

    def test_save_keeps_the_menu_open(self):
        result, log, udp = self.run_session(["down", "down", "ok", "back"])
        self.assertEqual(result, "resume")
        self.assertIn("SAVE_STATE", udp.cmds)
        self.assertNotIn("RESET", udp.cmds)

    def test_restart_needs_the_confirm_step(self):
        result, log, udp = self.run_session(["down", "ok", "down", "ok"])
        self.assertEqual(result, "restart")
        self.assertIn("RESET", udp.cmds)

    def test_exit_native(self):
        result, log, _ = self.run_session(["down", "down", "ok", "down", "ok"], kind="native")
        self.assertEqual(result, "exit")
        self.assertIn(("sig", signal.SIGTERM), log)

    def test_game_ending_underneath_closes_without_acting(self):
        state = {"n": 0}

        def alive():
            state["n"] += 1
            return state["n"] < 4
        result, log, udp = self.run_session([], alive=alive)
        self.assertEqual(result, "gone")
        self.assertIn("close", log)

    def test_repaint_is_rebased(self):
        log = []
        sc = FakeScreen(log)
        sc.dirty = True
        control = gm.GameControl({"kind": "native", "pid": 1}, lambda: True, udp=Recorder(), killpg=lambda p, s: None,
                                 pids=lambda n: [], sleep=lambda s: None, reaper=False)
        now = [0.0]

        def read(dt):
            now[0] += 0.2
            return ["close"] if now[0] > 1.0 else []
        gm.MenuSession(sc, control, gm.MenuModel("native"), read, clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s)).run()
        self.assertIn("rebase", log)


class LayoutTests(unittest.TestCase):
    def test_everything_fits_and_all_rows_are_there(self):
        for lw, lh in ((640, 480), (720, 480), (720, 720)):
            s = max(0.6, min(1.6, lw / 720.0))
            w, h = int(gm.PANEL_W * s) + int(gm.SHADOW * s), lh
            for kind in ("retroarch", "native"):
                m = gm.MenuModel(kind, "A very long game title that has to be shortened to fit the panel width")
                ops = gm.layout(m, w, h, s, gm.DEFAULT_THEME, measure, 1.0, 0.0)
                texts = [o[2] for o in ops if o[0] == "text"]
                for _, label in m.items():
                    self.assertIn(label, texts)
                for o in ops:
                    if o[0] == "text":
                        x, y = o[1]
                        self.assertTrue(0 <= x <= w and 0 <= y < h, o)
                        self.assertLessEqual(x + measure(o[2], o[4], o[5]), w + 2, o)
                last_row = max(o[1][1] for o in ops if o[0] == "text" and o[2] in [t for _, t in m.items()])
                self.assertLess(last_row + 24 * s, h - 40 * s)  # the rows stay clear of the footer

    def test_status_and_confirm_text(self):
        m = gm.MenuModel("retroarch", "Sonic")
        m.say("State saved", 9.0)
        ops = gm.layout(m, 318, 480, 1.0, gm.DEFAULT_THEME, measure, 1.0, 1.0)
        self.assertIn("State saved", [o[2] for o in ops if o[0] == "text"])
        m.sel = 4
        m.press("ok")
        ops = gm.layout(m, 318, 480, 1.0, gm.DEFAULT_THEME, measure, 1.0, 100.0)
        texts = [o[2] for o in ops if o[0] == "text"]
        self.assertIn("Exit game?", texts)
        self.assertIn("Yes, exit", texts)
        self.assertNotIn("State saved", texts)

    def test_rows_slide_in_staggered(self):
        m = gm.MenuModel("native")
        early = gm.layout(m, 318, 480, 1.0, gm.DEFAULT_THEME, measure, 0.3, 0.0)
        done = gm.layout(m, 318, 480, 1.0, gm.DEFAULT_THEME, measure, 1.0, 0.0)
        xs = lambda ops, t: [o[1][0] for o in ops if o[0] == "text" and o[2] == t][0]
        self.assertGreater(xs(early, "Exit Game"), xs(done, "Exit Game"))
        self.assertGreaterEqual(xs(early, "Exit Game"), xs(early, "Resume") - 1)

    def test_curves(self):
        self.assertEqual(gm.open_curve(0), 0.0)
        self.assertEqual(gm.open_curve(1), 1.0)
        self.assertEqual(gm.close_curve(0), 1.0)
        self.assertEqual(gm.close_curve(1), 0.0)
        self.assertGreater(gm.open_curve(0.5), 0.5)


class LaunchFlagTests(unittest.TestCase):
    def setUp(self):
        self.l = load_launch()
        self.l.RUN_DIR = os.path.join(tempfile.mkdtemp(), "run")
        self.l.GAME_FLAG = os.path.join(self.l.RUN_DIR, "ingame")

    def test_flag_carries_kind_title_and_pid(self):
        self.l.set_game_flag(True, kind="native", title="Doom")
        self.l.set_game_pid(321)
        info = gm.read_game(self.l.GAME_FLAG)
        self.assertEqual(info, {"kind": "native", "title": "Doom", "pid": 321})
        self.l.set_game_flag(False)
        self.assertIsNone(gm.read_game(self.l.GAME_FLAG))

    def test_plain_flag_still_works(self):
        self.l.set_game_flag(True)
        self.assertTrue(os.path.exists(self.l.GAME_FLAG))
        self.assertEqual(gm.read_game(self.l.GAME_FLAG), {})

    def test_set_game_pid_without_a_flag_does_nothing(self):
        self.l.set_game_pid(5)
        self.assertFalse(os.path.exists(self.l.GAME_FLAG))

    def test_consume_restart_is_one_shot(self):
        self.assertFalse(self.l.consume_restart())
        os.makedirs(self.l.RUN_DIR)
        open(os.path.join(self.l.RUN_DIR, "restart"), "w").close()
        self.assertTrue(self.l.consume_restart())
        self.assertFalse(self.l.consume_restart())

    def test_title(self):
        self.assertEqual(self.l.game_title("/roms/snes/Super Mario World.sfc"), "Super Mario World")
        self.assertEqual(self.l.game_title(""), "")


if __name__ == "__main__":
    unittest.main()


class RetroArchMenuTests(unittest.TestCase):
    def test_toggle_sends_menu_toggle_and_tracks_state(self):
        sent = []
        m = gm.RetroArchMenu(udp=sent.append)
        self.assertTrue(m.toggle())
        self.assertFalse(m.toggle())
        m.toggle(); m.reset()
        self.assertFalse(m.open)
        self.assertEqual(sent, ["MENU_TOGGLE"] * 3)
