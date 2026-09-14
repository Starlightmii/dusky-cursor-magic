#!/usr/bin/python3
"""Cursor Soul Studio — control window for the dusky-cursor-magic overlay.
Contract with the daemon is the config file only (atomic tmp+rename writes;
daemon hot-reloads on mtime). Live preview runs the real magic_core math.
Run: /usr/bin/python3 cursor_ctl.py [--selftest]"""
import gi, json, math, os, shutil, signal, subprocess, sys, time, types
import cairo
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from magic_core import WiggleDetector, AuraMachine, StarField, load_packs, decode_frames, load_config
CFG_PATH = os.path.expanduser("~/.config/dusky/cursor-magic/config.json")
USER_PACKS = os.path.expanduser("~/.config/dusky/cursor-magic/packs")
REPO_PACKS = os.path.join(HERE, "packs")
PIDFILE = "/tmp/magic_ctl.pid"
PROFILES = ("macos", "snappy", "smooth", "reduced")
SLIDERS = (("peak_scale", "motion", 1.5, 4.0, 0.05), ("gain", "wiggle", 0.1, 1.0, 0.01),
           ("arm_heat", "wiggle", 0.2, 0.95, 0.01), ("tau_s", "wiggle", 0.1, 1.5, 0.01),
           ("size", "sprite", 0.5, 2.0, 0.05))
CHECKS = (("sprite", "bob", "bob"), ("sprite", "spin", "spin"),
          ("aura", "trail", "trail"), ("stars", "enabled", "stars"))
KEY_DEFAULTS = {"size": 1.0, "bob": True, "spin": True, "trail": True, "enabled": True}
def user_cfg(path=CFG_PATH):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return {}
def write_cfg(**kv):
    """Atomic merge-write; daemon sees the mtime bump and reloads."""
    cfg = user_cfg()
    for k, v in kv.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict): cfg[k].update(v)
        else: cfg[k] = v
    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, CFG_PATH)
    return cfg
def pid_alive():
    try:
        with open(PIDFILE) as f: pid = int(f.read().strip())
        os.kill(pid, 0)
        return os.path.isdir(f"/proc/{pid}")     # our pidfile only — never scan names
    except Exception:
        return False
# ---- preview state + paint (shared by live window and --selftest) ----------
def new_state(cfg):
    mo = cfg["motion"]; st = types.SimpleNamespace()
    st.cfg, st.wig = cfg, WiggleDetector(**cfg["wiggle"])
    st.aura = AuraMachine(peak_scale=mo["peak_scale"],
                          start_scale=mo["start_scale"],
                          profile=mo.get("profile", "macos"))
    st.stars = StarField(n=cfg.get("stars", {}).get("per_burst", 10))
    st.rev = st.wig.rev_count
    st.C, st.center = 260.0, (130.0, 130.0)
    st.pixbufs, st.durations, st.total, st.s_time = [], [], 0.0, 0.0
    st.sprite_on = False
    st.trail = []                       # (t, x, y) preview comet path
    st.shake = None                     # pending synthetic (t, pt) test-shake queue
    return st
def all_emotions():
    merged = {}
    for d in (REPO_PACKS, USER_PACKS): merged.update(load_packs(d))
    return merged
def _seq_files(spec):
    """seq manifest -> sorted frame files in spec['path'] dir, else []."""
    d = spec.get("path", "")
    if not os.path.isdir(d): return []
    return sorted(f for f in os.listdir(d) if f.lower().endswith((".png", ".webp")))
def thumb_path(spec):
    """Any manifest type -> a still image path for the chooser, or None."""
    t, p = spec.get("type"), spec.get("path", "")
    if t in ("gif", "png") and os.path.isfile(p): return p
    if t == "seq":
        files = _seq_files(spec)
        if files: return os.path.join(p, files[0])   # f00.png
def load_sprite(st, name):
    st.pixbufs, st.sprite_on, st.total = [], False, 0.0
    for pack in all_emotions().values():
        spec = pack["emotions"].get(name or "")
        if not spec: continue
        t = spec.get("type")
        if t in ("gif", "png") and os.path.isfile(spec.get("path", "")):
            try: frames, durs = decode_frames(spec["path"])
            except Exception: return
            st.pixbufs = [GdkPixbuf.Pixbuf.new_from_data(
                f.convert("RGBA").tobytes(), GdkPixbuf.Colorspace.RGB, True, 8,
                f.width, f.height, f.width * 4) for f in frames]
            st.durations = [max(0.02, x) for x in durs]
        elif t == "seq":                              # turntable frames, daemon-mirror
            files = _seq_files(spec)
            try:
                st.pixbufs = [GdkPixbuf.Pixbuf.new_from_file(
                    os.path.join(spec["path"], f)) for f in files]
            except Exception: return
            st.durations = [1.0 / spec.get("fps", 24)] * len(st.pixbufs)
        else: continue
        st.total = float(sum(st.durations)); return
def tick_state(st, t, pt):
    """Feed preview-local coords to the REAL WiggleDetector -> heat -> aura."""
    stars_on = st.cfg.get("stars", {}).get("enabled", True)
    if pt and (st.wig.feed(t, *pt) or st.wig.rev_count != st.rev):
        st.rev = st.wig.rev_count
        if stars_on:
            st.stars.burst(t, st.cfg.get("stars", {}).get("per_burst", 10))
    if st.cfg.get("aura", {}).get("trail", True) and st.aura.alpha > 0.02 and pt:
        st.trail.append((t, pt[0], pt[1]))
    while st.trail and t - st.trail[0][0] > 0.6: st.trail.pop(0)
    st.aura.update(t, st.wig.heat)
    st.sprite_on = st.wig.heat >= st.wig.arm_heat and bool(st.pixbufs)
    if st.sprite_on: st.s_time += 0.016
def _star(cr, x, y, size, rot, al, col):
    cr.save(); cr.translate(x, y); cr.rotate(rot)
    for k in range(8):
        rr = size if k % 2 == 0 else size * 0.38
        th = k * math.pi / 4
        (cr.move_to if k == 0 else cr.line_to)(rr * math.cos(th), rr * math.sin(th))
    cr.close_path(); cr.set_source_rgba(*col, al); cr.fill()
    cr.arc(0, 0, size * 0.28, 0, 2 * math.tau)
    cr.set_source_rgba(1, 1, 1, al * 0.9); cr.fill(); cr.restore()
def paint(cr, st):
    """Mirror of the daemon's paint at 260px — same gradients/stars/particles."""
    C = st.C; cx, cy = st.center
    g = st.cfg["glow"]; col = g["color"]; m = st.aura; a, e = m.alpha, m.energy
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.set_source_rgb(0.05, 0.045, 0.08); cr.paint()
    cr.set_operator(cairo.OPERATOR_ADD)
    if a > 0.003:
        es = (m.scale - m.start) / max(0.01, m.peak - m.start)
        R = g["outer_r"] * C * (0.45 + 0.55 * es) * (0.6 + 0.4 * e)
        gr = cairo.RadialGradient(cx, cy, 0, cx, cy, R)
        gr.add_color_stop_rgba(0.00, *col, g["soft_alpha"] * a * (0.6 + 0.4 * e))
        gr.add_color_stop_rgba(0.45, *col, g["soft_alpha"] * 0.5 * a)
        gr.add_color_stop_rgba(0.80, *col, g["soft_alpha"] * 0.12 * a)
        gr.add_color_stop_rgba(1.00, *col, 0.0)
        cr.set_source(gr); cr.paint()
        r2 = 0.30 * C * (0.45 + 0.55 * es)
        gr2 = cairo.RadialGradient(cx, cy, 0, cx, cy, r2)
        gr2.add_color_stop_rgba(0.0, 1, 1, 1, g["inner_alpha"] * 0.7 * a)
        gr2.add_color_stop_rgba(1.0, *col, 0.0)
        cr.set_source(gr2); cr.paint()
        if st.sprite_on and st.pixbufs:
            t = st.s_time % st.total if st.total else 0.0
            acc = 0.0; i = 0
            for i, d in enumerate(st.durations):
                acc += d
                if t < acc: break
            pb = st.pixbufs[min(i, len(st.pixbufs) - 1)]
            sp = st.cfg.get("sprite", {}); now = time.perf_counter()
            red = st.cfg.get("motion", {}).get("profile") == "reduced"
            size = C * 0.35 * m.scale * sp.get("size", 1.0)
            if not red and sp.get("bob", True):
                size *= 1.0 + 0.03 * math.sin(now * (1.6 + 2.4 * e))
            cr.save(); cr.translate(cx, cy)
            if not red and sp.get("spin", True):
                cr.rotate(math.radians(2.0) * math.sin(now * (0.35 + 0.5 * e)))
            fit = size / max(pb.get_width(), pb.get_height())
            dw, dh = pb.get_width() * fit, pb.get_height() * fit
            Gdk.cairo_set_source_pixbuf(cr, pb, -dw / 2, -dh / 2)
            cr.paint_with_alpha(a); cr.restore()
        n = st.cfg.get("sparkles", 8); now = time.perf_counter()
        for i in range(n):
            ang = now * 0.6 + i * math.tau / n
            r = 150 * C / 512 * (1 + 0.2 * math.sin(now * 1.1 + i * 2.1)) * (0.5 + 0.5 * es)
            tw = 0.5 + 0.5 * math.sin(now * 3.0 + i * 1.7)
            cr.set_source_rgba(1, .93, .99, a * (0.2 + 0.5 * tw) * (0.5 + 0.5 * e))
            cr.arc(cx + r * math.cos(ang), cy + r * math.sin(ang) * 0.72,
                   (1.8 + 2 * tw) * C / 512 * (0.7 + 0.6 * e), 0, 2 * math.tau); cr.fill()
    scol = st.cfg.get("stars", {}).get("color", [1, .95, .75]); s = C / 512
    if st.trail:                                        # fading comet behind aura
        now = time.perf_counter(); prev = None
        for (tt, x, y) in st.trail:
            life = 1.0 - (now - tt) / 0.6
            if life > 0 and prev:
                cr.set_line_width(6 * life * a); cr.set_source_rgba(*scol, life * 0.35 * a)
                cr.move_to(*prev); cr.line_to(x, y); cr.stroke()
            prev = (x, y)
    for (ang, rad, size, rot, al) in st.stars.stars(time.perf_counter()):
        _star(cr, cx + rad * math.cos(ang) * s, cy + rad * math.sin(ang) * 0.85 * s,
              size * 0.6, rot, al, scol)
    cr.set_operator(cairo.OPERATOR_OVER)
# ---- window ----------------------------------------------------------------
CSS = b"""
window{background:#141220;color:#e6e2f5} \
.card{background:#1c1930;border:1px solid #322c52;border-radius:14px;padding:10px} \
.title{font-size:15px;font-weight:bold;color:#cabff5} \
.hint{color:#8f86b8;font-size:11px} \
button{background:#2b2547;color:#e6e2f5;border:1px solid #4a3f7a;border-radius:12px;padding:8px} \
button:hover{background:#372f5c} \
list,row{background:#1c1930;color:#e6e2f5;border-radius:10px} \
row:selected{background:#3d3468} \
scale trough{background:#2b2547;border-radius:8px;min-height:6px} \
scale slider{background:#cabff5;border-radius:8px;min-height:14px;min-width:14px} \
radiobutton label{color:#e6e2f5} \
.accent{color:#f5c9d8;font-weight:bold} \
button.accent{background:#7b3f6e;border-color:#b56ba0} \
button.accent:hover{background:#92497f}
"""
def cls(w, c):
    w.get_style_context().add_class(c); return w

class Studio(Gtk.Window):
    def __init__(self):
        super().__init__(title="✦ Cursor Soul Studio ✦")
        self.cfg = load_config(CFG_PATH)
        self.st = new_state(self.cfg)
        self.mouse = None
        self.set_default_size(720, 560); self.set_resizable(False)
        pr = Gtk.CssProvider(); pr.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), pr, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=12)
        self.add(root)
        root.pack_start(self._header(), False, False, 0)
        body = Gtk.Box(spacing=10); root.pack_start(body, True, True, 0)
        body.pack_start(self._motion_card(), False, False, 0)
        body.pack_start(self._sprite_card(), False, False, 0)
        body.pack_start(self._preview_card(), False, False, 0)
        self._refresh_packs()
        load_sprite(self.st, self.cfg.get("emotion"))
        self.connect("destroy", self._quit)
        self._src = GLib.timeout_add(16, self._tick)     # 60fps preview
        GLib.timeout_add(750, self._poll)                # /proc status dot
        self.connect("key-press-event", self._key)
        self.show_all()
    def _key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape: self.close()
        return False
    def _card(self, title):
        box = cls(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6), "card")
        box.pack_start(cls(Gtk.Label(label=title, xalign=0), "title"),
                       False, False, 0)
        return box
    def _header(self):
        box = Gtk.Box(spacing=10)
        self.dot = Gtk.Label(label="●")
        self.toggle = Gtk.Button(label="Wake the magic")
        self.toggle.connect("clicked", self._on_toggle)
        box.pack_start(self.dot, False, False, 0)
        box.pack_start(self.toggle, False, False, 0)
        box.pack_start(cls(Gtk.Label(label="shake the preview — the aura is alive ✧"), "hint"), True, True, 0)
        return box
    def _motion_card(self):
        mo = self._card("✧ Motion")
        row = Gtk.Box(spacing=8); self.radios = {}
        for p in PROFILES:
            r = Gtk.RadioButton.new_with_label_from_widget(self.radios.get("macos"), p)
            r.set_active(self.cfg["motion"].get("profile") == p)
            r.connect("toggled", self._profile, p)
            self.radios[p] = r; row.pack_start(r, False, False, 0)
        mo.pack_start(row, False, False, 0)
        self.sliders = {}
        for key, sec, lo, hi, step in SLIDERS:
            if sec not in ("motion", "wiggle") and key not in self.cfg.get(sec, {}):
                continue                                  # key not in config.default.json
            r = Gtk.Box(spacing=6)
            r.pack_start(Gtk.Label(label=key, width_request=70, xalign=0), False, False, 0)
            s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
            s.set_value(self.cfg.get(sec, {}).get(key, KEY_DEFAULTS.get(key, lo)))
            s.set_draw_value(False)
            lab = Gtk.Label(label=f"{s.get_value():.2f}", width_request=40, xalign=1)
            s.connect("value-changed", lambda sc, l=lab: l.set_text(f"{sc.get_value():.2f}"))
            s.connect("button-release-event",
                      lambda w, e, k=key, sc=s: self._slider(k, sc.get_value()))
            self.sliders[key] = (s, sec)
            r.pack_start(s, True, True, 0); r.pack_start(lab, False, False, 0)
            mo.pack_start(r, False, False, 0)
        return mo
    def _sprite_card(self):
        sp = self._card("☾ Soul sprite")
        self.packs = Gtk.ListBox()
        self.packs.connect("row-activated", self._pick)
        self.packs.set_size_request(250, 240)
        sw = Gtk.ScrolledWindow(); sw.add(self.packs)
        sw.set_policy("never", "automatic")
        sp.pack_start(sw, True, True, 0)
        self.checks = {}
        row = Gtk.Box(spacing=8)
        for sec, key, label in CHECKS:
            if key not in self.cfg.get(sec, {}): continue   # defensive: key not documented
            cb = Gtk.CheckButton.new_with_label(label)
            cb.set_active(bool(self.cfg.get(sec, {}).get(key, True)))
            cb.connect("toggled", self._check, sec, key)
            self.checks[f"{sec}.{key}"] = cb; row.pack_start(cb, False, False, 0)
        if row.get_children(): sp.pack_start(row, False, False, 0)
        ib = Gtk.Button(label="✦ Import .gif / .png")
        ib.connect("clicked", self._import)
        sp.pack_start(ib, False, False, 0)
        tb = cls(Gtk.Button(label="✧ Test shake"), "accent")
        tb.connect("clicked", self._test_shake)
        sp.pack_start(tb, False, False, 0)
        return sp
    def _preview_card(self):
        box = self._card("✦ Live preview — wiggle here")
        eb = Gtk.EventBox()
        self.da = Gtk.DrawingArea(); self.da.set_size_request(260, 260)
        self.da.connect("draw", lambda _w, cr: (paint(cr, self.st), False)[1])
        eb.add(self.da)
        eb.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        eb.connect("motion-notify-event", lambda _w, ev: setattr(self, "mouse", (ev.x, ev.y)))
        eb.connect("leave-notify-event", lambda *_: setattr(self, "mouse", None))
        box.pack_start(eb, False, False, 0)
        return box
    # behaviour ---------------------------------------------------------------
    def _tick(self):
        pt = self.st.shake.pop(0) if self.st.shake else self.mouse
        tick_state(self.st, time.perf_counter(), pt)
        self.da.queue_draw()
        return True
    def _poll(self):
        up = pid_alive()
        self.dot.set_markup(f'<span foreground="{"#8ce699" if up else "#d96680"}">●</span>')
        self.toggle.set_label("Put the spell to sleep" if up else "Wake the magic")
        return True
    def _on_toggle(self, _b):
        if pid_alive():                                   # OFF: kill our pidfile only
            with open(PIDFILE) as f: os.kill(int(f.read().strip()), signal.SIGTERM)
            os.remove(PIDFILE); write_cfg(disabled=True)
        else:                                             # ON: enable + launch detached
            write_cfg(disabled=False)
            log = open("/tmp/magic_ctl.log", "ab")
            p = subprocess.Popen(["setsid", "/usr/bin/python3",
                                  os.path.join(HERE, "cursor_magic.py")],
                                 stdout=log, stderr=log)
            with open(PIDFILE, "w") as f: f.write(str(p.pid))
        self._poll()
    def _apply(self):
        self.cfg = load_config(CFG_PATH)
        self.st = new_state(self.cfg); load_sprite(self.st, self.cfg.get("emotion"))
    def _profile(self, btn, name):
        if btn.get_active():
            write_cfg(motion={"profile": name}); self._apply()
    def _slider(self, key, val):
        write_cfg(**{self.sliders[key][1]: {key: round(val, 3)}}); self._apply()
    def _check(self, cb, sec, key):
        write_cfg(**{sec: {key: cb.get_active()}}); self._apply()
    def _test_shake(self, _b):
        """Queue 0.5s of fast zigzag (at the 16ms tick cadence) through the real detector."""
        self.st.shake = [(40.0 if i % 2 else 220.0, 110.0 + 40.0 * math.sin(i * 2.1))
                         for i in range(32)]
    def _refresh_packs(self):
        for c in self.packs.get_children(): self.packs.remove(c)
        self.rows = []
        for pname, pack in sorted(all_emotions().items()):
            for emo, spec in sorted(pack.get("emotions", {}).items()):
                img = Gtk.Image(); pb = None
                if spec.get("type") in ("gif", "png") and os.path.isfile(spec.get("path", "")):
                    try:
                        pb = GdkPixbuf.Pixbuf.new_from_file(spec["path"]).scale_simple(
                            48, 48, GdkPixbuf.InterpType.BILINEAR)
                    except Exception: pb = None
                if pb: img.set_from_pixbuf(pb)
                else: img.set_from_icon_name("image-x-generic", Gtk.IconSize.BUTTON)
                rb = Gtk.Box(spacing=8)
                rb.pack_start(img, False, False, 0)
                rb.pack_start(Gtk.Label(label=f"{emo} · {pname}"), False, False, 0)
                row = Gtk.ListBoxRow(); row.add(rb)
                self.packs.add(row); self.rows.append((emo, pname))
        self.packs.show_all()
        for i, (emo, _) in enumerate(self.rows):
            if emo == self.cfg.get("emotion"):
                self.packs.select_row(self.packs.get_row_at_index(i))
    def _pick(self, _lb, row):
        if row:
            emo, pname = self.rows[row.get_index()]
            write_cfg(emotion=emo, sprite_pack=pname)
            load_sprite(self.st, emo)
    def _import(self, _b):
        fc = Gtk.FileChooserDialog(title="Import a sprite", transient_for=self,
                                   action=Gtk.FileChooserAction.OPEN)
        fc.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Import", Gtk.ResponseType.OK)
        for pat in ("*.gif", "*.png"):
            f = Gtk.FileFilter(); f.add_pattern(pat); f.set_name(pat); fc.add_filter(f)
        src = fc.get_filename() if fc.run() == Gtk.ResponseType.OK else None
        fc.destroy()
        src = src or ""
        ext = os.path.splitext(src or "")[1].lower().lstrip(".")
        if ext not in ("gif", "png"): return
        stem = os.path.splitext(os.path.basename(src))[0]
        d = os.path.join(USER_PACKS, "imported")
        dst = os.path.join(d, stem, os.path.basename(src))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(dst): shutil.copy2(src, dst)
        mf = os.path.join(d, "manifest.json")
        m = user_cfg(mf); m.setdefault("emotions", {})[stem] = \
            {"type": ext, "path": f"{stem}/{os.path.basename(src)}"}
        tmp = mf + ".tmp"
        with open(tmp, "w") as f: json.dump(m, f, indent=1)
        os.replace(tmp, mf)
        self._refresh_packs()
    def _quit(self, *_):
        if self._src: GLib.source_remove(self._src)
        Gtk.main_quit()
# ---- selftest ----------------------------------------------------------------
def selftest():
    cfg = load_config(CFG_PATH); print("OK config loaded")
    merged = all_emotions()
    emos = sorted({e for p in merged.values() for e in p.get("emotions", {})})
    print(f"OK packs: {sorted(merged)} emotions: {emos}")
    st = new_state(cfg); load_sprite(st, cfg.get("emotion"))
    t, x = 1000.0, 130.0
    for _ in range(12):                                   # synthetic violent wiggle
        for _ in range(6):
            x += 70; t += 0.016; tick_state(st, t, (min(x, 250), 130 + 20 * math.sin(t * 9)))
        x = 130.0; t += 0.016; tick_state(st, t, (x, 130.0))
    assert st.wig.heat > 0.3, f"wiggle made no heat: {st.wig.heat}"
    assert st.aura.scale > st.aura.start + 0.5, f"aura flat: {st.aura.scale}"
    assert st.stars.count > 0, "no star burst"
    print(f"OK wiggle heat={st.wig.heat:.2f} aura={st.aura.scale:.2f} stars={st.stars.count}")
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 260, 260)
    paint(cairo.Context(surf), st)
    surf.write_to_png("/tmp/ctl_selftest.png")
    print("OK offscreen frame /tmp/ctl_selftest.png")
    print("OK selftest passed")
def main():
    if "--selftest" in sys.argv[1:]:
        selftest(); return
    Studio(); Gtk.main()
if __name__ == "__main__":
    main()
