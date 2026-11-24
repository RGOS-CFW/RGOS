#!/usr/bin/env python3
"""ROM artwork scraping from SteamGridDB for RG OS.

Standard library only. The launcher (menu.py) owns the UI; this module owns
everything else: finding the API key, matching ROM names to SteamGridDB games,
downloading a cover, and remembering what was already tried.

Layout on the ROMS card (visible and editable from a PC):

    artwork/<system>/<rom file name without extension>.png|jpg
    artwork/<system>/<rom file name without extension>.json   metadata (release date, description, ...)
    artwork/.misses.json        games SteamGridDB had no match for (retried after 30 days)
    artwork/overrides.json      optional {"<system>/<rom stem>": <SteamGridDB game id>}

Any image dropped into artwork/<system>/ with the right name is used as-is, so
hand-picked covers always work, with or without a key.

The API key is read from (first hit wins): $RGOS_SGDB_KEY, /etc/rgos/steamgriddb.json
({"api_key": "...", "shape": "portrait|square|any"}), or rgos-data/steamgriddb-key.txt on the ROMS card
(a steamgriddb-key.txt in the ROMS root from older versions is still read).
"""
import difflib
import http.client
import json
import os
import re
import shutil
import socket
import ssl
import struct
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.steamgriddb.com/api/v2"
USER_AGENT = "RGOS-artwork/1.0"
CONF_FILE = os.environ.get("RGOS_SGDB_CONF", "/etc/rgos/steamgriddb.json")
KEY_FILE_NAME = "steamgriddb-key.txt"
DATA_DIR_NAME = "rgos-data"
ART_EXTS = (".png", ".jpg", ".jpeg")
MISS_RETRY_S = 30 * 86400
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MIN_MATCH = 0.72
WIKI_API = "https://en.wikipedia.org"
META_VERSION = 1
MAX_DESC_CHARS = 600
SHAPES = {
    "portrait": "600x900,342x482,660x930",
    "square": "512x512,1024x1024",
    "any": "",
}
KEY_RE = re.compile(r"[A-Za-z0-9]{16,64}")
LOG_FILE = os.environ.get("RGOS_ART_LOG", "/var/log/rgos-artwork.log")
RESOLV_FILES = ("/etc/resolv.conf", os.environ.get("RGOS_RESOLV", "/run/rgos/resolv.conf"))
FALLBACK_DNS = ("1.1.1.1", "9.9.9.9", "8.8.8.8")


def _log(msg):
    """Append to the artwork log (collected into rgos-logs.txt). Never raises."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("%s artwork: %s\n" % (time.strftime("%H:%M:%S"), msg))
    except OSError:
        pass


# --------------------------------------------------------------------- key / config

def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:  # -sig: hand-edited files may start with a BOM
            d = json.load(f)
        return d if isinstance(d, type(default)) else default
    except (OSError, ValueError):
        return default


def valid_key(key):
    return bool(key) and KEY_RE.fullmatch(key.strip()) is not None


def load_conf():
    return _read_json(CONF_FILE, {})


def key_file_path(roms_root):
    """Where the key file lives: <ROMS>/rgos-data/steamgriddb-key.txt."""
    return os.path.join(roms_root, DATA_DIR_NAME, KEY_FILE_NAME)


def _read_key_file(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:  # -sig: Windows Notepad saves a BOM
            return f.readline().strip()
    except OSError:
        return ""


def load_key(roms_root):
    key = os.environ.get("RGOS_SGDB_KEY", "").strip()
    if valid_key(key):
        return key
    key = str(load_conf().get("api_key", "")).strip()
    if valid_key(key):
        return key
    # New location first, then the legacy ROMS-root file so existing setups keep working.
    for path in (key_file_path(roms_root), os.path.join(roms_root, KEY_FILE_NAME)):
        key = _read_key_file(path)
        if valid_key(key):
            return key
    return ""


def save_key(roms_root, key):
    """Store the key. Returns True when it was saved somewhere load_key() will find it."""
    key = key.strip()
    if not valid_key(key):
        return False
    conf = load_conf()
    conf["api_key"] = key
    try:
        os.makedirs(os.path.dirname(CONF_FILE), exist_ok=True)
        tmp = CONF_FILE + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(conf, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CONF_FILE)
        return True
    except OSError:
        pass
    try:
        os.makedirs(os.path.join(roms_root, DATA_DIR_NAME), exist_ok=True)
        with open(key_file_path(roms_root), "w", encoding="utf-8") as f:
            f.write(key + "\n")
        return True
    except OSError:
        return False


def key_hint(key):
    if not key:
        return ""
    return key[:4] + "..." + key[-4:] if len(key) > 10 else "*" * len(key)


def shape_pref():
    s = str(load_conf().get("shape", "portrait")).lower()
    return s if s in SHAPES else "portrait"


# --------------------------------------------------------------------- local art index

def art_dir(roms_root):
    return os.path.join(roms_root, "artwork")


def stem_of(path):
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    # a PICO-8 "game.p8.png" cart is called "game" (its artwork is game.png, not game.p8.png)
    return stem[:-3] if stem.lower().endswith(".p8") and name.lower().endswith(".png") else stem


class ArtIndex:
    """Which ROMs already have artwork. One directory listing per system, re-read
    when the folder changes, so asking about thousands of games stays cheap."""

    RECHECK_S = 2.0

    def __init__(self, roms_root):
        self.root = art_dir(roms_root)
        self._dirs = {}

    def invalidate(self):
        self._dirs = {}

    def _listing(self, sid):
        now = time.monotonic()
        ent = self._dirs.get(sid)
        folder = os.path.join(self.root, sid)
        if ent is not None and now - ent[0] < self.RECHECK_S:
            return ent[2]
        try:
            mt = os.stat(folder).st_mtime
        except OSError:
            self._dirs[sid] = (now, 0, {})
            return {}
        if ent is not None and ent[1] == mt:
            self._dirs[sid] = (now, mt, ent[2])
            return ent[2]
        found = {}
        try:
            names = os.listdir(folder)
        except OSError:
            names = []
        for n in names:
            stem, ext = os.path.splitext(n)
            if ext.lower() in ART_EXTS and not n.startswith("."):
                found.setdefault(stem.lower(), os.path.join(folder, n))
        self._dirs[sid] = (now, mt, found)
        return found

    def lookup(self, sid, rom_path):
        return self._listing(sid).get(stem_of(rom_path).lower())

    def count(self, games):
        return sum(1 for g in games if self.lookup(g["sid"], g["path"]))


# --------------------------------------------------------------------- name matching

def _norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"^(the|a|an) ", "", s)
    return s


def search_terms(title):
    """Candidate search strings for a ROM title, most likely first (at most 4)."""
    t = re.sub(r"\s*[\(\[].*?[\)\]]", "", title).replace("_", " ").strip()
    t = re.sub(r"\s+", " ", t)
    bases = [t]
    m = re.match(r"^(.*?),\s*(The|A|An)(\s+-\s+.*|\s*:.*)?$", t)
    if m:  # "Legend of Zelda, The - A Link to the Past" -> "The Legend of Zelda - A Link to the Past"
        bases.insert(0, ("%s %s%s" % (m.group(2), m.group(1), m.group(3) or "")).strip())
    terms = []
    for b in bases:
        terms.append(b)
        if " - " in b:
            head, tail = b.split(" - ", 1)
            terms += ["%s: %s" % (head, tail), head]
        elif ":" in b:
            terms.append(b.split(":", 1)[0])
    out, seen = [], set()
    for x in terms:
        x = x.strip()
        if len(_norm(x)) >= 2 and _norm(x) not in seen:
            seen.add(_norm(x))
            out.append(x)
    return out[:4]


_ROMAN_RE = re.compile(r"(ii|iii|iv|vi|vii|viii|ix|xi|xii)")


def _numbers(norm):
    """Sequel markers in a normalised title: tokens with a digit (2, x3) and roman numerals (ii, vii)."""
    return {t for t in norm.split() if any(c.isdigit() for c in t) or _ROMAN_RE.fullmatch(t)}


def pick_match(results, term):
    """Best SteamGridDB search hit for term as (hit, score), or (None, 0.0).

    A hit whose sequel number differs from the title's is never a match: the text similarity alone
    scores "Sonic the Hedgehog" 0.95 against "Sonic the Hedgehog 2" and picked the wrong game's cover.
    """
    want = _norm(term)
    want_nums = _numbers(want)
    best, best_s = None, 0.0
    for r in results or []:
        name = _norm(str(r.get("name", "")))
        if not name:
            continue
        if name != want and _numbers(name) != want_nums:
            continue
        s = 1.0 if name == want else difflib.SequenceMatcher(None, want, name).ratio()
        if s > best_s + 1e-9:
            best, best_s = r, s
    return (best, best_s) if best is not None and best_s >= MIN_MATCH else (None, 0.0)


# --------------------------------------------------------------------- HTTP

class ApiError(Exception):
    """kind: auth | tls | net | rate | server | other"""

    def __init__(self, kind, msg, retry_after=0):
        Exception.__init__(self, msg)
        self.kind, self.retry_after = kind, retry_after


_SSL = [None]


def _ctx():
    if _SSL[0] is None:
        _SSL[0] = ssl.create_default_context()
    return _SSL[0]


# The root filesystem is read-only, and /etc/resolv.conf is only a symlink to the file the Wi-Fi
# DHCP script writes. When that link is missing (or the lease carried no DNS), the C resolver has no
# nameserver and every lookup fails, so artwork asks DNS itself as a fallback.

def nameservers():
    out = []
    for path in RESOLV_FILES:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "nameserver":
                        out.append(parts[1])
        except OSError:
            pass
    out += FALLBACK_DNS
    res, seen = [], set()
    for ns in out:
        try:
            socket.inet_aton(ns)
        except OSError:
            continue  # IPv6 / junk: the fallback speaks IPv4 only
        if ns.startswith("127.") or ns in seen:
            continue
        seen.add(ns)
        res.append(ns)
    return res


def _skip_name(data, pos):
    while pos < len(data):
        n = data[pos]
        if n == 0:
            return pos + 1
        if n & 0xC0 == 0xC0:
            return pos + 2
        pos += n + 1
    return pos


def parse_dns_a(data, qid):
    """IPv4 addresses in a DNS response packet (empty when it is not an answer to qid)."""
    if len(data) < 12 or data[:2] != qid or data[3] & 0x0F != 0:
        return []
    qd, an = struct.unpack(">HH", data[4:8])
    pos = 12
    for _ in range(qd):
        pos = _skip_name(data, pos) + 4
    ips = []
    for _ in range(an):
        pos = _skip_name(data, pos)
        if pos + 10 > len(data):
            break
        typ, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[pos:pos + 10])
        pos += 10
        if typ == 1 and rdlen == 4 and pos + 4 <= len(data):
            ips.append(".".join(str(b) for b in data[pos:pos + 4]))
        pos += rdlen
    return ips


def _dns_query(host, server, timeout):
    qid = os.urandom(2)
    q = qid + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    for label in host.rstrip(".").split("."):
        b = label.encode("idna")
        q += bytes([len(b)]) + b
    q += b"\x00\x00\x01\x00\x01"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        sock.sendto(q, (server, 53))
        return parse_dns_a(sock.recv(1500), qid)
    finally:
        sock.close()


def dns_lookup(host, timeout=3):
    for server in nameservers():
        try:
            ips = _dns_query(host, server, timeout)
        except (OSError, UnicodeError):
            continue
        if ips:
            return ips
    return []


class _Conn(http.client.HTTPSConnection):
    def connect(self):
        try:
            return http.client.HTTPSConnection.connect(self)
        except socket.gaierror as e:
            _log("system DNS failed for %s (%s); asking %s directly" % (self.host, e, ", ".join(nameservers()[:3])))
            ips = dns_lookup(self.host)
            if not ips:
                raise
            last = None
            for ip in ips:
                try:
                    sock = socket.create_connection((ip, self.port), self.timeout)
                    break
                except OSError as err:
                    last = err
            else:
                raise last
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _Handler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_Conn, req, context=self._context)


def _open(url, key, limit, timeout):
    headers = {"User-Agent": USER_AGENT}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_Handler(context=_ctx()))
    try:
        with opener.open(req, timeout=timeout) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        _log("HTTP %d for %s" % (e.code, urllib.parse.urlparse(url).path[:60]))
        if e.code in (401, 403):
            raise ApiError("auth", "The API key was rejected")
        if e.code == 404:
            return None
        if e.code == 429:
            try:
                ra = int(e.headers.get("Retry-After", "5"))
            except (TypeError, ValueError):
                ra = 5
            raise ApiError("rate", "Rate limited", ra)
        raise ApiError("server" if e.code >= 500 else "other", "HTTP %d" % e.code)
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)
        _log("request failed: %r" % (reason or e))
        if isinstance(reason, ssl.SSLError):
            raise ApiError("tls", "Secure connection failed (is the clock set correctly?)")
        if isinstance(reason, socket.gaierror):
            raise ApiError("net", "No internet connection (DNS lookup failed)")
        raise ApiError("net", "No internet connection")
    except ssl.SSLError as e:
        _log("TLS failed: %r" % (e,))
        raise ApiError("tls", "Secure connection failed (is the clock set correctly?)")
    except (socket.timeout, TimeoutError, OSError) as e:
        _log("request failed: %r" % (e,))
        raise ApiError("net", "No internet connection")
    if len(data) > limit:
        raise ApiError("other", "Response too large")
    return data


def api_get(path, key, timeout=15):
    data = _open(API + path, key, MAX_JSON_BYTES, timeout)
    if data is None:
        return None
    try:
        d = json.loads(data.decode("utf-8", "replace"))
    except ValueError:
        raise ApiError("server", "Bad response from SteamGridDB")
    if isinstance(d, dict) and d.get("success") is False:
        errs = d.get("errors") or []
        msg = str(errs[0]) if errs else "SteamGridDB error"
        if "authorization" in msg.lower() or "token" in msg.lower():
            raise ApiError("auth", "The API key was rejected")
        return None
    return d.get("data") if isinstance(d, dict) else None


def _cdn_ok(url):
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    return p.scheme == "https" and (host == "steamgriddb.com" or host.endswith(".steamgriddb.com"))


def download(url, timeout=25):
    """Fetch an image from the SteamGridDB CDN. The API key is never sent to it."""
    if not _cdn_ok(url):
        raise ApiError("other", "Unexpected image host")
    data = _open(url, "", MAX_IMAGE_BYTES, timeout)
    if data is None:
        raise ApiError("other", "Image not found")
    return data


def image_ext(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    return ""


# --------------------------------------------------------------------- lookups

def _override_id(v):
    """A SteamGridDB game id from a hand-edited overrides.json value, or None if it is not one."""
    if isinstance(v, bool):
        return None
    try:
        n = int(float(str(v).strip()))
    except (TypeError, ValueError, OverflowError):
        return None
    return n if n > 0 else None


def find_game(key, title, override_id=None):
    """SteamGridDB game id for a ROM title, or None."""
    if override_id:
        oid = _override_id(override_id)
        if oid:
            return oid
        _log("ignoring bad overrides.json value for %r: %r" % (title, override_id))
    for term in search_terms(title):
        hits = api_get("/search/autocomplete/" + urllib.parse.quote(term, safe=""), key)
        hit, _score = pick_match(hits, term)
        if hit is not None and str(hit.get("id", "")).isdigit():
            return int(hit["id"])
        time.sleep(0.1)
    return None


def best_grid_info(key, game_id, shape):
    """The best-scored still image for game_id as SteamGridDB's dict (url, author, style, ...), or None."""
    base = "/grids/game/%d?types=static&mimes=image/png,image/jpeg&nsfw=false&humor=false&epilepsy=false" % game_id
    dims = SHAPES.get(shape, "")
    tries = [base + "&dimensions=" + dims] if dims else []
    tries.append(base)
    for path in tries:
        grids = api_get(path, key)
        grids = [g for g in (grids or []) if isinstance(g, dict) and _cdn_ok(str(g.get("url", "")))]
        if grids:
            grids.sort(key=lambda g: (g.get("score") or 0), reverse=True)
            return grids[0]
        time.sleep(0.1)
    return None


def best_grid(key, game_id, shape):
    """URL of the best-scored still image for game_id, or None."""
    g = best_grid_info(key, game_id, shape)
    return str(g["url"]) if g else None


def game_info(key, game_id):
    """SteamGridDB's own record for a game: name, release year, verified flag."""
    d = api_get("/games/id/%d" % game_id, key)
    if not isinstance(d, dict):
        return {}
    out = {"sgdb_id": game_id, "name": str(d.get("name") or "")}
    rd = d.get("release_date")
    try:
        out["release_date"] = time.strftime("%Y-%m-%d", time.gmtime(int(rd)))
        out["year"] = int(out["release_date"][:4])
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    if d.get("verified") is not None:
        out["verified"] = bool(d.get("verified"))
    return out


def grid_info(g):
    """The per-image fields worth keeping from a SteamGridDB grid."""
    if not g:
        return {}
    out = {}
    for k in ("style", "language", "width", "height", "score"):
        if g.get(k) is not None:
            out[k] = g[k]
    author = g.get("author")
    if isinstance(author, dict) and author.get("name"):
        out["author"] = str(author["name"])
    return out


# ---- descriptions (SteamGridDB has none, so Wikipedia's page summaries fill that gap)

def _wiki_json(path):
    data = _open(WIKI_API + path, "", MAX_JSON_BYTES, 15)
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8", "replace"))
    except ValueError:
        raise ApiError("server", "Bad response from Wikipedia")


def _clip(text, limit=MAX_DESC_CHARS):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:end + 1] if end > 120 else cut.rstrip() + "..."


def _is_game_page(d):
    blob = ("%s %s" % (d.get("description") or "", (d.get("extract") or "")[:240])).lower()
    return d.get("type") == "standard" and ("video game" in blob or "videogame" in blob or "arcade game" in blob)


def find_description(title, canonical=""):
    """(description, wikipedia_url) for a game, or ("", "") when no confident match.

    Only pages that identify themselves as a video game are accepted, so "Contra" the
    Roman-law page or "Tetris" the pop song never leak in."""
    names = []
    for n in [canonical] + search_terms(title):
        if n and n not in names:
            names.append(n)
    seen = set()
    for name in names[:3]:
        q = urllib.parse.quote(name + " video game", safe="")
        res = _wiki_json("/w/rest.php/v1/search/title?q=%s&limit=3" % q)
        for page in ((res or {}).get("pages") or [])[:3]:
            pkey = str(page.get("key") or "")
            if not pkey or pkey in seen:
                continue
            seen.add(pkey)
            if _norm(str(page.get("title", ""))).split(" ")[0] != _norm(name).split(" ")[0]:
                continue  # first word must agree: cheap guard against unrelated pages
            d = _wiki_json("/api/rest_v1/page/summary/" + urllib.parse.quote(pkey, safe=""))
            if isinstance(d, dict) and _is_game_page(d) and d.get("extract"):
                url = ((d.get("content_urls") or {}).get("desktop") or {}).get("page", "")
                return _clip(str(d["extract"])), url
        time.sleep(0.1)
    return "", ""


def meta_path(roms_root, sid, rom_path):
    return os.path.join(art_dir(roms_root), sid, stem_of(rom_path) + ".json")


def load_meta(roms_root, sid, rom_path):
    """Saved metadata for a ROM ({} when there is none). Cheap enough to call per frame's selection."""
    d = _read_json(meta_path(roms_root, sid, rom_path), {})
    return d if d.get("v") == META_VERSION else {}


def has_meta(roms_root, sid, rom_path):
    return os.path.exists(meta_path(roms_root, sid, rom_path))


def format_meta_lines(meta):
    """Short display strings for a game card: ["1991", "Verified"], etc."""
    out = []
    if meta.get("release_date"):
        out.append(str(meta["release_date"]))
    elif meta.get("year"):
        out.append(str(meta["year"]))
    return out


def _write_atomic(path, data):
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# --------------------------------------------------------------------- background scraper

class Scraper:
    """Downloads artwork for a list of games on a background thread."""

    def __init__(self, roms_root, key, index=None, post=None, shape=None):
        self.root, self.key, self.post = roms_root, key, post
        self.index = index or ArtIndex(roms_root)
        self.shape = shape or shape_pref()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._s = self._fresh("idle")
        self._misses = None

    @staticmethod
    def _fresh(state):
        return {"state": state, "total": 0, "done": 0, "found": 0, "missed": 0, "failed": 0,
                "current": "", "msg": "", "version": 0}

    # -- public
    def snapshot(self):
        with self._lock:
            return dict(self._s)

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, games, retry_misses=False):
        if self.running:
            return False
        self._stop.clear()
        with self._lock:
            ver = self._s["version"]
            self._s = self._fresh("running")
            self._s["version"] = ver
        self._thread = threading.Thread(target=self._run, args=(list(games), retry_misses), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()

    def clear_misses(self):
        self._misses = {}
        self._save_misses()

    # -- internals
    def _set(self, **kw):
        with self._lock:
            self._s.update(kw)

    def _bump(self, **kw):
        with self._lock:
            for k, v in kw.items():
                self._s[k] += v

    def _miss_file(self):
        return os.path.join(art_dir(self.root), ".misses.json")

    def _load_misses(self):
        if self._misses is None:
            self._misses = _read_json(self._miss_file(), {})
        return self._misses

    def _save_misses(self):
        try:
            os.makedirs(art_dir(self.root), exist_ok=True)
            _write_atomic(self._miss_file(), json.dumps(self._misses or {}).encode("utf-8"))
        except OSError:
            pass

    def _overrides(self):
        return _read_json(os.path.join(art_dir(self.root), "overrides.json"), {})

    def _finish(self, state, msg=""):
        _log("scrape %s: %s" % (state, msg))
        self._save_misses()
        self._set(state=state, msg=msg, current="")

    def _run(self, games, retry_misses):
        try:
            self._work(games, retry_misses)
        except Exception as e:  # never let the thread die silently
            self._finish("error", "Unexpected error: %s" % e)

    def _work(self, games, retry_misses):
        if not valid_key(self.key):
            return self._finish("error", "No API key set")
        try:
            os.makedirs(art_dir(self.root), exist_ok=True)
            probe = os.path.join(art_dir(self.root), ".w")
            open(probe, "w").close()
            os.remove(probe)
        except OSError:
            return self._finish("error", "Cannot write to the ROMS card")
        misses, overrides, now = self._load_misses(), self._overrides(), time.time()
        if retry_misses:
            misses.clear()
        self.index.invalidate()
        todo = []
        for g in games:
            if self.index.lookup(g["sid"], g["path"]) and has_meta(self.root, g["sid"], g["path"]):
                continue
            mk = "%s/%s" % (g["sid"], stem_of(g["path"]))
            if now - float(misses.get(mk, 0)) < MISS_RETRY_S:
                continue
            todo.append((g, mk))
        self._set(total=len(todo))
        if not todo:
            return self._finish("done", "Every game already has artwork and details, or was checked recently")
        by_title = {}
        net_fail = 0
        for g, mk in todo:
            if self._stop.is_set():
                return self._finish("stopped", "Stopped")
            self._set(current=g["title"])
            try:
                res = self._one(g, mk, overrides, by_title)
                net_fail = 0
            except ApiError as e:
                if e.kind == "auth":
                    return self._finish("error", "The API key was rejected. Check it in Settings > Game artwork")
                if e.kind == "tls":
                    return self._finish("error", str(e))
                if e.kind == "net":
                    net_fail += 1
                    if net_fail >= 3:
                        return self._finish("error", "%s. Check Wi-Fi in Settings > Wi-Fi" % e)
                _log("%s: %s (%s)" % (g["title"], e, e.kind))
                self._bump(failed=1, done=1)
                continue
            except OSError:
                return self._finish("error", "Cannot write to the ROMS card")
            if res is None:
                misses[mk] = now
                self._bump(missed=1)
            else:
                self._bump(found=1, version=1)
            self._bump(done=1)
            if self.snapshot()["done"] % 10 == 0:
                self._save_misses()
            time.sleep(0.15)
        s = self.snapshot()
        self._finish("done", "Found %d, no match for %d%s" % (s["found"], s["missed"], (", %d failed (try again)" % s["failed"]) if s["failed"] else ""))

    def _save_meta(self, g, meta):
        meta = dict(meta, v=META_VERSION, title=g["title"])
        _write_atomic(meta_path(self.root, g["sid"], g["path"]), json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))

    def _one(self, g, mk, overrides, by_title):
        """Fetch the cover (when missing) and the metadata (when missing) for one game.
        Returns the cover path, or None when SteamGridDB has no match and there is no cover."""
        stem = stem_of(g["path"])
        dest_dir = os.path.join(art_dir(self.root), g["sid"])
        os.makedirs(dest_dir, exist_ok=True)
        tkey = _norm(g["title"])
        ov = overrides.get(mk) or overrides.get(stem)
        existing = self.index.lookup(g["sid"], g["path"])
        need_meta = not has_meta(self.root, g["sid"], g["path"])
        cached = by_title.get(tkey) if not ov else None
        if cached and (cached[0] is None or os.path.exists(cached[0])):
            img, meta = cached
            dest = existing
            if dest is None and img:
                dest = os.path.join(dest_dir, stem + os.path.splitext(img)[1])
                shutil.copyfile(img, dest)
            if need_meta and meta:
                self._save_meta(g, meta)
            return dest
        game_id = self._retry(lambda: find_game(self.key, g["title"], ov))
        if game_id is None:
            if existing and need_meta:
                self._save_meta(g, {})  # user-supplied cover, nothing to look up: don't retry every run
            return existing
        dest, grid = existing, None
        if dest is None:
            grid = self._retry(lambda: best_grid_info(self.key, game_id, self.shape))
            if grid is None and not need_meta:
                return None
            if grid is not None:
                data = self._retry(lambda: download(str(grid["url"])))
                ext = image_ext(data)
                if not ext:
                    return None
                dest = os.path.join(dest_dir, stem + ext)
                _write_atomic(dest, data)
                if self.post is not None:
                    try:
                        dest = self.post(dest) or dest
                    except Exception:
                        pass
        meta = {}
        if need_meta or cached is None:
            meta = self._retry(lambda: game_info(self.key, game_id)) or {"sgdb_id": game_id}
            meta.update(grid_info(grid))
            try:
                desc, url = self._retry(lambda: find_description(g["title"], meta.get("name", "")))
            except ApiError as e:
                if e.kind in ("auth", "tls"):
                    raise
                _log("%s: description lookup failed (%s)" % (g["title"], e))
                desc, url = None, ""  # leave the metadata unsaved so the next run retries
            if desc is not None:
                if desc:
                    meta["description"], meta["description_source"] = desc, url or "Wikipedia"
                if need_meta:
                    self._save_meta(g, meta)
        by_title[tkey] = (dest, meta)
        return dest

    def _retry(self, fn):
        for attempt in range(3):
            try:
                return fn()
            except ApiError as e:
                if e.kind == "rate" and attempt < 2:
                    time.sleep(min(30, max(1, e.retry_after)))
                elif e.kind in ("net", "server") and attempt < 2:
                    time.sleep(1 + 2 * attempt)
                else:
                    raise
            if self._stop.is_set():
                raise ApiError("other", "stopped")
