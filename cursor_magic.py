#!/usr/bin/env /usr/bin/python3
"""dusky-cursor-magic: flick the mouse -> an emotion bursts over the cursor in a
glass glow, wobbles, shrinks away. Click-through; the real cursor is untouched.
Run: /usr/bin/python3 cursor_magic.py [--demo EMOTION] [-c config.json]"""
import gi, json, math, os, random, socket, sys, time
import cairo
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0"); gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GdkPixbuf, GtkLayerShell, GLib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from magic_core import SpeedEstimator, BurstMachine, load_packs, decode_frames, load_config

PACK_DIRS = [os.path.expanduser("~/.config/dusky/cursor-magic/packs"),
             os.path.join(os.path.dirname(os.path.abspath(__file__)), "packs")]

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
        self.est = SpeedEstimator()
        self.machine = None
        self.pixbufs, self.durations, self.total, self.pack_time = [], [], 0.0, 0.0
        self.build_window()
        self.rule(True)
        GLib.timeout_add(16, self.tick)

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

    def rule(self, on):
        # click-through compositor-side, belt & braces (Hyprland 0.56 Lua rule)
        self.hypr(f'eval pcall(hl.layer_rule,{{namespace="dusky-cursor-magic",'
                  f'pass_mouse_through={"true" if on else "false"}}})')

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
        if self.machine is None:
            if self.demo is not None:
                if self.show_emotion(self.demo):
                    self.start(pos, now)
                self.demo = None
            elif self.est.feed(now, *pos) >= self.cfg["threshold"]:
                if self.show_emotion(self.cfg["emotion"]):
                    self.start(pos, now)
        else:
            self.machine.update(now, self.est.speed(now))
            self.pack_time += 0.016
            if self.machine.state == "idle":
                self.machine = None; self.pixbufs = []
                self.win.hide()   # unmap: surface gone until next flick
        if self.machine:
            self.position(pos)
            self.win.queue_draw()
        return True

    def start(self, pos, now):
        c = self.cfg
        self.machine = BurstMachine(c["threshold"], c["hold_s"], c["shrink_s"],
                                    c["cooldown_s"], c["peak_scale"])
        self.machine.trigger(now, *pos)
        self.position(pos)
        self.win.show_all()   # map now; "map" handler re-applies empty input shape

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
        if not m or not self.pixbufs: return False
        e = m.envelope
        if e <= 0.02: return False
        C = self.cfg["canvas_px"]; cx, cy = getattr(self, "center", (C/2, C/2))
        g = self.cfg["glass"]; col = g["color"]
        fr = min(e * C / 2 * 0.9, C / 2 - 4)
        # frosted halo (real blur behind comes from the layerrule below)
        grad = cairo.RadialGradient(cx, cy, fr * 0.25, cx, cy, fr * 1.35)
        grad.add_color_stop_rgba(0.0, *col, g["alpha"] * e)
        grad.add_color_stop_rgba(0.75, *col, g["alpha"] * 0.35 * e)
        grad.add_color_stop_rgba(1.0, *col, 0.0)
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source(grad); cr.arc(cx, cy, fr * 1.35, 0, 2 * math.tau); cr.fill()
        # sprite frame, spring-scaled and wobbled
        t = self.pack_time % self.total if self.total else 0.0
        acc = 0.0; i = 0
        for i, d in enumerate(self.durations):
            acc += d
            if t < acc: break
        pb = self.pixbufs[min(i, len(self.pixbufs) - 1)]
        pw, ph = pb.get_width(), pb.get_height()
        size = min(C * 0.5 * max(m.scale, 0.001), C * 0.92)
        fit = size / max(pw, ph)               # keep aspect, fit in box
        cr.save(); cr.translate(cx, cy); cr.rotate(math.sin(m.wobble) * 0.08)
        cr.scale(pw * fit / pw, ph * fit / ph)
        Gdk.cairo_set_source_pixbuf(cr, pb, -pw * fit / 2, -ph * fit / 2)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(min(e * 4.0, 1.0)); cr.restore()
        return False

    # blur: ask Hyprland for a real frosted glass behind us ------------------
    def enable_blur(self):
        if self.cfg.get("blur_layerrule"):
            self.hypr('eval pcall(hl.layer_rule,{namespace="dusky-cursor-magic",'
                      'blur=true,ignorezero=true})')

def main():
    a = sys.argv[1:]
    demo = a[a.index("--demo") + 1] if "--demo" in a and a.index("--demo") + 1 < len(a) else ("random" if "--demo" in a else None)
    cfg = load_config(a[a.index("-c") + 1] if "-c" in a else None)
    d = Daemon(cfg, demo=demo)
    d.enable_blur()
    Gtk.main()

if __name__ == "__main__":
    main()
