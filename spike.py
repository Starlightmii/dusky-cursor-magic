#!/usr/bin/env /usr/bin/python3
"""Task 4 gate spike: overlay disc follows pointer via evdev, must be click-through.
Position = clamped TOP/LEFT margins; disc drawn with internal offset so it stays
centered even at screen edges."""
import json, subprocess
import cairo
import gi
gi.require_version("Gtk", "3.0"); gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell, GLib
import evdev

GLib.set_prgname("dusky-cursor-magic")

win = Gtk.Window(type=Gtk.WindowType.POPUP)
GtkLayerShell.init_for_window(win)
GtkLayerShell.set_namespace(win, "dusky-cursor-magic")
GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
GtkLayerShell.set_exclusive_zone(win, -1)
GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
# THE gate: empty input shape = fully click-through
def _passthrough(w):
    w.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
win.connect("realize", _passthrough)

N = 512
da = Gtk.DrawingArea(); da.set_size_request(N, N)

def draw(a, cr):
    cx = pos[0] - GtkLayerShell.get_margin(win, GtkLayerShell.Edge.LEFT)
    cy = pos[1] - GtkLayerShell.get_margin(win, GtkLayerShell.Edge.TOP)
    cr.set_source_rgba(0.7, 0.75, 1, 0.35)
    cr.arc(cx, cy, 80, 0, 6.2832); cr.fill()

da.connect("draw", draw)
win.add(da)
m_left, m_top = [0], [0]

j = json.loads(subprocess.run(["hyprctl", "cursorpos", "-j"],
    capture_output=True, text=True).stdout)
pos = [j["x"], j["y"]]

def on_dev(src, cond, d):
    for ev in d.read():
        if ev.code == 0: pos[0] += ev.value
        elif ev.code == 1: pos[1] += ev.value
    return True

for p in evdev.list_devices():
    d = evdev.InputDevice(p)
    caps = d.capabilities().get(2, [])
    if 0 in caps and 1 in caps:
        GLib.io_add_watch(d.fd, GLib.IO_IN, on_dev, d)
        print("watching", d.path, "|", d.name, flush=True)

def tick():
    m_left[0] = max(0, int(pos[0] - N / 2))
    m_top[0] = max(0, int(pos[1] - N / 2))
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, m_left[0])
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, m_top[0])
    da.queue_draw()
    return True

win.show_all()
GLib.timeout_add(16, tick)
Gtk.main()
