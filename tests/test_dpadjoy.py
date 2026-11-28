import os
import tempfile
import unittest
from unittest import mock

from tests import helpers

hub = helpers.load_hub()
gm = None

A, B, SELECT, MODE = 0x130, 0x131, hub.BTN_SELECT, hub.BTN_MODE
UP, DOWN, LEFT, RIGHT = hub.DPAD_UP, hub.DPAD_DOWN, hub.DPAD_LEFT, hub.DPAD_RIGHT
KEY, ABS, SYN = hub.EV_KEY, hub.EV_ABS, hub.EV_SYN
FULL = hub.ASTICK
DIAG = int(round(FULL * hub.DIAGONAL))


def k(code, value):
    return (KEY, code, value)


class Env(unittest.TestCase):
    """A DpadJoy with its flag files in a temp dir and a clock the test moves."""

    def setUp(self):
        d = tempfile.mkdtemp(prefix="rgos-djoy-")
        self.setting, self.ingame, self.flag = (os.path.join(d, n) for n in ("dpad-joystick", "ingame", "combo"))
        for name, path in (("DPADJOY", self.setting), ("INGAME", self.ingame), ("COMBO_FLAG", self.flag)):
            p = mock.patch.object(hub, name, path)
            p.start()
            self.addCleanup(p.stop)
        self.now, self.buzzes = 100.0, []
        self.dj = hub.DpadJoy(feedback=self.buzzes.append)

    @staticmethod
    def flip(path, on):
        if on:
            open(path, "w").close()
        elif os.path.exists(path):
            os.unlink(path)

    def game(self, on=True):
        """A game starts / ends. Returns the events the hub emits when it notices."""
        self.flip(self.ingame, on)
        return self.step(0.2)

    def setting_on(self, on=True):
        """Settings > DPAD to joystick toggled. Returns the events the hub emits when it notices."""
        self.flip(self.setting, on)
        return self.step(0.2)

    def step(self, dt=0.0):
        """Advance time and return what poll() produced."""
        self.now += dt
        return self.dj.poll(self.now)

    def feed(self, *events, dt=0.0):
        self.now += dt
        return self.dj.filter(list(events), self.now)


class DpadRemapTests(Env):
    def test_off_by_default_the_dpad_passes_through(self):
        self.game()
        self.assertEqual(self.feed(k(UP, 1), k(UP, 0)), [k(UP, 1), k(UP, 0)])

    def test_on_in_a_game_dpad_becomes_the_left_stick(self):
        self.setting_on()
        self.game()
        self.assertEqual(self.feed(k(UP, 1)), [(ABS, hub.ABS_Y, -FULL)])
        self.assertEqual(self.feed(k(UP, 0)), [(ABS, hub.ABS_Y, 0)])
        self.assertEqual(self.feed(k(RIGHT, 1)), [(ABS, hub.ABS_X, FULL)])
        self.assertEqual(self.feed(k(LEFT, 1)), [(ABS, hub.ABS_X, 0)])
        self.assertEqual(self.feed(k(DOWN, 1)), [(ABS, hub.ABS_Y, FULL)])

    def test_diagonal_stays_on_the_unit_circle(self):
        self.setting_on()
        self.game()
        self.feed(k(UP, 1))
        ev = self.feed(k(LEFT, 1))
        self.assertIn((ABS, hub.ABS_X, -DIAG), ev)
        self.assertIn((ABS, hub.ABS_Y, -DIAG), ev)
        self.assertLess(DIAG, FULL)

    def test_other_buttons_are_untouched(self):
        self.setting_on()
        self.game()
        self.assertEqual(self.feed(k(A, 1), k(A, 0), (SYN, 0, 0)), [k(A, 1), k(A, 0), (SYN, 0, 0)])

    def test_not_applied_outside_a_game(self):
        self.setting_on()
        self.assertEqual(self.feed(k(UP, 1)), [k(UP, 1)])
        self.assertEqual(self.step(), [])

    def test_game_start_and_end_swap_a_held_direction(self):
        self.setting_on()
        self.assertEqual(self.feed(k(UP, 1)), [k(UP, 1)])
        self.assertCountEqual(self.game(), [k(UP, 0), (ABS, hub.ABS_Y, -FULL)])
        self.assertCountEqual(self.game(False), [(ABS, hub.ABS_Y, 0), k(UP, 1)])

    def test_turning_the_setting_off_mid_game_hands_a_held_direction_back(self):
        self.setting_on()
        self.game()
        self.feed(k(LEFT, 1))
        self.assertCountEqual(self.setting_on(False), [(ABS, hub.ABS_X, 0), k(LEFT, 1)])
        self.assertEqual(self.feed(k(LEFT, 0)), [k(LEFT, 0)])

    def test_a_real_stick_still_works_and_dpad_wins_while_pushed(self):
        self.setting_on()
        self.game()
        self.assertEqual(self.feed((ABS, hub.ABS_X, 5000)), [(ABS, hub.ABS_X, 5000)])
        self.assertEqual(self.feed(k(LEFT, 1)), [(ABS, hub.ABS_X, -FULL)])
        self.assertEqual(self.feed(k(LEFT, 0)), [(ABS, hub.ABS_X, 5000)])

    def test_stick_values_pass_through_when_off(self):
        self.game()
        self.assertEqual(self.feed((ABS, hub.ABS_Y, -1234)), [(ABS, hub.ABS_Y, -1234)])


class ComboTests(Env):
    def press_both(self):
        out = self.feed(k(MODE, 1))
        out += self.feed(k(SELECT, 1), dt=0.05)
        return out

    def test_menu_then_select_is_swallowed_and_released_quietly(self):
        self.game()
        self.assertEqual(self.feed(k(MODE, 1)), [k(MODE, 1)])
        self.assertEqual(self.feed(k(SELECT, 1), dt=0.05), [])
        self.assertEqual(self.feed(k(SELECT, 0), dt=0.1), [])
        self.assertEqual(self.feed(k(MODE, 0), dt=0.01), [k(MODE, 0)])

    def test_select_then_menu_swallows_menu(self):
        self.game()
        self.assertEqual(self.feed(k(SELECT, 1)), [k(SELECT, 1)])
        self.assertEqual(self.feed(k(MODE, 1), dt=0.05), [])
        self.assertEqual(self.feed(k(MODE, 0), dt=0.1), [])
        self.assertEqual(self.feed(k(SELECT, 0), dt=0.01), [k(SELECT, 0)])

    def test_short_press_turns_it_on_and_buzzes_once(self):
        self.game()
        self.press_both()
        self.feed(k(SELECT, 0), k(MODE, 0), dt=0.2)
        self.assertTrue(os.path.exists(self.setting))
        self.assertEqual(self.buzzes, [hub.BUZZ_ON])
        self.assertEqual(len(hub.BUZZ_ON), 1)

    def test_it_takes_effect_straight_away(self):
        self.game()
        self.press_both()
        self.feed(k(SELECT, 0), k(MODE, 0), dt=0.2)
        self.step(0.2)
        self.assertEqual(self.feed(k(DOWN, 1)), [(ABS, hub.ABS_Y, FULL)])

    def test_holding_turns_it_off_and_buzzes_twice(self):
        self.setting_on()
        self.game()
        self.press_both()
        self.assertEqual(self.step(hub.COMBO_HOLD_S - 0.2), [])
        self.assertTrue(os.path.exists(self.setting))
        self.step(0.3)
        self.assertFalse(os.path.exists(self.setting))
        self.assertEqual(self.buzzes, [hub.BUZZ_OFF])
        self.assertEqual(len(hub.BUZZ_OFF), 3)

    def test_releasing_after_a_hold_does_not_turn_it_back_on(self):
        self.setting_on()
        self.game()
        self.press_both()
        self.step(hub.COMBO_HOLD_S + 0.1)
        self.feed(k(SELECT, 0), k(MODE, 0), dt=0.5)
        self.assertFalse(os.path.exists(self.setting))
        self.assertEqual(self.buzzes, [hub.BUZZ_OFF])

    def test_deadline_wakes_the_loop_for_the_hold(self):
        self.game()
        self.assertEqual(self.dj.next_deadline(self.now), 0.25)
        self.press_both()
        self.assertLess(self.dj.next_deadline(self.now), 0.25 + 1e-9)
        self.step(0.9)
        self.assertLessEqual(self.dj.next_deadline(self.now), 0.11)

    def test_not_a_combo_outside_a_game(self):
        self.assertEqual(self.press_both(), [k(MODE, 1), k(SELECT, 1)])
        self.feed(k(SELECT, 0), k(MODE, 0), dt=0.2)
        self.assertFalse(os.path.exists(self.setting))
        self.assertEqual(self.buzzes, [])

    def test_single_buttons_are_not_a_combo(self):
        self.game()
        self.assertEqual(self.feed(k(SELECT, 1), k(SELECT, 0)), [k(SELECT, 1), k(SELECT, 0)])
        self.assertEqual(self.feed(k(MODE, 1), k(MODE, 0), dt=0.3), [k(MODE, 1), k(MODE, 0)])
        self.assertEqual(self.buzzes, [])

    def test_flag_file_tells_the_game_menu_about_the_combo(self):
        self.game()
        self.assertFalse(os.path.exists(self.flag))
        self.press_both()
        self.assertTrue(os.path.exists(self.flag))

    def test_a_failed_save_does_not_buzz(self):
        self.game()
        blocker = os.path.join(os.path.dirname(self.setting), "a-file")
        open(blocker, "w").close()
        with mock.patch.object(hub, "DPADJOY", os.path.join(blocker, "dpad-joystick")):
            self.press_both()
            self.feed(k(SELECT, 0), k(MODE, 0), dt=0.1)
        self.assertEqual(self.buzzes, [])


class BuzzerTests(unittest.TestCase):
    class Motor:
        def __init__(self):
            self.log = []

        def set(self, on):
            self.log.append(bool(on))

    def setUp(self):
        self.t, self.m = [0.0], self.Motor()
        self.b = hub.Buzzer(self.m, clock=lambda: self.t[0])

    def advance(self, dt):
        self.t[0] += dt
        self.b.tick()

    def test_pattern_plays_without_blocking(self):
        self.b.play([0.12, 0.10, 0.12])
        self.assertEqual(self.m.log, [True])
        self.advance(0.13)
        self.assertEqual(self.m.log, [True, False])
        self.advance(0.11)
        self.assertEqual(self.m.log, [True, False, True])
        self.advance(0.13)
        self.assertEqual(self.m.log, [True, False, True, False])
        self.assertEqual(self.b.next_deadline(), 0.25)

    def test_no_motor_is_fine(self):
        b = hub.Buzzer(None)
        b.play([0.1])
        b.tick()
        b.close()

    def test_close_stops_the_motor(self):
        self.b.play([5.0])
        self.b.close()
        self.assertEqual(self.m.log, [True, False])


class VirtualPadTests(unittest.TestCase):
    def test_left_stick_axes_are_always_declared(self):
        self.assertEqual(hub.LEFT_STICK_AXES, (0x00, 0x01))
        self.assertTrue(set(hub.LEFT_STICK_AXES) <= set(hub.ANALOG_AXES))

    def test_run_declares_them_on_devices_without_sticks(self):
        with open(os.path.join(helpers.RGOS, "rgos-input"), "rb") as f:
            src = f.read().decode()
        self.assertIn("axes=ANALOG_AXES if translator.analog else LEFT_STICK_AXES", src)


class GameMenuTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gamemenu_djoy", os.path.join(helpers.RGOS, "gamemenu.py"))
        self.gm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gm)
        self.path = os.path.join(tempfile.mkdtemp(prefix="rgos-gm-"), "combo")

    def test_recent_combo_flag_suppresses_a_menu_tap(self):
        self.assertFalse(self.gm.combo_recent(self.path, now=1000.0))
        open(self.path, "w").close()
        mt = os.path.getmtime(self.path)
        self.assertTrue(self.gm.combo_recent(self.path, now=mt + 0.5))
        self.assertFalse(self.gm.combo_recent(self.path, now=mt + self.gm.COMBO_QUIET_S + 0.1))

    def test_quiet_window_covers_the_longest_tap(self):
        self.assertGreater(self.gm.COMBO_QUIET_S, self.gm.TAP_MAX_S)

    def test_stick_y_steps_the_menu_once_per_push(self):
        import struct
        pe = self.gm.PadEvents([])
        r, w = os.pipe()
        os.set_blocking(r, False)
        pe.fds.append(r)

        def push(*vals):
            os.write(w, b"".join(struct.pack("llHHi", 0, 0, 3, 1, v) for v in vals))
            return pe.read(0)

        self.assertEqual(push(-30000), ["up"])
        self.assertEqual(push(-32767), [])
        self.assertEqual(push(0), [])
        self.assertEqual(push(30000), ["down"])
        self.assertEqual(push(100, -100), [])
        os.close(w)
        pe.fds.clear()
        os.close(r)


if __name__ == "__main__":
    unittest.main()
