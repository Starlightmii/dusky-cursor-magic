#!/usr/bin/env python3
"""Cursor Soul — shader-field aura layer (CPU GPU-style field, cairo blit).

The feel Starlight asked for: the aura is alive under the pointer and reacts
to how you MOVE — sweep fast and it swells smooth; stop and it settles slow
(asymmetric easing, macOS butter). At rest it breathes. Every click fires a
ripple ring + energy flash from the pointer. Domain-warped FBM noise gives it
an organic, animated shader look; it renders into a small click-through
layer-shell window using the exact transport the sprite daemon proves visible
on Hyprland every day (GL was tried first: this box's EGL/GTK-GLArea combo
renders internally but never composites — dead end, kept nothing of it).

Standalone process — zero coupling with cursor_magic.py, stacks OVERLAY
beside it with a soft hole in the centre so the system cursor stays clear.

    /usr/bin/python3 shader_soul.py [--test] [--fps 60] [--canvas 256]

Self-check:  --test  (prints PASS/FAIL on speed-grows-size + centre ink)
"""
import argparse
import math
import os
import random
import socket
import subprocess
import sys
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell, GLib  # noqa: E402
import cairo  # noqa: E402
import numpy as np  # noqa: E402

RIPPLE_LIFE = 0.85


def set_cursor_theme(theme, size):
    subprocess.run(["hyprctl", "dispatch", "setcursor", str(theme), str(size)],
                   capture_output=True, timeout=5)


def _wal_rgb(hexcol):
    h = (hexcol or "").strip().lstrip("#")
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None


def surface_lum(x, y):
    """Mean luminance of the 40x40 patch just BELOW the pointer (offset so
    the soul's own aura isn't in frame — it would read itself). grim -t png
    -l 0 to stdout keeps it one subprocess, no temp file. None on failure."""
    try:
        import io
        from PIL import Image
        g = subprocess.run(
            ["grim", "-g", f"{int(x) - 20},{int(y) + 30} 40x40",
             "-t", "png", "-l", "0", "-"],
            capture_output=True, timeout=1.0)
        if g.returncode:
            return None
        a = np.asarray(Image.open(io.BytesIO(g.stdout)).convert("L"),
                       np.float32) / 255.0
        return float(a.mean())
    except Exception:
        return None


def dusky_theme(path=None):
    """Auto colour: Dusky's pywal palette (~/.cache/wal/colors.json, rewritten
    every time the theme/wallpaper changes) -> (cool, warm) aura tints.
    Issue dusklinux/dusky#343 asks for themeable cursor colours; matching the
    UI theme automatically IS that feature for the soul. Falls back to the
    moonlight blue when wal is missing/blank. Dark entries are normalised to
    full brightness so they keep their hue as a glow."""
    try:
        import json
        with open(path or os.path.expanduser("~/.cache/wal/colors.json")) as f:
            cs = json.load(f).get("colors", {})
    except (OSError, ValueError):
        return None

    def pick(*keys):
        for k in keys:
            rgb = _wal_rgb(cs.get(k))
            if rgb and max(rgb) > 0.15:      # skip black-ish slots
                m = max(rgb)
                return tuple(min(c / m, 1.0) for c in rgb)
        return None
    cool = pick("color12", "color4", "color3", "color10", "color5", "color13")
    warm = pick("color11", "color6", "color14", "color13", "color15", "color10")
    if not cool and not warm:
        return None
    return (cool or (0.42, 0.62, 1.00), warm or (1.00, 0.72, 0.38))


def hypr_sockets():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    for base in (f"/run/user/{os.getuid()}/hypr/{sig}", f"/tmp/hypr/{sig}"):
        if os.path.exists(base + "/.socket.sock"):
            return base + "/.socket.sock", base + "/.socket2.sock"
    sys.exit("shader_soul: no hyprland socket — run inside Hyprland")


SOCK, ESOCK = hypr_sockets()


def hypr(msg):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCK)
        s.sendall(msg.encode())
        r = s.recv(8192).decode(errors="replace")
        s.close()
        return r.strip()
    except OSError:
        return ""


# --------------------------------------------------------------- the field
# FBM value noise, vectorised. One permutation-free lattice hash per octave
# (frac(sin) trick like the GPU version — cheap and fine at these sizes).
def _hash2(ix, iy):
    return (np.sin(ix * 127.1 + iy * 311.7) * 43758.5453) % 1.0


def _noise(x, y):
    ix, iy = np.floor(x), np.floor(y)
    fx, fy = x - ix, y - iy
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = _hash2(ix, iy)
    b = _hash2(ix + 1, iy)
    c = _hash2(ix, iy + 1)
    d = _hash2(ix + 1, iy + 1)
    return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy


def fbm(x, y, octaves=3):
    v = np.zeros_like(x)
    amp = 0.5
    for _ in range(octaves):
        v += amp * _noise(x, y)
        x = x * 2.03
        y = y * 2.03
        amp *= 0.5
    return v


class Stars:
    """Galaxy sparkle field: 4-point stars (Gaussian cross) with ease-out
    radial launch, spin, twinkle; trail stars drift in slow orbit. All
    additive into the same glow field, tinted by aura tints."""
    TAU0 = 0.35

    def __init__(self, cap=140):
        self._s = []          # (t0, ang, spd, size, life, spin, tw, r0, drift)
        self.cap = cap

    def shed(self, t, x, y, size=1.0):
        """One trail sparkle: slow lazy drift, golden-angle direction."""
        self._s.append((t, t * 2.39996 % math.tau, random.uniform(30, 90),
                        random.uniform(4, 9) * size, random.uniform(0.55, 0.95),
                        random.uniform(-1.0, 1.0), random.uniform(1.5, 2.6),
                        (x, y), random.uniform(0.5, 1.6)))
        if len(self._s) > self.cap:
            self._s = self._s[-self.cap:]

    def burst(self, t, x, y, n_ring=14, n_hero=2, n_micro=5, size=1.0,
              speed=1.0):
        """Layered click-burst (recipe from research Cycle-6: Konixx/VFX
        assets — ring is the read, micro the texture, hero the focal):
        even ring +0.05rad jitter + alternating radius, golden-angle micro
        at sub speeds, 2.2x slow hero. No gravity, no duplicates."""
        rng = random.random
        for i in range(n_ring):
            ang = i * math.tau / n_ring + (rng() - 0.5) * 0.087
            self._add(t, ang, random.uniform(300, 450) * size * speed,
                      random.uniform(14, 26) * size * (1.0 if i % 2 else 0.72),
                      random.uniform(0.55, 0.75), 0.75 * (rng() - 0.5) * 2,
                      random.uniform(1.6, 2.4), x, y, rng() * 0.5)
        for _ in range(n_hero):
            ang = rng() * math.tau
            self._add(t, ang, random.uniform(140, 250), random.uniform(14, 26) * 2.2,
                      random.uniform(0.9, 1.2), random.uniform(6, 10) * (1 - 2 * rng()),
                      random.uniform(3, 4), x, y, rng() * 0.4)
        for i in range(n_micro):
            ang = i * 2.39996 + rng() * 0.15           # golden angle, jittered
            v = random.uniform(0.25, 0.6)
            self._add(t, ang, random.uniform(300, 450) * v, random.uniform(6, 10),
                      random.uniform(0.3, 0.45), random.uniform(1, 4) * (1 - 2 * rng()),
                      random.uniform(2.2, 3.2), x, y, rng() * 0.3)
        if len(self._s) > self.cap:
            self._s = self._s[-self.cap:]

    def supernova(self, t, x, y):
        """Fast-sweep-then-stop blast: over-driven click burst at 1.6x
        speed/size + a white-hot energy spike + shockwave ring (caller
        adds the ripple with scale >1). Cooldown lives in the caller."""
        self.burst(t, x, y, n_ring=18, n_hero=3, n_micro=8, size=1.5,
                   speed=1.6)

    def _add(self, t, ang, spd, size, life, spin, tw, x, y, drift):
        # asymptotic travel ≈ spd*0.31 over a star's life; clamp 500 → ≤155px
        # so every star FADES before the 160px half-window edge — the blast
        # lives in open space, not a box. Normal-burst ring max is 450 (kept)
        # so a supernova (raw spd ~1000, clamped 500) still outruns a click.
        self._s.append((t, ang, min(spd, 500.0), size, life, spin, tw,
                        (x, y), drift))

    def live(self, t, org=(0.0, 0.0), half=160.0):
        """[(x, y, size, rot, alpha)] in field coords (canvas px, centre-
        relative). Stars store SCREEN px — the galaxy stays put while the
        overlay window chases the pointer. Twinkle = per-star rate + a
        spiral wave shared across the burst (sin(t*ω + ang*3)) — the galaxy
        pulses as one, then desyncs."""
        ox, oy = org[0] + half, org[1] + half      # canvas centre on screen
        out = []
        keep = []
        for (t0, ang, spd, size, life, spin, tw, r0, drift) in self._s:
            age = t - t0
            if 0 <= age <= life:
                r = spd * self.TAU0 * (1.0 - math.exp(-age / self.TAU0))
                u = age / life
                tw_k = 0.5 * math.sin(age * tw * math.tau)
                a = (1.0 - u * u) * (0.45 + 0.25 * tw_k
                     + 0.30 * math.sin(t * 2.6 + ang * 3.0))
                # Steinrücken twinkle: SIZE pulses with brightness (never
                # vanishes flat) — same phase, 50-150%
                size_k = size * (1.0 + 0.5 * tw_k) * (1.0 - 0.4 * u)
                # Köppen log-spiral arms (b≈1.2, Milky-Way model): outer
                # stars lag by b*ln(1+r/40) so ANY burst shears into galaxy
                # arms; differential-omega term keeps inner orbit faster
                ang2 = (ang + drift * age * (1.0 - 0.45 * min(r / 90.0, 1.0))
                        + 1.2 * math.log1p(r / 40.0))
                out.append((r0[0] + r * math.cos(ang2) - ox,
                            r0[1] + r * math.sin(ang2) - oy,
                            size_k, spin * age, max(0.0, a)))
                keep.append((t0, ang, spd, size, life, spin, tw, r0, drift))
        self._s = keep
        return out

def stamp(gx, gy, glow, stars, scale=2):
    """Additive 4-point sparkles. Star coords are canvas px relative to the
    field CENTER (same frame as gx/gy, which span -half..+half canvas px);
    field index = coord/scale + half. Windowed to each star's bbox — a
    30-star burst costs ~2ms, a full-grid stamp would cost 45ms."""
    hy, hx = glow.shape[0] / 2.0, glow.shape[1] / 2.0
    for (x, y, size, rot, a) in stars:
        fx, fy = x / scale + hx, y / scale + hy     # field index space
        if a <= 0.01 or not (-glow.shape[0] < fy < 2 * glow.shape[0]
                             and -glow.shape[1] < fx < 2 * glow.shape[1]):
            continue
        hw = int(size * 1.35 / scale) + 2
        x0, x1 = max(int(fx) - hw, 0), min(int(fx) + hw + 1, glow.shape[1])
        y0, y1 = max(int(fy) - hw, 0), min(int(fy) + hw + 1, glow.shape[0])
        if x0 >= x1 or y0 >= y1:
            continue
        dx = gx[y0:y1, x0:x1] - x
        dy = gy[y0:y1, x0:x1] - y
        c, s_ = math.cos(rot), math.sin(rot)
        u = dx * c + dy * s_
        v = -dx * s_ + dy * c
        sig = size * 0.28
        g = glow[y0:y1, x0:x1]
        g += (np.exp(-(u * u) / (sig * sig) - (v * v) / (sig * sig * 9.0))
              + np.exp(-(v * v) / (sig * sig) - (u * u) / (sig * sig * 9.0))) * a * 1.4
        g += np.exp(-(dx * dx + dy * dy) / (sig * sig)) * a * 0.9


class Aura:
    """Pixel field with speed-scaling, breathing, ripples, click energy.
    Renders at 1/2 canvas resolution; cairo upscales (the glow is low
    frequency — half-res is pixel-identical to the eye, 4x less CPU)."""

    SCALE = 2

    def __init__(self, canvas, radius, strength, warp_seed, grow=1.6, ascale=0.55,
                 tints=None):
        self.C, self.R0, self.strength = canvas, radius, strength
        self.grow, self.ascale = grow, ascale
        self.seed = warp_seed
        self.tints = tints  # None -> moonlight default; set live from wal
        F = canvas // self.SCALE
        self.F = F
        c = np.arange(F, dtype=np.float32)
        gx, gy = np.meshgrid(c - F / 2, c - F / 2)
        self.gx, self.gy = gx * self.SCALE, gy * self.SCALE
        self.r = np.hypot(self.gx, self.gy)
        self.nx = self.gx * 0.028
        self.ny = self.gy * 0.028

    def render(self, t, speed, energy, ripples, out, core=False,
               hot=(0.0, 0.0), vel=(0.0, 0.0), trail=(0.0, 0.0), stars=()):
        """Fill ARGB32 numpy `out` (F x F view) with the current aura frame.
        hot = pointer offset from canvas centre in canvas px (non-zero at
        screen edges where the layer window clamps). Ripples carry
        (gx,gy,age,strength); core=True paints the orb AT the pointer.
        vel = smoothed pointer velocity (canvas px/frame): the orb squashes
        along its motion like hypr-dynamic-cursors tilts the sprite."""
        R = self.R0 * (1.0 + self.grow * speed) * self.strength
        rx = self.gx - hot[0]
        ry = self.gy - hot[1]
        r = (self.r if hot == (0.0, 0.0) else np.hypot(rx, ry))
        # organic warp
        wob = fbm(self.nx + self.seed, self.ny + t * 0.18
                  + fbm(self.nx * 0.5 - t * 0.06, self.ny * 0.5, 2) * 0.9, 3)
        glow = np.exp(-((r / R) ** 2))
        ring = np.exp(-(((r - R * 0.82) / (R * 0.35)) ** 2)) * (0.30 + 0.25 * speed)
        glow += ring
        glow *= 1.0 + (wob - 0.5) * (0.55 + 0.35 * speed)
        glow += energy * np.exp(-((r / R) ** 2)) * 0.6
        # click ripples: expanding rings that fade. exp=1.0 linear (click);
        # exp=0.4 Sedov-Taylor blast wave (supernova): violent breakout that
        # decelerates — R ∝ t^0.4 is how real supernova remnants expand.
        for (x, y, age, s, exp) in ripples:
            if 0.0 <= age < RIPPLE_LIFE:
                uu = age / RIPPLE_LIFE
                # endpoint R0*4.2 = 143px < half-window (160): rings fade out
                # on their own INSIDE the field — no edge pin, no hidden box.
                # exp<1 = Sedov-Taylor blast, exp=1 = linear click ring
                rr = self.R0 * 4.2 * (uu ** exp)
                # Sedov pressure decay behind the front: amp ∝ t^-1.2 flash
                # × (1-u) life-fade (omni cycle-7, unclamped — the [0,1]
                # clamp flattens it back to linear). Breakout punches, the
                # remnant evaporates; top-clamped at 2.2 = nova flash scale.
                amp = min((0.3 / max(uu, 0.05)) ** 1.2 * (1.0 - uu), 2.2) \
                    if exp < 1.0 else (1.0 - uu)
                band = np.exp(-(((np.hypot(self.gx - x * self.SCALE,
                                           self.gy - y * self.SCALE) - rr)
                                 / (self.R0 * 0.18)) ** 2))
                glow += band * amp * s * 0.8
        # alive ring hugging the pointer (breathes, tightens when moving)
        pulse = 0.9 + 0.10 * math.sin(t * 2.6) + 0.06 * math.sin(t * 5.1)
        ringR = self.R0 * 0.20 * (1.0 - 0.25 * speed) * pulse
        glow += np.exp(-(((r - ringR) / (self.R0 * 0.05)) ** 2)) \
            * (0.55 + 0.25 * energy) * pulse
        glow = np.maximum(glow, 0.0)
        if core:
            # arrow hidden -> we ARE the cursor: opaque white-hot core (blue
            # halo from the ring carries the fantasy tint), reads on any page
            cr_ = self.R0 * 0.24 * (1.0 + 0.12 * math.sin(t * 2.6))
            vmag = min(math.hypot(vel[0], vel[1]) * 0.05, 1.0)
            if vmag > 0.02:
                # hypr-dynamic-cursors feel: squash along motion, bulge across
                ux, uy = vel[0], vel[1]
                un = math.hypot(ux, uy) or 1.0
                ux, uy = ux / un, uy / un
                along = (rx * ux + ry * uy) / (cr_ * (1.0 + 0.5 * vmag))
                perp = (rx * uy - ry * ux) / (cr_ * (1.0 - 0.28 * vmag))
                core_w = np.exp(-(along * along + perp * perp))
            else:
                core_w = np.exp(-((r / cr_) ** 2))
            glow += core_w * 2.2
        else:
            # soft hole so the real cursor sprite stays crisp at the centre
            glow *= np.clip((r - 10.0) / 24.0, 0.0, 1.0)
            core_w = None
        # comet tail: a fainter orb lagging behind the pointer (EMA fed by
        # caller at ~1/3 the rate -> it trails and catches up, moonlight feel)
        if core and trail != (0.0, 0.0):
            tx, ty = trail[0] - hot[0], trail[1] - hot[1]
            if math.hypot(tx, ty) > 6.0:
                rt = np.hypot(rx - tx, ry - ty)
                glow += np.exp(-((rt / (cr_ * 0.8)) ** 2)) * 0.8 * min(
                    math.hypot(tx, ty) / 40.0, 1.0)
        # galaxy star field: click-bursts + shed trail stars, same tints,
        # one clock (passed t) — everything twinkles in synced phase waves
        if stars:
            stamp(self.gx, self.gy, glow, stars, self.SCALE)
        a = np.clip(glow * self.ascale, 0.0, 1.0)
        tint = np.clip(wob * 0.6 + speed * 0.55 + energy * 0.35, 0.0, 1.0)[..., None]
        cool_, warm_ = self.tints or ((0.42, 0.62, 1.00), (1.00, 0.72, 0.38))
        cool = np.array(cool_, np.float32)
        warm = np.array(warm_, np.float32)
        rgb = cool + (warm - cool) * tint
        if core_w is not None:
            rgb = rgb + (1.0 - rgb) * np.clip(core_w * 3.0, 0.0, 1.0)[..., None]
        alpha_u8 = (a * 255).astype(np.uint8)
        # premultiplied -> ARGB32 native uint32 (A<<24 | R<<16 | G<<8 | B)
        argb = ((alpha_u8.astype(np.uint32) << 24)
                | ((rgb[..., 0] * a * 255).astype(np.uint8).astype(np.uint32) << 16)
                | ((rgb[..., 1] * a * 255).astype(np.uint8).astype(np.uint32) << 8)
                | (rgb[..., 2] * a * 255).astype(np.uint8).astype(np.uint32))
        out[...] = argb


# ------------------------------------------------------------------ helpers
def field_only(canvas, radius, t, speed, energy, seed=0.0, grow=1.6):
    a = Aura(canvas, radius, 1.0, seed, grow=grow)
    buf = np.zeros((a.F, a.F), np.uint32)
    a.render(t, speed, energy, [], buf)
    return buf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true",
                    help="self-check the speed-grows-size physics, print PASS/FAIL, exit")
    ap.add_argument("--canvas", type=int, default=320)
    ap.add_argument("--radius", type=float, default=34.0)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--hue-seed", type=float, default=0.0)
    ap.add_argument("--grow", type=float, default=1.2,
                    help="how much the aura scales up at full speed")
    ap.add_argument("--glow", type=float, default=0.50,
                    help="overall brightness multiplier")
    ap.add_argument("--renderer", choices=("cpu", "gpu"), default="gpu",
                    help="aura field renderer (gpu = Intel iGPU GLES3; falls back to cpu)")
    ap.add_argument("--music", choices=("on", "off"), default="on",
                    help="sync aura/stars to whatever plays through the speakers")
    ap.add_argument("--homing", choices=("on", "off"), default="on",
                    help="the soul leans toward the pointer, like a pet")
    ap.add_argument("--surface", choices=("on", "off"), default="on",
                    help="read what's UNDER the cursor: brighter over dark UI")
    args = ap.parse_args()
    C = args.canvas

    if args.test:                                   # headless self-check
        rest = field_only(C, args.radius, 0.5, 0.0, 0.0, grow=args.grow)
        fast = field_only(C, args.radius, 0.5, 1.0, 0.0, grow=args.grow)
        F = C // Aura.SCALE
        n_rest = int((rest >> 24 > 12).sum())
        n_fast = int((fast >> 24 > 12).sum())
        hole = int((rest[F // 2, F // 2] >> 24))
        # the physics the user demanded: fast grows smooth, never floods
        ok = n_fast > 1.8 * n_rest > 0 and n_fast < F * F * 0.8 and hole == 0
        print(f"TEST: rest={n_rest}px fast={n_fast}px growth={n_fast / max(n_rest,1):.2f}x "
              f"centre-hole-a={hole}", flush=True)
        print("TEST:", "PASS" if ok else "FAIL", flush=True)
        sys.exit(0 if ok else 1)

    # ---- window: same transport the sprite daemon proves daily ------------
    win = Gtk.Window(type=Gtk.WindowType.POPUP)
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_exclusive_zone(win, -1)
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
    win.set_size_request(C, C)
    win.set_app_paintable(True)
    win.set_decorated(False)
    # click-through: Gtk.set_input_shape is a NO-OP on Wayland — the daemon's
    # proven path is the raw gdk window, re-applied on realize AND map
    # (this window sits under the cursor 24/7; if hit-testing ever reverts
    # to full-window it swallows every click — the "not clicking" bug).
    def _pt(w):
        w.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
    win.connect("realize", _pt)
    win.connect("map", _pt)
    area = Gtk.DrawingArea()
    area.set_size_request(C, C)
    win.add(area)

    surf_box = [None]

    def on_draw(_w, cr):
        if surf_box[0] is not None:
            cr.scale(C / F, C / F)              # nearest upscale, half-res field
            cr.set_source_surface(surf_box[0], 0, 0)
            cr.paint()
        return False
    area.connect("draw", on_draw)
    win.show_all()

    # self-register like the sprite daemon: studio reads this to toggle/kill.
    # flock so a second spawn exits silently instead of leaking a ghost layer
    pidfile = os.path.expanduser("~/.cache/cursor-magic/soul.pid")
    os.makedirs(os.path.dirname(pidfile), exist_ok=True)
    import fcntl
    _lock = open(pidfile, "a+")        # NO truncate: a refused spawn must not
    try:                               # clobber the live soul's pidfile
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(0)          # another soul owns the layer
    _lock.truncate(0); _lock.seek(0)
    _lock.write(str(os.getpid())); _lock.flush()

    # ---- state -------------------------------------------------------------
    CFG = os.path.expanduser("~/.config/dusky/cursor-magic/config.json")
    cfg_cache = [None, 0.0]
    def cfg():
        now = time.monotonic()
        if now - cfg_cache[1] > 1.0:
            cfg_cache[1] = now
            try:
                import json
                with open(CFG) as f:
                    cfg_cache[0] = json.load(f).get("soul") or {}
            except (OSError, ValueError):
                pass
            t = dusky_theme()
            if t:
                aura.tints = t
        return cfg_cache[0]

    # arrow control was the old sprite daemon's last job — soul owns it now.
    # Only touch hyprctl when the state actually flips (setcursor is a
    # compositor-wide op).
    arrow_st = [None]
    def apply_arrow(ac):
        want = bool(ac.get("hide_arrow")) and bool(ac.get("on", True))
        if want == arrow_st[0]:
            return
        arrow_st[0] = want
        try:
            if want:
                set_cursor_theme("Invisible", 24)
            else:
                set_cursor_theme(os.environ.get("XCURSOR_THEME", "Dusky"),
                                 int(os.environ.get("XCURSOR_SIZE", 18)))
        except Exception:
            pass

    def _restore_arrow():
        try:
            set_cursor_theme(os.environ.get("XCURSOR_THEME", "Dusky"),
                             int(os.environ.get("XCURSOR_SIZE", 18)))
        except Exception:
            pass
    import atexit
    atexit.register(_restore_arrow)
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # atexit runs

    def make_aura():
        if args.renderer == "gpu":
            try:
                import soul_gl
                a = soul_gl.SoulGL(C, args.radius, args.strength,
                                   args.hue_seed, grow=args.grow,
                                   ascale=args.glow)
                print("aura renderer = gpu (iGPU GLES3)", flush=True)
                return a
            except Exception as e:            # GL init/compile: never die,
                print(f"aura gpu failed ({e}); cpu", flush=True)   # just fall back
        return Aura(C, args.radius, args.strength, args.hue_seed,
                    grow=args.grow, ascale=args.glow)
    aura = make_aura()
    F = aura.F
    buf = np.zeros((F, F), np.uint32)
    speed = [0.0]
    energy = [0.0]
    peak = [0.0]                   # max speed since last blast (supernova arm)
    nova_at = [-9.0]               # monotonic time of last supernova
    nova_pt = [None]               # (now, x, y) of shockwave ring to place once hot is known
    vel = [(0.0, 0.0)]                # smoothed per-frame pointer delta
    ripples = []                     # canvas-local (x-off, y-off, t0, s)
    stars = Stars()                  # galaxy sparkles (canvas px coords)
    shed_pt = [None]                 # last trail-star spawn point (screen px)
    mus = None
    if args.music == "on":
        try:
            import music
            mus = music.Music()
            mus.start()
        except Exception:
            mus = None               # no audio tap -> soul behaves normally
    bob = [0.0, 0.0, 0.0, 0.0]       # homing spring x,y,vx,vy (the pet leans)
    twitch_at = [0.0]                # next idle micro-sparkle time
    surf = [0.5, 0.0]                # surface lum EMA + last sample time
    if args.surface == "on":
        import threading

        def _sense():                # 2 Hz: what is the soul hovering over?
            while True:
                time.sleep(0.5)
                try:
                    l = surface_lum(ptr[0], ptr[1])
                except Exception:
                    l = None
                if l is not None:
                    surf[0] += (l - surf[0]) * 0.25   # slow EMA: no strobing
        threading.Thread(target=_sense, daemon=True).start()
    last = [None, None, None, 0.0]   # [pos, idle-pos, idle-hot, last-render]
    trail = [None]                   # slow EMA of screen pointer pos
    evsock = [None]
    start = time.monotonic()
    screen = [1920, 1080]
    try:
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk
        mon = (Gdk.Display.get_default().get_primary_monitor()
               or Gdk.Display.get_default().get_monitor(0))
        geo = mon.get_geometry()
        screen[0], screen[1] = geo.width, geo.height
    except Exception:
        pass

    # clicks: same proven evdev watcher the daemon uses (socket2 events
    # proved unreliable — the .sock is a request socket, not an event bus).
    from clicks import ClickWatcher

    def on_click(ev):
        if ev["kind"] == "press":
            click_q.append(ev)

    click_q = __import__("collections").deque()
    watcher = ClickWatcher(); watcher.start(on_click)
    hot_st = [0.0, 0.0]              # live pointer offset from canvas centre
    ptr = [0, 0]                     # live pointer screen px

    def poll_clicks(now):
        while click_q:
            ev = click_q.popleft()
            energy[0] = 1.0
            ripples.append((hot_st[0] / Aura.SCALE, hot_st[1] / Aura.SCALE,
                            now, 1.0, 1.0))
            del ripples[:-4]
            stars.burst(now - start, float(ptr[0]), float(ptr[1]),
                        speed=1.0 + min(speed[0], 0.6))

    pos_file = os.environ.get("AURA_POS_FILE")   # test seam: file has 'x y'

    def tick():
        now = time.monotonic()
        ac = cfg()
        apply_arrow(ac)
        if not ac.get("on", True):
            if win.get_visible():
                win.hide()
            return True
        if not win.get_visible():
            win.show()
        out = open(pos_file).read() if pos_file else hypr("cursorpos")
        try:
            x, y = map(int, out.replace(",", " ").split()[:2])
        except ValueError:
            return True
        if last[0]:
            dx, dy = x - last[0][0], y - last[0][1]
            inst = min(math.hypot(dx, dy) * 2.6e-4 * args.fps, 1.0)
            # macOS feel: grow fast, shrink slow (asymmetric easing)
            a = 0.30 if inst > speed[0] else 0.055
            speed[0] += (inst - speed[0]) * a
            va = 0.35 if math.hypot(*vel[0]) > math.hypot(dx, dy) else 0.18
            vel[0] = (vel[0][0] + (dx - vel[0][0]) * va,
                      vel[0][1] + (dy - vel[0][1]) * va)
            # SUPERNOVA: a fast sweep that slams on the brakes detonates.
            # arm on peak>0.85, fire when speed collapses <0.35, 1.2s cooldown
            peak[0] = max(peak[0], speed[0])
            if (peak[0] > 0.85 and speed[0] < 0.35
                    and now - nova_at[0] > 1.2):
                nova_at[0] = now
                peak[0] = 0.0
                energy[0] = 2.2                  # white-hot flash (clip handles it)
                stars.supernova(now - start, float(x), float(y))
                nova_pt[0] = (now, x, y)         # shockwave ring once hot is known
        last[0] = (x, y)
        if trail[0] is None:
            trail[0] = (float(x), float(y))
        else:  # lag behind, catch up softly (0.18 ≈ 1/3 of the 0.55 shrink)
            trail[0] = (trail[0][0] + (x - trail[0][0]) * 0.18,
                        trail[0][1] + (y - trail[0][1]) * 0.18)
        ml = min(max(x - C // 2, 0), screen[0] - C)
        mt = min(max(y - C // 2, 0), screen[1] - C)
        hot = (float(x - ml - C // 2), float(y - mt - C // 2))
        trail_hot = (trail[0][0] - ml - C / 2.0, trail[0][1] - mt - C / 2.0)
        if args.homing == "on":
            # the pet leans: a damped spring drags the aura centre toward the
            # pointer's motion, so fast flicks make it swing after you
            tx = max(-14.0, min(14.0, vel[0][0] * 0.30))
            ty = max(-14.0, min(14.0, vel[0][1] * 0.30))
            bob[2] += (tx - bob[0]) * 0.10 - bob[2] * 0.22
            bob[3] += (ty - bob[1]) * 0.10 - bob[3] * 0.22
            bob[0] += bob[2]
            bob[1] += bob[3]
            hot = (hot[0] + bob[0], hot[1] + bob[1])
            trail_hot = (trail_hot[0] + bob[0], trail_hot[1] + bob[1])
        hot_st[0], hot_st[1] = hot
        ptr[0], ptr[1] = x, y
        if nova_pt[0]:                               # place deferred shockwave
            (nnow, nx_, ny_) = nova_pt[0]
            nova_pt[0] = None
            ripples.append(((nx_ - ml - C / 2.0) / Aura.SCALE,
                            (ny_ - mt - C / 2.0) / Aura.SCALE, nnow, 2.4, 0.4))
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, ml)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, mt)
        poll_clicks(now)
        energy[0] *= 0.90
        bass = mid = treb = beat = 0.0
        if mus:
            bass, mid, treb, beat = mus.poll(now)
            if bass > 0.5 and beat > 0.25 and speed[0] < 0.3:
                # a kick lands while you're parked: the soul flares a touch
                energy[0] = max(energy[0], min(0.55, beat * 0.35))
            if beat > 0.6 and speed[0] > 0.05:
                # riding a fast sweep across the downbeat: sprinkle stars
                stars.shed(now - start, x, y, size=0.5 + beat * 0.6)
        # idle twitch: alone and still, the soul breathes a tiny sparkle
        if (not mus or bass < 0.05) and speed[0] < 0.02 and now > twitch_at[0]:
            twitch_at[0] = now + random.uniform(2.5, 5.0)
            stars.shed(now - start, x + random.uniform(-8, 8),
                       y + random.uniform(-8, 8), size=0.35)
        # tail stars: shed a sparkle whenever the trail orb has drifted >=26px
        # from the last spawn — sparkles mark the path, spaced, synced twinkle
        tp = trail[0]
        if speed[0] > 0.12 and (shed_pt[0] is None
                                or math.hypot(tp[0] - shed_pt[0][0],
                                              tp[1] - shed_pt[0][1]) > 26.0):
            shed_pt[0] = tp
            stars.shed(now - start, tp[0], tp[1], size=0.7 + speed[0])
        live = [(rx, ry, now - t0, s, e) for (rx, ry, t0, s, e) in ripples
                if now - t0 < RIPPLE_LIFE]
        slive = stars.live(now - start, (ml, mt), C / 2.0)
        # idle budget: pointer still + nothing decaying -> 30fps is plenty
        # (the 2.6rad/s breath samples fine at half rate; 2x less CPU)
        moved = last[1] != (x, y) or hot != last[2]
        active = moved or speed[0] > 0.01 or energy[0] > 0.02 or live or slive
        if not active and now - last[3] < 1.0 / 30.0:
            return True
        last[3] = now
        last[1], last[2] = (x, y), hot
        # live knobs from studio sliders
        aura.grow = float(ac.get("grow", args.grow))
        # surface: dark UI beneath the pointer -> the soul shines harder,
        # bright paper -> it dims (contrast instinct, like a firefly)
        surfk = 1.0 + (0.5 - surf[0]) * 0.5 if args.surface == "on" else 1.0
        aura.ascale = float(ac.get("glow", args.glow)) * (1.0 + 0.5 * treb) * surfk
        aura.R0 = float(ac.get("radius", args.radius)) + 7.0 * bass
        aura.strength = float(ac.get("strength", args.strength)) * (1.0 + 0.35 * mid)
        aura.render(now - start, speed[0], energy[0], live, buf,
                    core=bool(ac.get("hide_arrow")), hot=hot, vel=vel[0],
                    trail=trail_hot, stars=slive)
        surf_box[0] = cairo.ImageSurface.create_for_data(
            buf.view(np.uint8), cairo.FORMAT_ARGB32, F, F)
        area.queue_draw()
        return True

    GLib.timeout_add(int(1000 / args.fps), tick)
    Gtk.main()


if __name__ == "__main__":
    main()
