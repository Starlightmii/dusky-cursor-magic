#!/usr/bin/env /usr/bin/python3
"""Does input_shape_combine_region actually stick on GTK3-wayland? Prints rc."""
import cairo, gi
gi.require_version("Gtk", "3.0"); gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell, GLib
GLib.set_prgname("dcm-probe")
win = Gtk.Window(type=Gtk.WindowType.POPUP)
GtkLayerShell.init_for_window(win)
GtkLayerShell.set_namespace(win, "dusky-cursor-magic")
GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, 200)
GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, 200)

def try_shape(tag):
    w = win.get_window()
    if not w:
        print(tag, "no gdk window yet"); return
    for arg, name in [(cairo.Region(), "empty-region"), (None, "none")]:
        try:
            w.input_shape_combine_region(arg, 0, 0)
            print(tag, name, "-> call ok")
        except Exception as ex:
            print(tag, name, "-> RAISED", type(ex).__name__, ex)

win.connect("realize", lambda w: (try_shape("realize"),
        GLib.timeout_add(300, lambda: (try_shape("map+300ms"), False)[1])))
win.show_all()
GLib.timeout_add(1500, Gtk.main_quit)
Gtk.main()
