"""Pure logic for dusky-cursor-magic. No gi/evdev imports — testable headless."""
import json, math, os, time


class SpeedEstimator:
    """Sliding-window |dx|+|dy| px/s.
    # ponytail: O(n) list, n = events in ~50 ms (< ~50). Use a deque if
    # window_s ever grows past ~1s."""
    def __init__(self, window_s=0.05):
        self.window_s = window_s
        self._s = []  # (t, px)
        self._last = None

    def add(self, dx, dy, t=None):
        self._s.append((t if t is not None else time.monotonic(), abs(dx) + abs(dy)))

    def feed(self, t, x, y):
        """Absolute pointer pos -> windowed px/s."""
        if self._last:
            self.add(x - self._last[1], y - self._last[2], t)
        self._last = (t, x, y)
        return self.speed(t)

    def speed(self, t=None):
        t = t if t is not None else time.monotonic()
        self._s = [p for p in self._s if t - p[0] <= self.window_s]
        if not self._s:
            return 0.0
        span = max(1e-4, min(self.window_s, t - min(x[0] for x in self._s)))
        return sum(p for _, p in self._s) / span


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


class WiggleDetector:
    """macOS 'find my cursor': N velocity reversals with real speed inside
    window_s. One straight swipe = 0 reversals, so it never fires."""
    def __init__(self, window_s=0.35, min_speed=900.0, need=2):
        self.window_s, self.min_speed, self.need = window_s, min_speed, need
        self._v, self._rev, self._last = [], [], None

    def feed(self, t, x, y):
        fired = False
        if self._last:
            dt = max(t - self._last[0], 1e-4)
            vx, vy = (x - self._last[1]) / dt, (y - self._last[2]) / dt
            if self._v:
                pvx, pvy = self._v[-1][1], self._v[-1][2]
                if (math.hypot(vx, vy) >= self.min_speed
                        and math.hypot(pvx, pvy) >= self.min_speed
                        and vx * pvx + vy * pvy < 0):
                    self._rev.append(t)
            self._v.append((t, vx, vy))
            self._v = [s for s in self._v if t - s[0] <= self.window_s]
            self._rev = [r for r in self._rev if t - r <= self.window_s]
            if len(self._rev) >= self.need:
                fired = True
                self._rev.clear()
        self._last = (t, x, y)
        return fired


class BurstMachine:
    """enter -> hold -> exit -> idle. All motion uses absolute age so phases
    never snap. Publishes alpha/scale/rot for the painter."""
    def __init__(self, hold_s=1.4, enter_s=0.28, exit_s=0.32, cooldown_s=0.8):
        self.hold, self.enter, self.exit, self.cool = hold_s, enter_s, exit_s, cooldown_s
        self.state, self.t0, self.last_end = "idle", 0.0, -9e9
        self.alpha, self.scale, self.rot, self.age = 0.0, 0.82, 0.0, 0.0

    def trigger(self, t):
        if self.state != "idle" or t - self.last_end < self.cool:
            return False
        self.state, self.t0, self.age = "enter", t, 0.0
        return True

    def update(self, t, speed=0.0):
        if self.state == "idle":
            self.alpha, self.scale, self.rot = 0.0, 0.82, 0.0
            return "idle", 0.0
        self.age = t - self.t0
        a = self.age
        if a < self.enter:
            p = a / self.enter
            self.state = "enter"
            self.alpha = ease_out_cubic(p)
            self.scale = 0.82 + 0.18 * ease_out_cubic(p)
        elif a < self.enter + self.hold:
            self.state = "hold"
            self.alpha = 1.0
            h = a - self.enter
            self.scale = 1.0 + 0.02 * math.sin(2 * math.pi * 0.5 * h)     # breathe
            self.rot = math.radians(1.2) * math.sin(2 * math.pi * 0.33 * h)  # sway
        elif a < self.enter + self.hold + self.exit:
            p = (a - self.enter - self.hold) / self.exit
            self.state = "exit"
            self.alpha = 1.0 - ease_out_cubic(p)
            # 0.18 (not plan's 0.08): exit must land on the 0.82 idle baseline
            # or scale pops 0.92->0.82 at exit->idle — test_scale_continuous.
            self.scale = 1.0 - 0.18 * ease_out_cubic(p)
        else:
            self.state, self.last_end = "idle", t
            self.alpha, self.rot = 0.0, 0.0
            self.scale = 0.82
        return self.state, max(0.0, min(1.0, a / (self.enter + self.hold + self.exit)))


# ---- packs ------------------------------------------------------------------

def load_packs(pack_dir):
    """pack_dir/<name>/manifest.json -> {name, emotions: {label: {"type":
    "gif"|"png"|"emoji", "path"|"char"}}}. Each pack dict gets "_dir" added."""
    packs = {}
    if not os.path.isdir(pack_dir):
        return packs
    for name in sorted(os.listdir(pack_dir)):
        d = os.path.join(pack_dir, name)
        mf = os.path.join(d, "manifest.json")
        if os.path.isfile(mf):
            with open(mf) as f:
                m = json.load(f)
            m.setdefault("name", name)
            m["_dir"] = d
            for spec in m.get("emotions", {}).values():
                if "path" in spec:
                    spec["path"] = os.path.join(d, spec["path"])
            packs[m["name"]] = m
    return packs


def decode_frames(path):
    """GIF/PNG -> ([PIL RGBA frames], [durations_s]). GIF holds its own timing."""
    from PIL import Image
    im = Image.open(path)
    frames, durs = [], []
    try:
        while True:
            frames.append(im.convert("RGBA"))
            durs.append(max(0.02, im.info.get("duration", 90) / 1000.0))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return frames, durs


def load_config(path=None):
    """config.default.json merged with an optional user override file."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.default.json")
    with open(base) as f:
        cfg = json.load(f)
    if path and os.path.isfile(path):
        with open(path) as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg
