"""rgos-volume: choosing the ALSA card from hw.json."""
import importlib.machinery
import importlib.util
import os
import sys
import unittest
from unittest import mock

from tests import helpers


def load_volume():
    loader = importlib.machinery.SourceFileLoader("rgos_volume", os.path.join(helpers.RGOS, "rgos-volume"))
    spec = importlib.util.spec_from_loader("rgos_volume", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class MixerCardTests(unittest.TestCase):
    def mixer(self, audio_conf):
        vol = load_volume()
        fake_hw = mock.MagicMock(name="hwctl")
        fake_hw.audio_card.return_value = 3
        fake_hw.audio_enable.return_value = []
        with mock.patch.dict(sys.modules, {"hwctl": fake_hw}), \
                mock.patch.object(vol, "read_json", return_value={"audio": audio_conf}), \
                mock.patch.object(vol, "run", return_value=""), \
                mock.patch.object(vol, "log"):
            return vol.Mixer()

    def test_card_zero_is_honoured(self):
        self.assertEqual(self.mixer({"card": 0}).card, 0)
        self.assertEqual(self.mixer({"card": "0"}).card, 0)

    def test_other_card_numbers_are_honoured(self):
        self.assertEqual(self.mixer({"card": 2}).card, 2)

    def test_unset_or_bad_card_is_auto_detected(self):
        for val in (None, "", False, "x", -1):
            self.assertEqual(self.mixer({"card": val}).card, 3, val)
        self.assertEqual(self.mixer({}).card, 3)


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class AnnouncerTests(unittest.TestCase):
    def setUp(self):
        self.vol = load_volume()
        self.clock, self.sent = FakeClock(), []
        self.ann = self.vol.Announcer(self.sent.append, self.clock)

    def advance(self, s):
        self.clock.t += s
        self.ann.poll()

    def test_first_change_shows_at_once(self):
        self.ann.note(75, False)
        self.assertEqual(self.sent, ["VOLUME [###############-----] 75%"])

    def test_held_button_does_not_flood_retroarch(self):
        for pct in range(5, 101, 5):
            self.ann.note(pct, False)
            self.advance(0.04)
        self.assertEqual(len(self.sent), 1)
        self.advance(0.4)
        self.assertEqual(len(self.sent), 2)
        self.assertTrue(self.sent[-1].endswith("100%"))
        self.advance(5)
        self.assertEqual(len(self.sent), 2)

    def test_hold_longer_than_a_message_updates_every_few_seconds(self):
        for i in range(200):
            self.ann.note(i % 100, False)
            self.advance(0.04)
        self.assertTrue(2 <= len(self.sent) <= 4, self.sent)

    def test_press_after_the_message_expired_shows_at_once(self):
        self.ann.note(50, False)
        self.advance(4)
        self.ann.note(55, False)
        self.assertEqual(len(self.sent), 2)

    def test_mute_and_limits(self):
        self.ann.note(0, True)
        self.assertEqual(self.sent[-1], "VOLUME [MUTED]")
        self.assertEqual(self.vol.bar_text(100, False), "VOLUME [" + "#" * 20 + "] 100%")
        self.assertEqual(self.vol.bar_text(0, False), "VOLUME [" + "-" * 20 + "] 0%")

    def test_a_failing_send_is_survived(self):
        def boom(_):
            raise OSError("no socket")
        ann = self.vol.Announcer(boom, self.clock)
        ann.note(40, False)


if __name__ == "__main__":
    unittest.main()
