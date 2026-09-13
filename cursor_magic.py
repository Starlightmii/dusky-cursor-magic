#!/usr/bin/env /usr/bin/python3
"""dusky-cursor-magic: wiggle the mouse -> an emotion bursts over the cursor in a
dreamy glow, breathes, fades away. Click-through; the real cursor is untouched.
Run: /usr/bin/python3 cursor_magic.py [--demo EMOTION] [-c config.json]"""
import gi, json, math, os, random, socket, subprocess, sys, time
import cairo
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0"); gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GdkPixbuf, GtkLayerShell, GLib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from magic_core import WiggleDetector, BurstMachine, load_packs, decode_frames, load_config

PACK_DIRS = [os.path.expanduser("~/.config/dusky/cursor-magic/packs"),
             os.path.join(os.path.dirname(os.path.abspath(__file__)), "packs")]

def _auto_profile():
    """motion.profile 'auto' -> reduced if the desktop disables animations."""
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
        self._prev = time.perf_counter()
        self.machine = None
        self.pixbufs, self.durations, self.total, self.pack_time = [], [], 0.0, 0.0
        self.build_window()
        self.apply_rules()
        GLib.timeout_add(cfg.get("tick_ms", 8), self.tick)

    # window ----------------------------------------------------------------
    def build_window(self):
        C = self.cfg["canvas_px"]
        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_app_paintable(True)
        self.win.set_size_request(C, C)
        GtkLayerShell.init_for_window(self.win)
        GtkLayerShell.set_layer(self.win, GtkLayerShell.Layer.OVERLAY)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.LEFT):
            GtkLayerShell.set_anchor(self.win, edge, True)
        GtkLayerShell.set_exclusive_zone(self.win, -1)
        # click-through client-side: empty input region (verified by gate test)
        def _pt(w):
            w.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
        self.win.connect("realize", _pt)
        self.win.connect("map", _pt)
        GtkLayerShell.set_namespace(self.win, "dusky-cursor-magic")
        self.win.connect("draw", self.draw)
        # stays hidden until a burst: no surface when idle => nothing can block clicks

    def apply_rules(self):
        # one layerrule per Hyprland session (no read API in 0.56.2; marker keyed
        # by instance signature — new session, new sig, rule re-added as needed)
        marker = os.path.expanduser(f"~/.cache/dusky-cursor-magic/rule-{os.path.basename(self.sock_path)}.ok")
        if os.path.exists(marker):
            return
        self.hypr('eval pcall(hl.layer_rule,{namespace="dusky-cursor-magic",'
                  'pass_mouse_through=true,blur=true,ignorezero=true,xray=true})')
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        open(marker, "w").write("1")

    def hypr(self, cmd):
        try:
            s = socket.socket(socket.AF_UNIX); s.connect(self.sock_path)
            s.sendall(cmd.encode()); d = s.recv(65536).decode(); s.close()
            return d
        except OSError:
            return ""

    def cursor(self):
        d = self.hypr("cursorpos")
        try:
            x, y = d.split(","); return int(x), int(y)
        except ValueError:
            return None

    # packs -----------------------------------------------------------------
    def all_emotions(self):
        out = {}
        for d in PACK_DIRS:
            for p in load_packs(d).values():
                out.update(p["emotions"])
        return out

    def show_emotion(self, name):
        emos = self.all_emotions()
        keys = sorted(emos)
        if not keys: return False
        if name in ("random", "", None):
            name = random.choice(keys)
        elif name not in emos:
            return False
        frames, dur = decode_frames(emos[name]["path"])
        self.pixbufs = [GdkPixbuf.Pixbuf.new_from_data(
            f.convert("RGBA").tobytes(), GdkPixbuf.Colorspace.RGB, True, 8,
            f.width, f.height, f.width * 4) for f in frames]
        self.durations, self.total, self.pack_time = dur, float(sum(dur)), 0.0
        return True

    # main loop ---------------------------------------------------------------
    def tick(self):
        pos = self.cursor()
        if pos is None: return True
        now = time.perf_counter()
        dt = min(now - self._prev, 0.05); self._prev = now
        if self.machine is None:
            fired = (self.demo is not None) or self.wig.feed(now, *pos)
            if fired:
                name = self.demo or self.cfg["emotion"]; self.demo = None
                if self.show_emotion(name):
                    mo = self.cfg.get("motion", {})
                    prof = mo.get("profile", "auto")
                    if prof == "auto":
                        prof = _auto_profile()
                    self.machine = BurstMachine(
                        self.cfg["hold_s"], self.cfg["enter_s"],
                        self.cfg["exit_s"], self.cfg["cooldown_s"],
                        peak_scale=mo.get("peak_scale", 1.8),
                        start_scale=mo.get("start_scale", 0.35),
                        profile=prof, ring=mo.get("ring", True),
                        breathe_sine=mo.get("breathe_sine", 1.0))
                    if self.machine.trigger(now):
                        self.position(pos); self.win.show_all()
                        # map handler re-applies empty input shape
                    else:
                        self.machine = None
        else:
            self.machine.update(now)
            self.pack_time += dt                      # real dt — fixes GIF stutter
            if self.machine.state == "idle":
                self.machine = None; self.pixbufs = []
                self.win.hide()   # unmap: surface gone until next wiggle
        if self.machine:
            self.position(pos); self.win.queue_draw()
        return True

    def position(self, pos):
        C = self.cfg["canvas_px"]
        ml = max(0, pos[0] - C // 2); mt = max(0, pos[1] - C // 2)
        GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.LEFT, ml)
        GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.TOP, mt)
        self.center = (pos[0] - ml, pos[1] - mt)   # sprite stays on cursor at edges

    # paint -----------------------------------------------------------------
    def draw(self, w, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR); cr.paint()
        m = self.machine
        if not m or not self.pixbufs or m.alpha <= 0.003: return False
        C = self.cfg["canvas_px"]; cx, cy = getattr(self, "center", (C/2, C/2))
        g = self.cfg["glow"]; col = g["color"]; a = m.alpha
        cr.set_operator(cairo.OPERATOR_ADD)
        es = m.scale / max(0.01, getattr(m, "_peak", 1.0))   # envelope 0..1 of peak
        R = g["outer_r"] * C * (0.45 + 0.55 * es)            # aura grows WITH the sprite
        gr = cairo.RadialGradient(cx, cy, 0, cx, cy, R)
        gr.add_color_stop_rgba(0.00, *col, g["soft_alpha"] * a)
        gr.add_color_stop_rgba(0.45, *col, g["soft_alpha"] * 0.5 * a)
        gr.add_color_stop_rgba(0.80, *col, g["soft_alpha"] * 0.12 * a)
        gr.add_color_stop_rgba(1.00, *col, 0.0)
        cr.set_source(gr); cr.paint()
        r2 = 0.30 * C * (0.45 + 0.55 * es)
        gr2 = cairo.RadialGradient(cx, cy, 0, cx, cy, r2)
        gr2.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, g["inner_alpha"] * 0.7 * a)
        gr2.add_color_stop_rgba(1.0, *col, 0.0)
        cr.set_source(gr2); cr.paint()
        if m.ring_alpha > 0.01:                              # KDE-style enter ring
            cr.set_source_rgba(*col, m.ring_alpha)
            cr.set_line_width(3.0 * (1.0 - m.ring / 1.2) + 1.0)
            cr.arc(cx, cy, m.ring * C * 0.5, 0, 2 * math.tau)
            cr.stroke()
        # sprite frame at GIF-native cadence
        t = self.pack_time % self.total if self.total else 0.0
        acc = 0.0; i = 0
        for i, d in enumerate(self.durations):
            acc += d
            if t < acc: break
        pb = self.pixbufs[min(i, len(self.pixbufs) - 1)]
        pw, ph = pb.get_width(), pb.get_height()
        size = C * 0.35 * m.scale                     # start~63px (cursor-sized) -> peak~322px, fits canvas
        fit = size / max(pw, ph)
        dw, dh = pw * fit, ph * fit
        cr.save(); cr.translate(cx, cy); cr.rotate(m.rot)
        # bloom: cheap 4x downscale-upscale of the sprite, additive
        bp = pb.scale_simple(max(1, pw // 4), max(1, ph // 4), GdkPixbuf.InterpType.BILINEAR) \
             .scale_simple(max(1, int(dw / 4)), max(1, int(dh / 4)), GdkPixbuf.InterpType.NEAREST)
        Gdk.cairo_set_source_pixbuf(cr, bp, -dw / 2, -dh / 2)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint_with_alpha(g["bloom_alpha"] * a)
        # sprite
        Gdk.cairo_set_source_pixbuf(cr, pb, -dw / 2, -dh / 2)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(a)
        cr.restore()
        self._particles(cr, cx, cy, m.age, a)
        return False

    def _particles(self, cr, cx, cy, t, a):
        n = self.cfg.get("sparkles", 8)
        m = self.machine
        es = (m.scale / max(0.01, getattr(m, "_peak", 1.0))) if m else 1.0
        for i in range(n):
            ang = t * 0.6 + i * math.tau / n
            r = (150 + 30 * math.sin(t * 1.1 + i * 2.1)) * (0.5 + 0.5 * es)
            px, py = cx + r * math.cos(ang), cy + r * math.sin(ang) * 0.72 - 20 * math.sin(t + i)
            tw = 0.5 + 0.5 * math.sin(t * 3.0 + i * 1.7)
            s = 1.8 + 2.0 * tw
            cr.set_source_rgba(1.0, 0.93, 0.99, a * (0.20 + 0.5 * tw))
            cr.arc(px, py, s, 0, 2 * math.tau); cr.fill()
            cr.set_source_rgba(1.0, 1.0, 1.0, a * 0.8 * tw)
            cr.arc(px, py, s * 0.35, 0, 2 * math.tau); cr.fill()

def main():
    a = sys.argv[1:]
    demo = a[a.index("--demo") + 1] if "--demo" in a and a.index("--demo") + 1 < len(a) else ("random" if "--demo" in a else None)
    cfg = load_config(a[a.index("-c") + 1] if "-c" in a else None)
    Daemon(cfg, demo=demo)
    Gtk.main()

if __name__ == "__main__":
    main()
