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
               hot=(0.0, 0.0), vel=(0.0, 0.0), trail=(0.0, 0.0)):
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

    aura = Aura(C, args.radius, args.strength, args.hue_seed,
                grow=args.grow, ascale=args.glow)
    F = aura.F
    buf = np.zeros((F, F), np.uint32)
    speed = [0.0]
    energy = [0.0]
    vel = [(0.0, 0.0)]                # smoothed per-frame pointer delta
    ripples = []                     # canvas-local (x-off, y-off, t0, s)
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

    def poll_clicks(now):
        while click_q:
            ev = click_q.popleft()
            energy[0] = 1.0
            ripples.append((hot_st[0] / Aura.SCALE, hot_st[1] / Aura.SCALE,
                            now, 1.0))
            del ripples[:-4]

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
        hot_st[0], hot_st[1] = hot
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, ml)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, mt)
        poll_clicks(now)
        energy[0] *= 0.90
        live = [(rx, ry, now - t0, s) for (rx, ry, t0, s) in ripples
                if now - t0 < RIPPLE_LIFE]
        # idle budget: pointer still + nothing decaying -> 30fps is plenty
        # (the 2.6rad/s breath samples fine at half rate; 2x less CPU)
        moved = last[1] != (x, y) or hot != last[2]
        active = moved or speed[0] > 0.01 or energy[0] > 0.02 or live
        if not active and now - last[3] < 1.0 / 30.0:
            return True
        last[3] = now
        last[1], last[2] = (x, y), hot
        # live knobs from studio sliders
        aura.grow = float(ac.get("grow", args.grow))
        aura.ascale = float(ac.get("glow", args.glow))
        aura.R0 = float(ac.get("radius", args.radius))
        aura.strength = float(ac.get("strength", args.strength))
        aura.render(now - start, speed[0], energy[0], live, buf,
                    core=bool(ac.get("hide_arrow")), hot=hot, vel=vel[0],
                    trail=trail_hot)
        surf_box[0] = cairo.ImageSurface.create_for_data(
            buf.view(np.uint8), cairo.FORMAT_ARGB32, F, F)
        area.queue_draw()
        return True

    GLib.timeout_add(int(1000 / args.fps), tick)
    Gtk.main()


if __name__ == "__main__":
    main()
