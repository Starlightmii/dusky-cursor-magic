#!/usr/bin/env /usr/bin/python3
"""Static 512x512 disc at argv[1],argv[2] via gtk3 layer-shell + empty input shape."""
import sys, cairo, gi
gi.require_version("Gtk", "3.0"); gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell, GLib
GLib.set_prgname("dusky-cursor-magic")
X, Y = int(sys.argv[1]), int(sys.argv[2])
win = Gtk.Window(type=Gtk.WindowType.POPUP)
GtkLayerShell.init_for_window(win)
GtkLayerShell.set_namespace(win, "dusky-cursor-magic")
GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, X - 256)
GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, Y - 256)
GtkLayerShell.set_exclusive_zone(win, -1)
GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
win.connect("realize", lambda w: w.get_window().input_shape_combine_region(cairo.Region(), 0, 0))
da = Gtk.DrawingArea(); da.set_size_request(512, 512)
da.connect("draw", lambda a, cr: (cr.set_source_rgba(0.7, 0.75, 1, 0.35), cr.arc(256, 256, 80, 0, 6.2832), cr.fill())[0])
win.add(da); win.show_all()
Gtk.main()
