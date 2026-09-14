"""Pure logic for dusky-cursor-magic. No gi/evdev imports — testable headless.

macOS find-my-cursor is ALIVE because it tracks motion continuously: shake
harder -> pointer bigger, stop -> shrinks. We mirror that: WiggleDetector
accumulates a `heat` signal (velocity-weighted, exp decay), AuraMachine is a
spring-damper follower of that heat, and StarField throws Starlight's
signature burst of spreading stars on every reversal.
"""
import json, math, os, random, time


class SpeedEstimator:
    """Sliding-window |dx|+|dy| px/s."""
    def __init__(self, window_s=0.05):
        self.window_s = window_s
        self._s = []  # (t, px)
        self._last = None

    def add(self, dx, dy, t=None):
        self._s.append((t if t is not None else time.monotonic(), abs(dx) + abs(dy)))

    def feed(self, t, x, y):
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


class WiggleDetector:
    """Heat signal, not a switch. Each velocity reversal >= min_speed
    deposits gain * min(1, speed/reversal_speed) into .heat; heat decays
    exponentially (tau_s). .fired pulses once per burst past arm_heat."""
    def __init__(self, window_s=0.35, min_speed=900.0, need=None,
                 tau_s=0.42, gain=0.45, reversal_speed=4000.0, arm_heat=0.55):
        # tau 0.42 ≈ kwin's 2s hold: heat visibly sustains ~1.5s after last shake
        # `need` is a deprecated no-op kept so old configs (**cfg["wiggle"]) still load
        self.window_s, self.min_speed = window_s, min_speed
        self.tau_s, self.gain, self.rs = tau_s, gain, reversal_speed
        self.arm_heat = arm_heat
        self.heat = 0.0
        self.rev_count = 0            # monotonic; daemon diffs it for star bursts
        self._v, self._rev, self._last = [], [], None
        self._armed = False

    def feed(self, t, x, y):
        """-> True on the tick heat first crosses arm_heat (one pulse)."""
        fired = False
        if self._last:
            dt = max(t - self._last[0], 1e-4)
            self.heat *= math.exp(-dt / self.tau_s)        # decay every sample
            vx, vy = (x - self._last[1]) / dt, (y - self._last[2]) / dt
            sp = math.hypot(vx, vy)
            if self._v:
                pvx, pvy = self._v[-1][1], self._v[-1][2]
                if (sp >= self.min_speed
                        and math.hypot(pvx, pvy) >= self.min_speed
                        and vx * pvx + vy * pvy < 0):
                    self._rev.append(t)
                    self.rev_count += 1
                    self.heat = min(1.0, self.heat + self.gain * min(1.0, sp / self.rs))
            self._v.append((t, vx, vy))
            self._v = [s for s in self._v if t - s[0] <= self.window_s]
            self._rev = [r for r in self._rev if t - r <= self.window_s]
            if self.heat >= self.arm_heat and not self._armed:
                self._armed = True
                fired = True
            elif self.heat < self.arm_heat * 0.5:
                self._armed = False            # re-arm once calm (hysteresis)
        self._last = (t, x, y)
        return fired

    @property
    def settled(self):
        return self.heat < 0.02


class AuraMachine:
    """Critically-tuned spring follower of heat: scale/alpha chase
    start + (peak-start)*heat with zero steady-state error and no overshoot
    pop — butter growing AND shrinking, alive like macOS."""
    PROFILES = {
        # kwin shakecursor (the only faithful macOS clone in source): 3x mag,
        # 2s hold before deflate. Spring equivalents below (continuous heat
        # replaces kwin's discrete +1x re-magnify, so no separate boost needed).
        # U3: k 240->260, z 0.9->0.88 — measured t95 ~250ms, KWin's 200ms band;
        # melt gets the 1.6x/+.12 exit boost in update()
        "macos":   {"peak": 3.0, "start": 0.35, "k": 260.0, "zeta": 0.88},
        "smooth":  {"peak": 2.6, "start": 0.4,  "k": 90.0,  "zeta": 1.0},
        "snappy":  {"peak": 3.2, "start": 0.3,  "k": 300.0, "zeta": 0.85},
        "reduced": {"peak": 1.0, "start": 1.0,  "k": 120.0, "zeta": 1.0},
    }

    def __init__(self, peak_scale=None, start_scale=None, k=None, zeta=None,
                 profile="macos", age_s=None):
        p = dict(self.PROFILES.get(profile, self.PROFILES["macos"]))
        if peak_scale is not None: p["peak"] = peak_scale
        if start_scale is not None: p["start"] = start_scale
        if k is not None: p["k"] = k
        if zeta is not None: p["zeta"] = zeta
        self.peak, self.start = p["peak"], p["start"]
        self._k, self._z = p["k"], p["zeta"]
        self._reduced = profile == "reduced"
        self.age_s = age_s or 4.0
        self.scale = self.start
        self.alpha = 0.0
        self.v = 0.0                      # scale velocity (spring)
        self.av = 0.0                     # alpha velocity
        self._t = None
        self._settled_at = None
        self._peak_heat = 0.0

    def update(self, t, heat, amb=0.0):
        """heat (wiggle) and amb (ambient speed) in [0,1]; the combination
        drives scale/alpha/energy, but settling keys on wiggle heat alone."""
        dt = 0.0 if self._t is None else min(max(t - self._t, 0.0), 0.05)
        self._t = t
        heat = max(0.0, min(1.0, heat))
        h = min(1.0, heat + max(0.0, amb))
        # U1: leaky peak — energy melts away with the aura instead of
        # staying pinned at the last shake's maximum (stale-hot melt bug)
        self._peak_heat = max(h, self._peak_heat * math.exp(-dt / 0.35))
        # U3: asymmetric spring — exits 1.6x stiffer than enters, so the
        # melt lets go quicker than the grow (Material 225/195 pair)
        tgt = self.start + (self.peak - self.start) * h
        melting = tgt < self.scale
        k = self._k * (1.6 if melting else 1.0)
        z = min(1.0, self._z + (0.12 if melting else 0.0))
        c = 2 * math.sqrt(k) * z
        self.v += (-k * (self.scale - tgt) - c * self.v) * dt
        self.scale += self.v * dt
        ta = (0.35 + 0.65 * h) if h > 0.02 else 0.0   # whisper-dim at low heat
        self.av += (-260.0 * (self.alpha - ta) - 2 * math.sqrt(260.0) * self.av) * dt
        self.alpha = max(0.0, self.alpha + self.av * dt)
        if self._reduced:
            self.scale = 1.0
        if abs(self.scale - tgt) < 0.01 and abs(self.v) < 0.05 and heat < 0.02:
            if self._settled_at is None:
                self._settled_at = t
                self._peak_heat = 0.0
        else:
            self._settled_at = None
        return self.alpha

    def settled(self, t):
        return self._settled_at is not None and t - self._settled_at > 0.45

    @property
    def energy(self):
        """0..1 *recent* heat: peak held, then e-folds toward the current
        heat target over ~1.2 s — sparkles/glow/bursts melt down instead of
        staying pinned at the last violent shake."""
        return self._peak_heat


class StarField:
    """Starlight's signature: a burst of 4-point stars that spread outward
    from the cursor, twinkle, spin and fade. burst() per reversal pulse."""
    def __init__(self, n=10, seed=None):
        self.n = n
        self.rng = random.Random(seed)
        self._stars = []                    # (t0, ang, spd, size, life, spin, tw)

    def burst(self, t, n=None, size=1.0):
        for _ in range(n or self.n):
            ang = self.rng.uniform(0, math.tau)
            self._stars.append((t, ang,
                                self.rng.uniform(260.0, 620.0) * (0.6 + 0.5 * size),  # px/s outward
                                self.rng.uniform(4.0, 11.0) * size,                  # size px
                                self.rng.uniform(1.25, 1.9),       # life s
                                self.rng.uniform(-2.5, 2.5),       # spin rad/s
                                self.rng.uniform(0.5, 1.5)))       # twinkle rate
        # ponytail: O(n) scan per frame; n capped at 120 — fine at 8ms ticks
        if len(self._stars) > 120:
            self._stars = self._stars[-120:]

    def stars(self, t):
        """yield (angle, radius, size, rot, alpha) for living stars."""
        out = []
        tau = 0.35                          # ease-out radius (fast launch, glide)
        for (t0, ang, spd, size, life, spin, tw) in self._stars:
            age = t - t0
            if 0 <= age <= life:
                r = spd * tau * (1.0 - math.exp(-age / tau))
                u = age / life
                a = (1.0 - u * u) * (0.65 + 0.35 * math.sin(age * tw * math.tau))
                out.append((ang, r, size * (1.0 - 0.4 * u), spin * age, max(0.0, a)))
        self._stars = [s for s in self._stars if 0 <= t - s[0] <= s[4]]
        return out

    @property
    def count(self):
        return len(self._stars)


def frame_index(durations, t):
    """Index of the frame at elapsed time t inside a looping animation.
    Wraps forever: frame = durations[:n] played back-to-back, t % total."""
    total = float(sum(durations)) if durations else 0.0
    if not durations or total <= 0.0:
        return 0
    t %= total
    acc = 0.0
    for i, d in enumerate(durations):
        acc += d
        if t < acc:
            return i
    return len(durations) - 1


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
