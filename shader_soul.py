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
import socket
import sys
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell, GLib  # noqa: E402
import cairo  # noqa: E402
import numpy as np  # noqa: E402

RIPPLE_LIFE = 0.85


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


class Aura:
    """Pixel field with speed-scaling, breathing, ripples, click energy.
    Renders at 1/2 canvas resolution; cairo upscales (the glow is low
    frequency — half-res is pixel-identical to the eye, 4x less CPU)."""

    SCALE = 2

    def __init__(self, canvas, radius, strength, warp_seed, grow=1.6, ascale=0.55):
        self.C, self.R0, self.strength = canvas, radius, strength
        self.grow, self.ascale = grow, ascale
        self.seed = warp_seed
        F = canvas // self.SCALE
        self.F = F
        c = np.arange(F, dtype=np.float32)
        gx, gy = np.meshgrid(c - F / 2, c - F / 2)
        self.gx, self.gy = gx * self.SCALE, gy * self.SCALE
        self.r = np.hypot(self.gx, self.gy)
        self.nx = self.gx * 0.028
        self.ny = self.gy * 0.028

    def render(self, t, speed, energy, ripples, out, core=False):
        """Fill ARGB32 numpy `out` (F x F view) with the current aura frame.
        Pointer sits at field centre; ripples carry (gx,gy,age,strength).
        core=True: system arrow hidden -> we ARE the cursor, paint a bright
        orb at the centre instead of punching the soft hole for it."""
        R = self.R0 * (1.0 + self.grow * speed) * self.strength
        r = self.r
        # organic warp
        wob = fbm(self.nx + self.seed, self.ny + t * 0.18
                  + fbm(self.nx * 0.5 - t * 0.06, self.ny * 0.5, 2) * 0.9, 3)
        glow = np.exp(-((r / R) ** 2))
        ring = np.exp(-(((r - R * 0.82) / (R * 0.35)) ** 2)) * (0.30 + 0.25 * speed)
        glow += ring
        glow *= 1.0 + (wob - 0.5) * (0.55 + 0.35 * speed)
        glow += energy * np.exp(-((r / R) ** 2)) * 0.6
        # click ripples: expanding rings that fade
        for (x, y, age, s) in ripples:
            if 0.0 <= age < RIPPLE_LIFE:
                rr = age * self.R0 * 6.0
                band = np.exp(-(((np.hypot(self.gx - x * self.SCALE,
                                           self.gy - y * self.SCALE) - rr)
                                 / (self.R0 * 0.18)) ** 2))
                glow += band * (1.0 - age / RIPPLE_LIFE) * s * 0.8
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
            core_w = np.exp(-((r / cr_) ** 2))
            glow += core_w * 2.2
        else:
            # soft hole so the real cursor sprite stays crisp at the centre
            glow *= np.clip((r - 10.0) / 24.0, 0.0, 1.0)
            core_w = None
        a = np.clip(glow * self.ascale, 0.0, 1.0)
        tint = np.clip(wob * 0.6 + speed * 0.55 + energy * 0.35, 0.0, 1.0)[..., None]
        cool = np.array((0.42, 0.62, 1.00), np.float32)
        warm = np.array((1.00, 0.72, 0.38), np.float32)
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
    ap.add_argument("--canvas", type=int, default=256)
    ap.add_argument("--radius", type=float, default=34.0)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--hue-seed", type=float, default=0.0)
    ap.add_argument("--grow", type=float, default=1.2,
                    help="how much the aura scales up at full speed")
    ap.add_argument("--glow", type=float, default=0.50,
                    help="overall brightness multiplier")
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
        return cfg_cache[0]
    aura = Aura(C, args.radius, args.strength, args.hue_seed,
                grow=args.grow, ascale=args.glow)
    F = aura.F
    buf = np.zeros((F, F), np.uint32)
    speed = [0.0]
    energy = [0.0]
    ripples = []                     # canvas-local (x-off, y-off, t0, s)
    last = [None]
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

    def poll_clicks(now):
        while click_q:
            ev = click_q.popleft()
            energy[0] = 1.0
            ripples.append((0.0, 0.0, now, 1.0))
            del ripples[:-4]

    pos_file = os.environ.get("AURA_POS_FILE")   # test seam: file has 'x y'

    def tick():
        now = time.monotonic()
        ac = cfg()
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
        last[0] = (x, y)
        ml = min(max(x - C // 2, 0), screen[0] - C)
        mt = min(max(y - C // 2, 0), screen[1] - C)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, ml)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, mt)
        poll_clicks(now)
        energy[0] *= 0.90
        live = [(rx, ry, now - t0, s) for (rx, ry, t0, s) in ripples
                if now - t0 < RIPPLE_LIFE]
        # live knobs from studio sliders
        aura.grow = float(ac.get("grow", args.grow))
        aura.ascale = float(ac.get("glow", args.glow))
        aura.R0 = float(ac.get("radius", args.radius))
        aura.strength = float(ac.get("strength", args.strength))
        aura.render(now - start, speed[0], energy[0], live, buf,
                    core=bool(ac.get("hide_arrow")))
        surf_box[0] = cairo.ImageSurface.create_for_data(
            buf.view(np.uint8), cairo.FORMAT_ARGB32, F, F)
        area.queue_draw()
        return True

    GLib.timeout_add(int(1000 / args.fps), tick)
    Gtk.main()


if __name__ == "__main__":
    main()
