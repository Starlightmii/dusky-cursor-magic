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


def elastic_burst(p):
    """0->1 progress -> scale factor with true >1 overshoot (easeOutElastic).
    Peak ~1.35 near p=0.15: fast pop-in, wobbly settle (macOS feel)."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    c4 = (2 * math.pi) / 3
    return 2 ** (-10 * p) * math.sin((p * 10 - 0.75) * c4) + 1


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


class BurstMachine:
    """idle -> burst (threshold) -> shrink -> idle. One burst at a time.
    Publishes envelope (0..1 shape), scale (px multiplier incl. peak_scale),
    wobble (radians-ish phase for spring rotation)."""
    def __init__(self, threshold=3000.0, hold_s=0.9, shrink_s=0.35, cooldown_s=1.2,
                 peak_scale=3.4):
        self.thr, self.hold, self.shrink, self.cool = threshold, hold_s, shrink_s, cooldown_s
        self.peak = peak_scale
        self.state, self.start, self.last_end = "idle", 0.0, -9e9
        self.envelope, self.scale, self.wobble = 0.0, 1.0, 0.0

    def update(self, t, speed):
        """-> (state, progress 0..1)."""
        if self.state == "burst":
            p = (t - self.start) / self.hold
            if p >= 1.0:
                self.state, self.start, self.last_end = "shrink", t, t
                return "shrink", 0.0
            self._shape(p, t)
            return "burst", p
        if self.state == "shrink":
            p = (t - self.start) / self.shrink
            if p >= 1.0:
                self.state = "idle"
                self.envelope = self.wobble = 0.0; self.scale = 1.0
                return "idle", 1.0
            self.envelope = 1.0 - ease_out_cubic(p)
            self.scale = 1.0 + (self.peak - 1.0) * self.envelope
            self.wobble = (t - self.start) * 30.0
            return "shrink", p
        if speed >= self.thr and t - self.last_end >= self.cool:
            self.state, self.start = "burst", t
            self._shape(0.0, t)
            return "burst", 0.0
        return "idle", 0.0

    def _shape(self, p, t):
        e = elastic_burst(p)
        self.envelope = e
        self.scale = 1.0 + (self.peak - 1.0) * e
        self.wobble = (t - self.start) * 30.0 if p < 1.0 else 0.0

    def trigger(self, t, *ignored):
        """Force-arm a burst now (demo mode)."""
        self.state, self.start = "burst", t
        self._shape(0.0, t)


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
