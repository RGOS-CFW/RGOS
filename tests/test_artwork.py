import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests import helpers

menu = helpers.load_menu()
sys.path.insert(0, helpers.RGOS)
import artwork

KEY = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


def game(roms, sid, name):
    p = os.path.join(roms, "roms", sid, name)
    return {"title": menu.pretty(name), "path": p, "sid": sid, "tag": sid.upper(), "core": "retroarch", "size": 1, "card": 1}


def wait(sc, timeout=10):
    end = time.time() + timeout
    while sc.running and time.time() < end:
        time.sleep(0.02)
    assert not sc.running, "scraper did not finish"
    return sc.snapshot()


class NameTests(unittest.TestCase):
    def test_terms_strip_tags_and_fix_articles(self):
        self.assertEqual(artwork.search_terms("Super Mario World (USA) [!]")[0], "Super Mario World")
        t = artwork.search_terms("Legend of Zelda, The - A Link to the Past")
        self.assertEqual(t[0], "The Legend of Zelda - A Link to the Past")
        self.assertIn("The Legend of Zelda", t)
        self.assertLessEqual(len(t), 4)

    def test_terms_subtitle_fallbacks(self):
        t = artwork.search_terms("Sonic - The Hedgehog")
        self.assertEqual(t[0], "Sonic - The Hedgehog")
        self.assertIn("Sonic", t)

    def test_pick_exact_beats_prefix(self):
        hits = [{"id": 1, "name": "Metroid Prime Hunters"}, {"id": 2, "name": "Metroid Prime"}]
        hit, score = artwork.pick_match(hits, "Metroid Prime")
        self.assertEqual(hit["id"], 2)
        self.assertEqual(score, 1.0)

    def test_pick_rejects_weak_match(self):
        hit, _ = artwork.pick_match([{"id": 1, "name": "Completely Different Game"}], "Tetris")
        self.assertIsNone(hit)

    def test_pick_ignores_articles_accents_and_ampersand(self):
        hit, score = artwork.pick_match([{"id": 7, "name": "The Pokémon & Friends"}], "pokemon and friends")
        self.assertEqual(hit["id"], 7)
        self.assertEqual(score, 1.0)


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rgos-art-")
        self.conf = os.path.join(self.tmp, "etc", "steamgriddb.json")
        p = mock.patch.object(artwork, "CONF_FILE", self.conf)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(mock.patch.dict(os.environ).stop)
        os.environ.pop("RGOS_SGDB_KEY", None)

    def test_valid_key(self):
        self.assertTrue(artwork.valid_key(KEY))
        self.assertFalse(artwork.valid_key(""))
        self.assertFalse(artwork.valid_key("short"))
        self.assertFalse(artwork.valid_key("has spaces in it but is long enough"))

    def test_save_then_load(self):
        self.assertEqual(artwork.load_key(self.tmp), "")
        self.assertTrue(artwork.save_key(self.tmp, KEY))
        self.assertEqual(artwork.load_key(self.tmp), KEY)
        self.assertEqual(os.stat(self.conf).st_mode & 0o777, 0o600)

    def test_save_rejects_bad_key(self):
        self.assertFalse(artwork.save_key(self.tmp, "nope"))
        self.assertFalse(os.path.exists(self.conf))

    def test_key_file_on_roms_card(self):
        with open(os.path.join(self.tmp, "steamgriddb-key.txt"), "w") as f:
            f.write(KEY + "\r\nsecond line ignored\n")
        self.assertEqual(artwork.load_key(self.tmp), KEY)

    def test_falls_back_to_roms_card_when_etc_is_read_only(self):
        with mock.patch.object(artwork.os, "makedirs", side_effect=OSError("ro")):
            self.assertTrue(artwork.save_key(self.tmp, KEY))
        self.assertEqual(artwork.load_key(self.tmp), KEY)

    def test_env_wins(self):
        artwork.save_key(self.tmp, KEY)
        os.environ["RGOS_SGDB_KEY"] = "z" * 32
        self.assertEqual(artwork.load_key(self.tmp), "z" * 32)

    def test_hint_never_shows_whole_key(self):
        self.assertNotIn(KEY, artwork.key_hint(KEY))


class IndexTests(unittest.TestCase):
    def test_lookup_is_case_insensitive_and_ignores_junk(self):
        roms = tempfile.mkdtemp(prefix="rgos-art-")
        d = os.path.join(roms, "artwork", "gba")
        os.makedirs(d)
        for n in ("Metroid Fusion.PNG", "Wario Land.jpg", "notes.txt", ".hidden.png", "Zelda.png.part"):
            open(os.path.join(d, n), "wb").write(b"x")
        ix = artwork.ArtIndex(roms)
        self.assertTrue(ix.lookup("gba", "/x/Metroid Fusion.gba").endswith("Metroid Fusion.PNG"))
        self.assertTrue(ix.lookup("gba", "/x/wario land.gba").endswith("Wario Land.jpg"))
        self.assertIsNone(ix.lookup("gba", "/x/Zelda.gba"))
        self.assertIsNone(ix.lookup("gba", "/x/.hidden.gba"))
        self.assertIsNone(ix.lookup("snes", "/x/Metroid Fusion.sfc"))

    def test_sees_new_files_after_invalidate(self):
        roms = tempfile.mkdtemp(prefix="rgos-art-")
        ix = artwork.ArtIndex(roms)
        self.assertIsNone(ix.lookup("gb", "/x/Tetris.gb"))
        os.makedirs(os.path.join(roms, "artwork", "gb"))
        open(os.path.join(roms, "artwork", "gb", "Tetris.png"), "wb").write(b"x")
        ix.invalidate()
        self.assertTrue(ix.lookup("gb", "/x/Tetris.gb"))


class ScrapeTests(unittest.TestCase):
    def setUp(self):
        self.roms = tempfile.mkdtemp(prefix="rgos-art-")
        self.calls = []
        for p in (mock.patch.object(artwork.time, "sleep", lambda s: None),
                  mock.patch.object(artwork, "api_get", self.fake_api),
                  mock.patch.object(artwork, "download", self.fake_dl)):
            p.start()
            self.addCleanup(p.stop)
        self.db = {"Super Mario World": (11, "https://cdn2.steamgriddb.com/grid/a.png", PNG),
                   "Sonic the Hedgehog": (22, "https://cdn2.steamgriddb.com/grid/b.jpg", JPG)}

    def fake_api(self, path, key, timeout=15):
        self.calls.append(path)
        if key == "bad":
            raise artwork.ApiError("auth", "rejected")
        if path.startswith("/search/autocomplete/"):
            term = artwork.urllib.parse.unquote(path.split("/", 3)[3])
            return [{"id": v[0], "name": k} for k, v in self.db.items() if artwork._norm(k) == artwork._norm(term)]
        if path.startswith("/grids/game/"):
            gid = int(path.split("/")[3].split("?")[0])
            for v in self.db.values():
                if v[0] == gid:
                    return [{"url": v[1], "score": 1}, {"url": "https://evil.example/x.png", "score": 99}]
        return []

    def fake_dl(self, url, timeout=25):
        for v in self.db.values():
            if v[1] == url:
                return v[2]
        raise artwork.ApiError("other", "missing")

    def run_scraper(self, games, key=KEY, **kw):
        sc = artwork.Scraper(self.roms, key, shape="portrait")
        sc.start(games, **kw)
        return sc, wait(sc)

    def test_downloads_matches_and_records_misses(self):
        gl = [game(self.roms, "snes", "Super Mario World (USA).sfc"), game(self.roms, "genesis", "Sonic the Hedgehog.md"),
              game(self.roms, "gba", "Obscure Homebrew.gba")]
        sc, s = self.run_scraper(gl)
        self.assertEqual((s["state"], s["found"], s["missed"], s["failed"], s["total"]), ("done", 2, 1, 0, 3))
        png = os.path.join(self.roms, "artwork", "snes", "Super Mario World (USA).png")
        jpg = os.path.join(self.roms, "artwork", "genesis", "Sonic the Hedgehog.jpg")
        self.assertEqual(open(png, "rb").read(), PNG)
        self.assertEqual(open(jpg, "rb").read(), JPG)
        misses = json.load(open(os.path.join(self.roms, "artwork", ".misses.json")))
        self.assertEqual(list(misses), ["gba/Obscure Homebrew"])
        self.assertFalse(any(n.endswith(".part") for _r, _d, fs in os.walk(self.roms) for n in fs))

    def test_rejects_images_from_other_hosts(self):
        gl = [game(self.roms, "snes", "Super Mario World.sfc")]
        self.run_scraper(gl)
        self.assertTrue(any("grids/game/11" in c for c in self.calls))
        self.assertFalse(artwork._cdn_ok("https://evil.example/x.png"))
        self.assertFalse(artwork._cdn_ok("http://cdn2.steamgriddb.com/x.png"))
        self.assertFalse(artwork._cdn_ok("https://steamgriddb.com.evil.example/x.png"))
        self.assertTrue(artwork._cdn_ok("https://cdn2.steamgriddb.com/x.png"))

    def test_second_run_skips_done_and_recent_misses(self):
        gl = [game(self.roms, "snes", "Super Mario World.sfc"), game(self.roms, "gba", "Obscure Homebrew.gba")]
        self.run_scraper(gl)
        self.calls.clear()
        _sc, s = self.run_scraper(gl)
        self.assertEqual(s["total"], 0)
        self.assertEqual(self.calls, [])

    def test_retry_misses_asks_again(self):
        gl = [game(self.roms, "gba", "Obscure Homebrew.gba")]
        self.run_scraper(gl)
        self.calls.clear()
        _sc, s = self.run_scraper(gl, retry_misses=True)
        self.assertEqual(s["total"], 1)
        self.assertTrue(self.calls)

    def test_user_image_is_never_overwritten(self):
        d = os.path.join(self.roms, "artwork", "snes")
        os.makedirs(d)
        mine = os.path.join(d, "Super Mario World.png")
        open(mine, "wb").write(b"mine")
        _sc, s = self.run_scraper([game(self.roms, "snes", "Super Mario World.sfc")])
        self.assertEqual(s["total"], 0)
        self.assertEqual(open(mine, "rb").read(), b"mine")

    def test_bad_key_stops_the_run(self):
        gl = [game(self.roms, "snes", "Super Mario World.sfc"), game(self.roms, "genesis", "Sonic the Hedgehog.md")]
        with mock.patch.object(artwork, "valid_key", lambda k: True):
            sc = artwork.Scraper(self.roms, "bad", shape="portrait")
            sc.start(gl)
            s = wait(sc)
        self.assertEqual(s["state"], "error")
        self.assertIn("key", s["msg"].lower())
        self.assertEqual(s["found"], 0)
        self.assertEqual(len([c for c in self.calls if c.startswith("/search/")]), 1)

    def test_no_key_is_an_error_not_a_crash(self):
        _sc, s = self.run_scraper([game(self.roms, "snes", "A.sfc")], key="")
        self.assertEqual(s["state"], "error")
        self.assertEqual(self.calls, [])

    def test_same_title_on_two_discs_downloads_once(self):
        a = game(self.roms, "snes", "Super Mario World (Disc 1).sfc")
        b = game(self.roms, "snes", "Super Mario World (Disc 2).sfc")
        _sc, s = self.run_scraper([a, b])
        self.assertEqual(s["found"], 2)
        self.assertEqual(sum(1 for c in self.calls if c.startswith("/search/")), 1)

    def test_network_loss_stops_after_three_failures(self):
        def boom(path, key, timeout=15):
            raise artwork.ApiError("net", "No internet connection")
        gl = [game(self.roms, "gba", "G%d.gba" % i) for i in range(6)]
        with mock.patch.object(artwork, "api_get", boom):
            _sc, s = self.run_scraper(gl)
        self.assertEqual(s["state"], "error")
        self.assertIn("internet", s["msg"].lower())
        self.assertEqual(s["found"], 0)
        self.assertEqual(os.path.exists(os.path.join(self.roms, "artwork", ".misses.json")), True)
        self.assertEqual(json.load(open(os.path.join(self.roms, "artwork", ".misses.json"))), {})

    def test_post_hook_can_replace_the_file(self):
        def post(path):
            new = os.path.splitext(path)[0] + ".jpg"
            os.replace(path, new)
            return new
        sc = artwork.Scraper(self.roms, KEY, post=post, shape="portrait")
        sc.start([game(self.roms, "snes", "Super Mario World.sfc")])
        wait(sc)
        self.assertTrue(os.path.exists(os.path.join(self.roms, "artwork", "snes", "Super Mario World.jpg")))
        self.assertFalse(os.path.exists(os.path.join(self.roms, "artwork", "snes", "Super Mario World.png")))

    def test_stop(self):
        gl = [game(self.roms, "gba", "G%d.gba" % i) for i in range(50)]
        sc = artwork.Scraper(self.roms, KEY, shape="portrait")
        orig = self.fake_api
        def slow(path, key, timeout=15):
            sc.stop()
            return orig(path, key, timeout)
        with mock.patch.object(artwork, "api_get", slow):
            sc.start(gl)
            s = wait(sc)
        self.assertEqual(s["state"], "stopped")
        self.assertLess(s["done"], 50)


class MenuWiringTests(unittest.TestCase):
    def test_settings_row_and_icon_exist(self):
        self.assertIn("artwork", menu.SETTINGS_ROWS)
        self.assertIn("artwork", menu.ICONS)

    def test_flow_base_key_includes_art_and_falls_back(self):
        with mock.patch.object(menu, "_flow_gradient_card", return_value="gradient") as g, \
                mock.patch.object(menu, "_flow_art_card", side_effect=[None, "art"]) as a:
            menu._FLOW["cards"].clear()
            k1, lv1 = menu._flow_base(10, "GBA", "SM", 200, None, None)
            k2, lv2 = menu._flow_base(10, "GBA", "SM", 200, None, "/x/broken.png")
            k3, lv3 = menu._flow_base(10, "GBA", "SM", 200, None, "/x/ok.png")
        self.assertEqual(len({k1, k2, k3}), 3)
        self.assertEqual(k1, (10, "GBA", "SM", 200, None))
        self.assertEqual(lv1[0], "gradient")
        self.assertEqual(lv2[0], "gradient")
        self.assertEqual(lv3[0], "art")
        self.assertEqual(a.call_count, 2)
        self.assertEqual(g.call_count, 2)
        menu._FLOW["cards"].clear()


if __name__ == "__main__":
    unittest.main()
