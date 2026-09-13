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


def _ease_out_sine(u):
    return math.sin(u * math.pi / 2)


class BurstMachine:
    """enter -> hold -> exit -> idle. Absolute age = no phase snaps.
    Profile-driven envelope (research/find-my-cursor.md): grows from
    start_scale to peak_scale (macOS ~2x), breathes, shrinks back smooth.
    update(t, speed) -> (state, alpha, scale, rot, age)."""
    PROFILES = {
        "macos":   {"enter": 1.0, "hold": 1.0, "exit": 1.0, "breathe": 1.0},
        "smooth":  {"enter": 1.35, "hold": 1.0, "exit": 1.25, "breathe": 0.8},
        "snappy":  {"enter": 0.75, "hold": 0.8, "exit": 0.65, "breathe": 1.2},
        "reduced": {"enter": 1.0, "hold": 1.0, "exit": 1.0, "breathe": 0.0},
    }

    def __init__(self, hold_s=1.4, enter_s=0.35, exit_s=0.28, cooldown_s=0.8,
                 peak_scale=1.8, start_scale=0.35, profile="macos",
                 ring=True, breathe_sine=1.0):
        self.hold, self.enter, self.exit, self.cool = hold_s, enter_s, exit_s, cooldown_s
        self.state, self.t0, self.last_end = "idle", 0.0, -9e9
        self.alpha, self.scale, self.rot, self.age = 0.0, 0.0, 0.0, 0.0
        self.ring, self.ring_alpha = 0.0, 0.0
        self._peak, self._start = peak_scale, start_scale
        p = self.PROFILES.get(profile, self.PROFILES["macos"])
        self._reduced = profile == "reduced"
        self._ke, self._kh, self._kx = p["enter"], p["hold"], p["exit"]
        self._breathe = p["breathe"] * (0.0 if self._reduced else breathe_sine)
        self._ring = ring and not self._reduced

    def trigger(self, t):
        if self.state != "idle" or t - self.last_end < self.cool:
            return False
        self.state, self.t0, self.age = "enter", t, 0.0
        return True

    def update(self, t, speed=0.0):
        if self.state == "idle":
            self.alpha = self.scale = self.rot = self.ring_alpha = 0.0
            return ("idle", 0.0, 0.0, 0.0, 0.0)
        a = self.age = t - self.t0
        e_len = self.enter * self._ke
        h_end = e_len + self.hold * self._kh
        x_end = h_end + self.exit * self._kx
        if a < e_len:                       # grow: start -> peak, butter easeInOutSine
            self.state = "enter"
            u = a / e_len
            s = 0.5 - 0.5 * math.cos(u * math.pi)   # smooth in AND out, no initial pop
            self.scale = self._start + (self._peak - self._start) * s
            self.alpha = min(1.0, u * 1.6)  # fade-in trails the growth start
        elif a < h_end:                     # hold at peak, gentle breathe
            self.state = "hold"
            h = a - e_len
            self.scale = self._peak * (1.0 + 0.012 * self._breathe
                                       * math.sin(h * 2 * math.pi / 1.6))
            self.alpha = 1.0
        elif a < x_end:                     # exit: peak -> 0, butter easeInOutSine shrink
            self.state = "exit"
            u = (a - h_end) / (self.exit * self._kx)
            self.scale = self._peak * (0.5 + 0.5 * math.cos(u * math.pi))  # 1->0, zero-velocity both ends
            self.alpha = 1.0 - u * u
        else:
            self.state, self.last_end = "idle", t
            self.alpha = self.scale = self.rot = self.ring_alpha = 0.0
            return (self.state, 0.0, 0.0, 0.0, self.age)
        if self._reduced:                   # reduced motion: alpha only, no move
            self.scale = 1.0
        if self._ring and self.state == "enter":   # KDE-style ring on enter
            u = a / e_len
            self.ring = 0.25 + 0.75 * _ease_out_sine(u)
            self.ring_alpha = (1.0 - u) * 0.6
        else:
            self.ring_alpha = 0.0
        self.rot = 0.014 * math.sin(a * 2 * math.pi / 2.4)   # ~0.8deg sway
        return (self.state, max(0.0, self.alpha), self.scale, self.rot, self.age)


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
