import json, os, time

SOI = b"\xff\xd8\xff"
DEFAULT_FPS = 24
MODES = ("on", "silent", "off")


def split_mjpeg(data):
    starts, pos = [], 0
    while True:
        i = data.find(SOI, pos)
        if i < 0:
            break
        starts.append(i)
        pos = i + 3
    return [(s, starts[k + 1] if k + 1 < len(starts) else len(data)) for k, s in enumerate(starts)]


def find_splash(device, roms_root, etc_dir="/etc/rgos/splash"):
    for p in (os.path.join(roms_root, "splash", "splash.mjpg"),
              os.path.join(etc_dir, "splash-%s.mjpg" % device),
              os.path.join(etc_dir, "splash.mjpg")):
        try:
            if os.path.getsize(p) > 0:
                return p
        except OSError:
            pass
    return None


def read_conf(path):
    base = os.path.splitext(path)[0]
    conf = {}
    try:
        with open(base + ".json") as f:
            conf = json.load(f)
    except Exception:
        pass
    if not isinstance(conf, dict):
        conf = {}
    try:
        fps = float(conf.get("fps", DEFAULT_FPS))
        if not 1 <= fps <= 60:
            raise ValueError
    except Exception:
        fps = float(DEFAULT_FPS)
    snd = conf.get("sound")
    snd = os.path.join(os.path.dirname(path), snd) if isinstance(snd, str) and snd else base + ".wav"
    return {"fps": fps, "sound": snd if os.path.isfile(snd) else None}


def mode_of(state):
    m = state.get("splash", "on") if isinstance(state, dict) else "on"
    return m if m in MODES else "on"


def play(data, frames, fps, decode, show, skip, now=time.time, sleep=time.sleep, max_wait=0.02):
    if not frames:
        return 0
    t0, last, shown, bad = now(), -1, 0, 0
    while True:
        if skip():
            break
        i = int((now() - t0) * fps)
        if i >= len(frames):
            break
        if i != last:
            last = i
            s, e = frames[i]
            try:
                show(decode(data[s:e]))
                shown += 1
                bad = 0
            except Exception:
                bad += 1
                if bad >= 5:
                    break
        else:
            sleep(min(max_wait, max(0.0, (t0 + (i + 1) / fps) - now())))
    return shown
