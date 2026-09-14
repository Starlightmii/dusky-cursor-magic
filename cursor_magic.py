#!/usr/bin/env /usr/bin/python3
"""dusky-cursor-magic: an AURA that tracks your mouse like macOS — shake
faster, it grows; calm down, it melts away. Starlight signature: every
reversal throws a burst of spreading stars. Past the intent threshold the
anime girl materialises inside the glow. Click-through; real cursor untouched.
Run: /usr/bin/python3 cursor_magic.py [--demo girl] [-c config.json]"""
import gi, json, math, os, random, socket, subprocess, sys, time
import cairo
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0"); gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GdkPixbuf, GtkLayerShell, GLib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from magic_core import (WiggleDetector, AuraMachine, StarField, SpeedEstimator,
                        frame_index, load_packs, decode_frames, load_config)

PACK_DIRS = [os.path.expanduser("~/.config/dusky/cursor-magic/packs"),
             os.path.join(os.path.dirname(os.path.abspath(__file__)), "packs")]

def _auto_profile():
    try:
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface",
                              "enable-animations"], capture_output=True,
                             text=True, timeout=1).stdout
        if out.strip() == "false":
            return "reduced"
    except Exception:
        pass
    return "macos"

def hypr_socket_path():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    for base in (f"/run/user/{os.getuid()}/hypr/{sig}", f"/tmp/hypr/{sig}"):
        p = base + "/.socket.sock"
        if os.path.exists(p):
            return p
    sys.exit("no hyprland socket — run inside Hyprland")

class Daemon:
    def __init__(self, cfg, demo=None, cfg_path=None):
        self.cfg, self.demo = cfg, demo
        self.cfg_path = cfg_path
        self._cfg_mtime = 0.0
        self.sock_path = hypr_socket_path()
        self.wig = WiggleDetector(**cfg["wiggle"])
        mo = cfg["motion"]
        prof = mo.get("profile", "auto")
        if prof == "auto":
            prof = _auto_profile()
        self.aura = AuraMachine(peak_scale=mo["peak_scale"],
                                start_scale=mo["start_scale"], profile=prof)
        self._reduced = prof == "reduced"
        self.stars = StarField(n=cfg.get("stars", {}).get("per_burst", 10),
                               seed=None)
        self._prev = time.perf_counter()
        self.speed_est = SpeedEstimator(window_s=0.05)   # U5: ambient breath
        self._sm = None                                  # U4: smoothed glow center
        self._last_alive = time.perf_counter()           # U8: idle shimmer clock
        self._demo_t = 0.0 if demo else None
        self.pixbufs, self.durations, self.total, self.pack_t0 = [], [], 0.0, 0.0
        self.sprite_on = False
        self.click_fx = []            # (t0, big)  -> ripple + star pop
        self.trail = []               # (t, x, y)  fading comet behind aura
        try:
            from clicks import ClickWatcher
            self.clicks = ClickWatcher()
            self.clicks.start(self._on_click)
        except Exception:
            self.clicks = None
        self.build_window()
        self.apply_rules()
        GLib.timeout_add(cfg.get("tick_ms", 8), self.tick)

    # window ----------------------------------------------------------------
    def build_window(self):
        C = self.cfg["canvas_px"]
        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_size_request(C, C)
        self.win.set_app_paintable(True)
        self.win.set_visual(self.win.get_screen().get_rgba_visual())
        GtkLayerShell.init_for_window(self.win)
        GtkLayerShell.set_layer(self.win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self.win, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self.win, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_exclusive_zone(self.win, -1)
        GtkLayerShell.set_keyboard_mode(self.win, GtkLayerShell.KeyboardMode.NONE)
        def _pt(w):
            w.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
        self.win.connect("realize", _pt)
        self.win.connect("map", _pt)
        GtkLayerShell.set_namespace(self.win, "dusky-cursor-magic")
        self.win.connect("draw", self.draw)
        # stays hidden until heat > 0: no surface idle => nothing blocks clicks

    def apply_rules(self):
        marker = os.path.expanduser(f"~/.cache/dusky-cursor-magic/rule-{os.path.basename(self.sock_path)}.ok")
        if os.path.exists(marker):
            return
        self.hypr('eval pcall(hl.layer_rule,{namespace="dusky-cursor-magic",'
                  'pass_mouse_through=true,blur=true,ignorezero=true,xray=true})')
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        open(marker, "w").write("1")

    def hypr(self, cmd):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(self.sock_path); s.sendall(("[bash]" + cmd).encode())
            s.recv(4096); s.close()
        except Exception:
            pass

    def cursor(self):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(self.sock_path); s.sendall(b"cursorpos")
            x, y = s.recv(64).decode().strip().split(",")
            s.close(); return int(x), int(y)
        except Exception:
            return None

    # sprite ----------------------------------------------------------------
    def all_emotions(self):
        out = {}
        for d in PACK_DIRS:
            out.update({k: v for k, v in load_packs(d).items()})
        return out

    def _pixbufs(self, frames, durs):
        self.pixbufs = [GdkPixbuf.Pixbuf.new_from_data(
            f.convert("RGBA").tobytes(), GdkPixbuf.Colorspace.RGB, True, 8,
            f.width, f.height, f.width * 4) for f in frames]
        self.durations, self.total = durs, float(sum(durs))
        self.pack_t0 = time.monotonic()

    def show_emotion(self, name, pack_name=None):
        for pname, pack in self.all_emotions().items():
            if pack_name and pname != pack_name:
                continue
            spec = pack["emotions"].get(name)
            if not spec:
                continue
            t = spec.get("type", "gif")
            try:
                if t == "seq":                      # turntable PNG frames
                    d = spec["path"]
                    files = sorted(f for f in os.listdir(d)
                                   if f.lower().endswith((".png", ".webp")))
                    if not files:
                        continue
                    pb = [GdkPixbuf.Pixbuf.new_from_file(os.path.join(d, fn))
                          for fn in files]
                    self.pixbufs = pb
                    fps = spec.get("fps", 24)
                    self.durations = [1.0 / fps] * len(pb)
                    self.total = len(pb) / fps
                    self.pack_t0 = time.monotonic()
                    return True
                frames, dur = decode_frames(spec["path"])   # gif OR single png
                if frames:
                    self._pixbufs(frames, [max(0.02, d) for d in dur])
                    return True
            except Exception:
                continue
        return False

    # clicks ------------------------------------------------------------------
    def _on_click(self, ev):           # worker thread -> queue, drained in tick
        self._click_q = getattr(self, "_click_q", __import__("collections").deque())
        self._click_q.append(ev)

    def _drain_clicks(self, now):
        q = getattr(self, "_click_q", None)
        while q:
            try:
                ev = q.popleft()
            except IndexError:
                break
            if ev["kind"] == "press":
                self.click_fx.append((now, ev.get("dbl", False), "click"))
                self._last_alive = now          # any click counts as alive (U8)
                # Cycle-2: remember the press anchor so tick can measure drag
                if ev.get("button", "left") == "left":
                    ax, ay = getattr(self, "_p_last", (None, None))
                    self._press = {"x": ax, "y": ay, "moved": 0.0} \
                        if ax is not None else None
                if self.cfg.get("clicks", {}).get("stars", True):
                    self._star_burst(now, 6 if not ev.get("dbl") else 14)
            elif ev["kind"] == "release" and ev.get("button") == "left":
                # Cycle-2: a held press that travelled = drag -> wake ripple
                pr = getattr(self, "_press", None)
                if pr and pr.get("moved", 0.0) > 12.0:
                    self.click_fx.append((now, False, "drag"))
                self._press = None

    def _star_burst(self, now, n, size=1.0):
        if not self._reduced and self.cfg.get("stars", {}).get("enabled", True):
            # U2: count answers energy too — gentle flick sprinkles, wild shake
            # throws fireworks (leaky energy after U1, so melts cool down)
            e = self.aura.energy
            self.stars.burst(now, int(n * (0.5 + 0.8 * e)), size)

    # main loop ---------------------------------------------------------------
    def hot_reload(self):
        """Config file is the IPC: ctl window writes, we mtime-poll at ~4Hz."""
        if not self.cfg_path:
            return
        try:
            mt = os.stat(self.cfg_path).st_mtime
        except OSError:
            return
        if mt == self._cfg_mtime:
            return
        self._cfg_mtime = mt
        old = self.cfg
        self.cfg = load_config(self.cfg_path)
        self.disabled = self.cfg.get("disabled", False)
        if self.cfg.get("wiggle") != old.get("wiggle"):
            self.wig = WiggleDetector(**self.cfg["wiggle"])
        mo = self.cfg["motion"]
        if mo != old.get("motion"):
            prof = mo.get("profile", "macos")
            if prof == "auto":
                prof = _auto_profile()
            self._reduced = prof == "reduced"
            self.aura = AuraMachine(peak_scale=mo["peak_scale"],
                                    start_scale=mo["start_scale"],
                                    profile=prof)
        if self.disabled and self.win.get_visible():
            self.win.hide()

    def tick(self):
        now = time.perf_counter()
        dt = min(now - self._prev, 0.05); self._prev = now
        self.hot_reload()
        self._drain_clicks(now)
        if getattr(self, "disabled", False):
            if self.win.get_visible():
                self.win.hide()
            return True
        if self._demo_t is not None:
            # synthetic shake: ~9s worth of wiggle compressed into 1s, then calm
            self._demo_t += dt
            u = self._demo_t
            heat = math.sin(min(u, 0.7) / 0.7 * math.pi / 2) if u < 0.7 else \
                   max(0.0, math.exp(-(u - 0.7) / 0.55))
            if self.sprite_on and heat <= 0.02:
                self.sprite_on = False; self.pixbufs = []
            if not self.sprite_on and heat > 0.6:
                self.sprite_on = True
                self.show_emotion(self.demo or self.cfg["emotion"])
            if int(u / 0.10) != int((u - dt) / 0.10) and u < 0.7:
                self._star_burst(now, self.cfg.get("stars", {}).get("per_burst", 10))
            if u > 2.2:
                self._demo_t = None
            self.aura.update(now, heat)
            pos = (self.cfg["canvas_px"] // 2 + 400,
                   self.cfg["canvas_px"] // 2 + 200)
        else:
            pos = self.cursor()
            if pos is None:
                return True
            fired = self.wig.feed(now, *pos)
            if fired:
                if not self.sprite_on:
                    self.sprite_on = self.show_emotion(
                        self.cfg["emotion"], self.cfg.get("sprite_pack") or None)
                    if self.sprite_on:
                        self.aura._peak_heat = self.wig.heat
            # U5: ambient whisper — feed the (until-now unused) SpeedEstimator;
            # ordinary glide speed lifts the aura to a faint breath, never near
            # arm_heat, so no sprite / false shake trigger
            sp = self.speed_est.feed(now, pos[0], pos[1])
            am = self.cfg.get("ambient", {})
            amb = 0.0
            if am.get("on", True) and not self._reduced:
                amb = max(0.0, min(1.0, (sp - am.get("min_speed", 150.0)) /
                                   am.get("speed_range", 900.0))) \
                      * am.get("max_gain", 0.35)
            # U7 comet trail: 0.35s window; stop feeding when parked so the
            # tail dissolves on stop instead of freezing into a ribbon
            if self.aura.alpha > 0.02 and sp > 60.0:
                self.trail.append((now, pos[0], pos[1]))
            while self.trail and now - self.trail[0][0] > 0.35:
                self.trail.pop(0)
            del self.click_fx[:max(0, len(self.click_fx) - 8)]
            self.click_fx = [c for c in self.click_fx if now - c[0] < 0.75]
            # one star burst per reversal pulse while the detector is hot
            self._last_rev = getattr(self, "_last_rev", self.wig.rev_count)
            if self.wig.rev_count != self._last_rev:
                # ponytail: burst size answers the shake's violence (heat)
                self._star_burst(now, self.cfg.get("stars", {}).get("per_burst", 10),
                                 size=0.6 + 0.8 * self.wig.heat)
                self._last_rev = self.wig.rev_count
            # velocity for squash-stretch: px/s between last two cursor samples
            if getattr(self, "_p_last", None) is not None and dt > 1e-4:
                vx = (pos[0] - self._p_last[0]) / dt
                vy = (pos[1] - self._p_last[1]) / dt
                self._vel = (math.hypot(vx, vy), math.atan2(vy, vx))
            self._p_last = pos
            # Cycle-2: live drag distance while a press is held
            pr = getattr(self, "_press", None)
            if pr and pr.get("x") is not None:
                pr["moved"] = max(pr["moved"],
                                  math.hypot(pos[0] - pr["x"], pos[1] - pr["y"]))
            self.aura.update(now, self.wig.heat, amb)
            # U4: smoothed glow center — dt-correct 35ms follower kills the
            # flick strobe; raw pos stays the anchor for clicks/star bursts
            a4 = 1.0 - math.exp(-dt / 0.035)
            sx, sy = self._sm if self._sm else pos
            self._sm = (sx + (pos[0] - sx) * a4, sy + (pos[1] - sy) * a4)
            # alive: real motion pushes back the idle-shimmer clock (U8)
            if sp > 60.0:
                self._last_alive = now
            if (self.aura.settled(now) and self.stars.count == 0
                    and self.sprite_on):
                self.sprite_on = False; self.pixbufs = []
        # U8: idle shimmer — faint starlight orbit while the cursor rests
        # (2s after last motion/click, auto-suspended after 10s)
        am = self.cfg.get("ambient", {})
        idle = (am.get("idle_shimmer", True) and not self._reduced
                and self._demo_t is None and 2.0 < now - self._last_alive < 10.0)
        self._idle = idle
        # surface exists only while something is visible (click-through guarantee)
        if (self.aura.alpha > 0.01 or self.stars.count or self.click_fx
                or idle) and not self.win.get_visible():
            self.win.show_all()
            self._fresh = True
        elif (self.aura.alpha <= 0.01 and self.stars.count == 0
              and not self.click_fx and not idle and self.win.get_visible()):
            self.win.hide()
        if self.win.get_visible():
            if getattr(self, "_fresh", False):
                self._fresh = False
            self.position(pos)
            self.win.queue_draw()
        return True

    def position(self, pos):
        C = self.cfg["canvas_px"]
        # U4: the glow rides the 35ms-smoothed follower (set in tick); raw
        # pos stays the anchor for click ripples and star bursts
        sx, sy = self._sm if self._sm else pos
        ml = max(0, int(sx) - C // 2); mt = max(0, int(sy) - C // 2)
        self._o = (ml, mt)
        GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.LEFT, ml)
        GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.TOP, mt)
        self.center = (sx - ml, sy - mt)
        self._anchor = (pos[0] - ml, pos[1] - mt)

    # paint -----------------------------------------------------------------
    def draw(self, w, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR); cr.paint()
        C = self.cfg["canvas_px"]
        cx, cy = getattr(self, "center", (C / 2, C / 2))
        g = self.cfg["glow"]; col = g["color"]
        m, e = self.aura, self.aura.energy
        a = m.alpha
        if a > 0.003 or self.stars.count or self.click_fx:
            self._comet(cr)
            self._click_ripples(cr)
        elif getattr(self, "_idle", False):
            self._shimmer(cr)                      # U8: alive even at rest
        if a > 0.003:
            es = (m.scale - m.start) / max(0.01, m.peak - m.start)
            cr.set_operator(cairo.OPERATOR_ADD)
            # Cycle-2: aura hue follows heat — calm blue-calm to warm at full shake
            col = self._tint()
            # ponytail: velocity squash-stretch — aura elongates along motion.
            # strength 0.18@3kpx/s, square-root area preserve; drop when idle.
            vsp, vang = getattr(self, "_vel", (0.0, 0.0))
            sq = 1 + 0.18 * min(1.0, vsp / 3000.0) if not self._reduced else 1.0
            if sq != 1.0:
                cr.save()
                cr.translate(cx, cy); cr.rotate(vang)
                cr.scale(sq, 1.0 / math.sqrt(sq)); cr.translate(-cx, -cy)
            # living aura: breathes with the spring (es) — always on while hot
            R = g["outer_r"] * C * (0.45 + 0.55 * es) * (0.6 + 0.4 * e)
            gr = cairo.RadialGradient(cx, cy, 0, cx, cy, R)
            gr.add_color_stop_rgba(0.00, *col, g["soft_alpha"] * a * (0.6 + 0.4 * e))
            gr.add_color_stop_rgba(0.45, *col, g["soft_alpha"] * 0.5 * a)
            gr.add_color_stop_rgba(0.80, *col, g["soft_alpha"] * 0.12 * a)
            gr.add_color_stop_rgba(1.00, *col, 0.0)
            cr.set_source(gr); cr.paint()
            r2 = 0.30 * C * (0.45 + 0.55 * es)
            gr2 = cairo.RadialGradient(cx, cy, 0, cx, cy, r2)
            gr2.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, g["inner_alpha"] * 0.7 * a)
            gr2.add_color_stop_rgba(1.0, *col, 0.0)
            cr.set_source(gr2); cr.paint()
            if self.sprite_on and self.pixbufs:
                self._draw_sprite(cr, cx, cy, C, m, a)
            if sq != 1.0:
                cr.restore()          # ponytail: end squash-stretch xform
            self._particles(cr, cx, cy, m, a, e)
            self._ring(cr, cx, cy, C, m, col)
        self._starlight(cr, cx, cy, m)
        return False

    def _comet(self, cr):
        """Tapered starlit comet — fat bright head, thin dark tip, dissolves
        ~350ms after you stop (never a frozen ribbon)."""
        if not self.cfg.get("aura", {}).get("trail", True):
            return
        if len(self.trail) < 2:
            return
        ox, oy = getattr(self, "_o", (0, 0))
        now = time.perf_counter()
        col = self.cfg.get("stars", {}).get("color", [1.0, 0.95, 0.75])
        cr.set_operator(cairo.OPERATOR_ADD)
        # U7: head width answers live speed (not stale energy)
        vsp = getattr(self, "_vel", (0.0, 0.0))[0]
        head_w = 3.0 + 5.0 * min(1.0, vsp / 4000.0)
        prev = None
        for (t, x, y) in self.trail:
            life = 1.0 - (now - t) / 0.35
            if life <= 0 or prev is None:
                prev = (x - ox, y - oy); continue
            px, py = x - ox, y - oy
            cr.set_line_width(max(0.5, head_w * life ** 1.5))
            cr.set_source_rgba(*col, 0.16 * life ** 2 * self.aura.alpha)
            cr.move_to(*prev); cr.line_to(px, py); cr.stroke()
            prev = (px, py)

    def _tint(self):
        """Cycle-2: lerp the glow color toward warm as heat/energy rises —
        the aura reads calm-cool at rest, candle-warm in a violent shake.
        getattr-tolerant: visual-proxy tests build Daemon without .wig."""
        g = self.cfg["glow"]
        col = g["color"]
        wc = g.get("warm_color", [1.0, 0.72, 0.42])   # candle-warm fallback
        wig = getattr(self, "wig", None)
        heat = wig.heat if wig is not None else 0.0
        k = min(1.0, 0.55 * heat + 0.45 * self.aura.energy)
        return tuple(c + (w - c) * k for c, w in zip(col, wc))

    def _click_ripples(self, cr):
        """Click = springy sonar ripple (easeOutBack) at the raw press point."""
        if not self.click_fx:
            return
        now = time.perf_counter()
        col = self.cfg["glow"]["color"]
        C = self.cfg["canvas_px"]
        cr.set_operator(cairo.OPERATOR_ADD)
        for fx in self.click_fx:
            # 2-tuples (pre cycle-2) render as clicks
            t0, dbl, kind = fx if len(fx) == 3 else (fx[0], fx[1], "click")
            age = now - t0
            if age > 0.75:
                continue
            u = min(1.0, age / 0.45)               # U6: 600 -> 450 ms
            ax, ay = getattr(self, "_anchor", self.center)
            if kind == "drag":
                # wake: slower wider softer ring — release of a held drag
                uu = min(1.0, age / 0.7)
                e = 1.0 - (1.0 - uu) ** 3         # easeOutCubic glide
                r = (0.05 + 0.50 * e) * C
                cr.set_line_width(3.5 * (1.0 - uu) + 0.5)
                cr.set_source_rgba(*self._tint(), (1.0 - uu) ** 2 * 0.40)
                cr.arc(ax, ay, r, 0, 2 * math.tau)
                cr.stroke()
                continue
            for k in range(2 if dbl else 1):
                uu = max(0.0, u - k * 0.12)
                if uu <= 0:
                    continue
                b = 1.70158                        # easeOutBack: launch fast,
                e = 1 + (b + 1) * (uu - 1) ** 3 + b * (uu - 1) ** 2  # ~10% boing
                r = min((0.02 + 0.45 * e) * C, 0.47 * C) * (0.8 if k else 1.0)
                cr.set_line_width(2.5 * (1.0 - uu) + 0.5)
                cr.set_source_rgba(*col, (1.0 - uu) ** 1.6 * 0.55)
                cr.arc(ax, ay, r, 0, 2 * math.tau)
                cr.stroke()

    def _draw_sprite(self, cr, cx, cy, C, m, a):
        sp = self.cfg.get("sprite", {})
        now = time.monotonic()
        t = now - self.pack_t0
        if self.total:
            t = t % self.total if sp.get("frame_loop", True) \
                else min(t, self.total - 1e-3)   # one-shot: hold last frame
        pb = self.pixbufs[frame_index(self.durations, t)
                          if self.durations else 0]
        pw, ph = pb.get_width(), pb.get_height()
        size = C * 0.35 * m.scale * sp.get("size", 1.0)
        e = m.energy
        if not self._reduced and sp.get("bob", True):
            size *= 1.0 + 0.03 * math.sin(now * (1.6 + 2.4 * e))
        fit = size / max(pw, ph)
        dw, dh = pw * fit, ph * fit
        cr.save(); cr.translate(cx, cy)
        if not self._reduced and sp.get("spin", True):
            cr.rotate(math.radians(2.0) * math.sin(now * (0.35 + 0.5 * e)))
        bp = pb.scale_simple(max(1, pw // 4), max(1, ph // 4), GdkPixbuf.InterpType.BILINEAR) \
             .scale_simple(max(1, int(dw / 4)), max(1, int(dh / 4)), GdkPixbuf.InterpType.NEAREST)
        Gdk.cairo_set_source_pixbuf(cr, bp, -dw / 2, -dh / 2)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint_with_alpha(self.cfg["glow"]["bloom_alpha"] * a)
        Gdk.cairo_set_source_pixbuf(cr, pb, -dw / 2, -dh / 2)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(a)
        cr.restore()

    def _particles(self, cr, cx, cy, m, a, e):
        n = self.cfg.get("sparkles", 8)
        es = (m.scale - m.start) / max(0.01, m.peak - m.start)
        t = time.perf_counter()
        for i in range(n):
            ang = t * 0.6 + i * math.tau / n
            r = (150 + 30 * math.sin(t * 1.1 + i * 2.1)) * (0.5 + 0.5 * es)
            px, py = cx + r * math.cos(ang), cy + r * math.sin(ang) * 0.72 - 20 * math.sin(t + i)
            tw = 0.5 + 0.5 * math.sin(t * 3.0 + i * 1.7)
            s = (1.8 + 2.0 * tw) * (0.7 + 0.6 * e)
            cr.set_source_rgba(1.0, 0.93, 0.99, a * (0.20 + 0.5 * tw) * (0.5 + 0.5 * e))
            cr.arc(px, py, s, 0, 2 * math.tau); cr.fill()
            cr.set_source_rgba(1.0, 1.0, 1.0, a * 0.8 * tw)
            cr.arc(px, py, s * 0.35, 0, 2 * math.tau); cr.fill()

    def _ring(self, cr, cx, cy, C, m, col):
        # pulse ring every time the aura crosses ~peak energy in a shake
        es = (m.scale - m.start) / max(0.01, m.peak - m.start)
        if es > 0.92 and m.energy > 0.8:
            if getattr(self, "_ring_at", 0) < time.perf_counter() - 0.6:
                self._ring_at = time.perf_counter()
            age = time.perf_counter() - self._ring_at
            if age < 0.5:
                u = age / 0.5
                cr.set_source_rgba(*col, (1.0 - u) * 0.5)
                cr.set_line_width(3.0 * (1.0 - u) + 1.0)
                cr.arc(cx, cy, (0.25 + 0.75 * u) * C * 0.5, 0, 2 * math.tau)
                cr.stroke()

    def _shimmer(self, cr):
        """U8: idle shimmer — 3 tiny stars in a slow orbit, breathing at
        whisper alpha (3-5%) around the resting cursor. Never fights the
        pointer for attention; real effects take over on any motion."""
        t = time.perf_counter()
        ax, ay = getattr(self, "_anchor", self.center)
        col = self.cfg.get("stars", {}).get("color", [1.0, 0.95, 0.75])
        cr.set_operator(cairo.OPERATOR_ADD)
        for i in range(3):
            ang = t * 0.05 * math.tau + i * (math.tau / 3)
            r = 26.0 + 4.0 * math.sin(t * 0.6 + i * 2.1)
            x, y = ax + r * math.cos(ang), ay + r * math.sin(ang)
            breathe = 0.5 + 0.5 * math.sin(t * 0.6)
            cr.set_source_rgba(*col, 0.035 * breathe)
            cr.arc(x, y, 1.6 + 0.6 * breathe, 0, math.tau)
            cr.fill()

    def _starlight(self, cr, cx, cy, m):
        """Starlight's signature: 4-point stars spreading out, spinning, twinkling.
        Anchored at the raw cursor sample — bursts come FROM where you flicked,
        not from the smoothed follower (U4)."""
        t = time.perf_counter()
        st = self.cfg.get("stars", {})
        col = st.get("color", [1.0, 0.95, 0.75])
        ax, ay = getattr(self, "_anchor", (cx, cy))
        cr.set_operator(cairo.OPERATOR_ADD)
        for (ang, r, size, rot, al) in self.stars.stars(t):
            x, y = ax + r * math.cos(ang), ay + r * math.sin(ang) * 0.85
            cr.save(); cr.translate(x, y); cr.rotate(rot)
            # 4-point star: outer tips at size, inner waist at size*0.38
            pts = []
            for k in range(8):
                rr = size if k % 2 == 0 else size * 0.38
                th = k * math.pi / 4
                pts.append((rr * math.cos(th), rr * math.sin(th)))
            cr.move_to(*pts[0])
            for p in pts[1:]:
                cr.line_to(*p)
            cr.close_path()
            cr.set_source_rgba(*col, al)
            cr.fill()
            # hot core
            cr.arc(0, 0, size * 0.28, 0, 2 * math.tau)
            cr.set_source_rgba(1, 1, 1, al * 0.9)
            cr.fill()
            cr.restore()

def main():
    a = sys.argv[1:]
    demo = a[a.index("--demo") + 1] if "--demo" in a and a.index("--demo") + 1 < len(a) else ("random" if "--demo" in a else None)
    cp = a[a.index("-c") + 1] if "-c" in a else os.path.expanduser(
        "~/.config/dusky/cursor-magic/config.json")
    cfg = load_config(cp)
    Daemon(cfg, demo=demo, cfg_path=cp)
    Gtk.main()

if __name__ == "__main__":
    main()
