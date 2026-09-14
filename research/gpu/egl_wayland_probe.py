#!/usr/bin/env python3
"""Cycle-5 gap fill: does EGL_PLATFORM_WAYLAND (via libwayland-client) yield configs?
This is THE path a layer-shell GPU window needs. Correct argtypes throughout."""
import ctypes, ctypes.util, os

EGL = ctypes.CDLL("libEGL.so.1")
WL = ctypes.CDLL(ctypes.util.find_library("wayland-client"))

EGL_EXTENSIONS, EGL_VENDOR, EGL_VERSION = 0x3055, 0x3053, 0x3054
EGL_SURFACE_TYPE, EGL_RENDERABLE_TYPE = 0x3033, 0x3040
EGL_WINDOW_BIT, EGL_PBUFFER_BIT = 0x0001, 0x0002
EGL_OPENGL_ES2_BIT, EGL_OPENGL_ES3_BIT, EGL_OPENGL_BIT = 0x0004, 0x0040, 0x0008
EGL_RED_SIZE, EGL_GREEN_SIZE, EGL_BLUE_SIZE, EGL_ALPHA_SIZE, EGL_DEPTH_SIZE = 0x3024, 0x3023, 0x3022, 0x3025, 0x3026
EGL_NONE, EGL_PLATFORM_WAYLAND = 0x3038, 0x31D8

WL.wl_display_connect.restype = ctypes.c_void_p
WL.wl_display_connect.argtypes = [ctypes.c_char_p]
WL.wl_display_get_error.restype = ctypes.c_int
WL.wl_display_get_error.argtypes = [ctypes.c_void_p]

EGL.eglGetError.restype = ctypes.c_uint32
EGL.eglQueryString.restype = ctypes.c_char_p
EGL.eglQueryString.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
EGL.eglGetPlatformDisplay.restype = ctypes.c_void_p
EGL.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
EGL.eglInitialize.restype = ctypes.c_uint
EGL.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
EGL.eglChooseConfig.restype = ctypes.c_uint
EGL.eglChooseConfig.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
EGL.eglBindAPI.restype = ctypes.c_uint
EGL.eglBindAPI.argtypes = [ctypes.c_uint]

wl = WL.wl_display_connect(os.environ.get("WAYLAND_DISPLAY", "wayland-1").encode())
if not wl:
    print("wl_display_connect FAILED")
    raise SystemExit(1)
print("wl_display_connect OK; wl error:", WL.wl_display_get_error(wl))

dpy = EGL.eglGetPlatformDisplay(EGL_PLATFORM_WAYLAND, ctypes.c_void_p(wl), None)
print("eglGetPlatformDisplay(WAYLAND):", "OK" if dpy else f"FAILED 0x{EGL.eglGetError():x}")
if not dpy:
    raise SystemExit(1)

maj, min_ = ctypes.c_int(0), ctypes.c_int(0)
ok = EGL.eglInitialize(dpy, ctypes.byref(maj), ctypes.byref(min_))
print(f"eglInitialize: ok={ok} {maj.value}.{min_.value} err=0x{EGL.eglGetError():x}" if not ok
      else f"eglInitialize OK {maj.value}.{min_.value} vendor={(EGL.eglQueryString(dpy, EGL_VENDOR) or b'').decode()}")
print("display extensions:", (EGL.eglQueryString(dpy, EGL_EXTENSIONS) or b"").decode())

for name, attrs in [
    ("GLES2+WINDOW+8/8/8/8+D24", [EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                                   EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_DEPTH_SIZE, 24, EGL_NONE]),
    ("GLES3+WINDOW+8/8/8/8",      [EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
                                   EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE]),
    ("GL(desktop)+WINDOW",        [EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
                                   EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE]),
    ("GLES2+WINDOW no-alpha",     [EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                                   EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE]),
    ("GLES2+PBUFFER (control)",   [EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE]),
]:
    arr = (ctypes.c_int * len(attrs))(*attrs)
    n = ctypes.c_int(0)
    ok = EGL.eglChooseConfig(dpy, arr, None, 0, ctypes.byref(n))
    err = EGL.eglGetError()
    tag = "  <-- WORKS" if (ok and n.value > 0) else ""
    print(f"chooseConfig[{name}]: ok={ok} n={n.value} err=0x{err:x}{tag}")
