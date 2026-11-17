import importlib.machinery, json, os, tempfile, types, unittest

HUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rgos", "rgos-input")


def load_hub():
    mod = types.ModuleType("rgos_input_hide")
    mod.__file__ = HUB
    importlib.machinery.SourceFileLoader("rgos_input_hide", HUB).exec_module(mod)
    return mod


class HideRawNode(unittest.TestCase):
    def setUp(self):
        self.hub = load_hub()
        self.tmp = tempfile.mkdtemp()
        self.hub.HIDDEN = os.path.join(self.tmp, "hidden.json")
        self.hub.log = lambda *a: None
        self.sysfs = os.path.join(self.tmp, "sys")
        os.makedirs(os.path.join(self.sysfs, "event3"))
        with open(os.path.join(self.sysfs, "event3", "dev"), "w") as f:
            f.write("13:67\n")
        self.node = os.path.join(self.tmp, "event3")
        open(self.node, "w").close()

    def test_hidden_node_is_removed_and_recorded(self):
        self.hub.hide_raw_node(self.node, self.sysfs)
        self.assertFalse(os.path.exists(self.node))
        with open(self.hub.HIDDEN) as f:
            self.assertEqual(json.load(f), [[self.node, 13, 67]])

    def test_failed_hide_leaves_node_alone(self):
        os.unlink(os.path.join(self.sysfs, "event3", "dev"))
        self.hub.hide_raw_node(self.node, self.sysfs)
        self.assertTrue(os.path.exists(self.node))
        self.assertFalse(os.path.exists(self.hub.HIDDEN))

    def test_restore_after_a_killed_hub(self):
        with open(self.hub.HIDDEN, "w") as f:
            json.dump([[self.node + "x", 13, 67]], f)
        self.hub.HIDDEN_NODES.clear()
        try:
            self.hub.restore_hidden()
        except PermissionError:
            self.skipTest("mknod needs root")
        if os.path.exists(self.node + "x"):
            self.assertFalse(os.path.exists(self.hub.HIDDEN))


if __name__ == "__main__":
    unittest.main()
