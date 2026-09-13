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
from magic_core import (WiggleDetector, AuraMachine, StarField,
                        load_packs, decode_frames, load_config)

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
    def __init__(self, cfg, demo=None):
        self.cfg, self.demo = cfg, demo
        self.sock_path = hypr_socket_path()
        self.wig = WiggleDetector(**cfg["wiggle"])
        mo = cfg["motion"]
        prof = mo.get("profile", "auto")
        if prof == "auto":
            prof = _auto_profile()
        self.aura = AuraMachine(peak_scale=mo["peak_scale"],
                                start_scale=mo["start_scale"], profile=prof)
        self.stars = StarField(n=cfg.get("stars", {}).get("per_burst", 10),
                               seed=None)
        self._prev = time.perf_counter()
        self._demo_t = 0.0 if demo else None
        self.pixbufs, self.durations, self.total, self.pack_time = [], [], 0.0, 0.0
        self.sprite_on = False
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

    def show_emotion(self, name):
        for pack in self.all_emotions().values():
            spec = pack["emotions"].get(name)
            if spec and spec.get("type") == "gif":
                frames, dur = decode_frames(spec["path"])
                self.pixbufs = [GdkPixbuf.Pixbuf.new_from_data(
                    f.convert("RGBA").tobytes(), GdkPixbuf.Colorspace.RGB, True, 8,
                    f.width, f.height, f.width * 4) for f in frames]
                self.durations, self.total, self.pack_time = dur, float(sum(dur)), 0.0
                return True
        return False

    # main loop ---------------------------------------------------------------
    def tick(self):
        now = time.perf_counter()
        dt = min(now - self._prev, 0.05); self._prev = now
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
                self.stars.burst(now, self.cfg.get("stars", {}).get("per_burst", 10))
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
                    name = self.cfg["emotion"]
                    self.sprite_on = self.show_emotion(name)
                    if self.sprite_on:
                        self.aura._peak_heat = self.wig.heat
            # one star burst per reversal pulse while the detector is hot
            self._last_rev = getattr(self, "_last_rev", self.wig.rev_count)
            if self.wig.rev_count != self._last_rev:
                self.stars.burst(now, self.cfg.get("stars", {}).get("per_burst", 10))
                self._last_rev = self.wig.rev_count
            self.aura.update(now, self.wig.heat)
            if (self.aura.settled(now) and self.stars.count == 0
                    and self.sprite_on):
                self.sprite_on = False; self.pixbufs = []
        # surface exists only while something is visible (click-through guarantee)
        if (self.aura.alpha > 0.01 or self.stars.count) and not self.win.get_visible():
            self.win.show_all()
            self._fresh = True
        elif self.aura.alpha <= 0.01 and self.stars.count == 0 and self.win.get_visible():
            self.win.hide()
        if self.win.get_visible():
            if getattr(self, "_fresh", False):
                self._fresh = False
            self.position(pos)
            self.pack_time += dt if self.sprite_on else 0.0
            self.win.queue_draw()
        return True

    def position(self, pos):
        C = self.cfg["canvas_px"]
        ml = max(0, pos[0] - C // 2); mt = max(0, pos[1] - C // 2)
        GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.LEFT, ml)
        GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.TOP, mt)
        self.center = (pos[0] - ml, pos[1] - mt)

    # paint -----------------------------------------------------------------
    def draw(self, w, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR); cr.paint()
        C = self.cfg["canvas_px"]
        cx, cy = getattr(self, "center", (C / 2, C / 2))
        g = self.cfg["glow"]; col = g["color"]
        m, e = self.aura, self.aura.energy
        a = m.alpha
        if a > 0.003:
            es = (m.scale - m.start) / max(0.01, m.peak - m.start)
            cr.set_operator(cairo.OPERATOR_ADD)
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
            self._particles(cr, cx, cy, m, a, e)
            self._ring(cr, cx, cy, C, m, col)
        self._starlight(cr, cx, cy, m)
        return False

    def _draw_sprite(self, cr, cx, cy, C, m, a):
        t = self.pack_time % self.total if self.total else 0.0
        acc = 0.0; i = 0
        for i, d in enumerate(self.durations):
            acc += d
            if t < acc: break
        pb = self.pixbufs[min(i, len(self.pixbufs) - 1)]
        pw, ph = pb.get_width(), pb.get_height()
        size = C * 0.35 * m.scale
        fit = size / max(pw, ph)
        dw, dh = pw * fit, ph * fit
        cr.save(); cr.translate(cx, cy)
        cr.rotate(0.014 * math.sin(m.scale * 3.0))
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

    def _starlight(self, cr, cx, cy, m):
        """Starlight's signature: 4-point stars spreading out, spinning, twinkling."""
        t = time.perf_counter()
        st = self.cfg.get("stars", {})
        col = st.get("color", [1.0, 0.95, 0.75])
        cr.set_operator(cairo.OPERATOR_ADD)
        for (ang, r, size, rot, al) in self.stars.stars(t):
            x, y = cx + r * math.cos(ang), cy + r * math.sin(ang) * 0.85
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
    cfg = load_config(a[a.index("-c") + 1] if "-c" in a else None)
    Daemon(cfg, demo=demo)
    Gtk.main()

if __name__ == "__main__":
    main()
