#!/usr/bin/env python3
"""EGL probe: print client/display extensions + config counts per display type
and per attribute combination. Correct ctypes argtypes everywhere (no truncation bugs).
Answers: which EGL paths yield GPU configs on this hybrid Arch box."""
import ctypes, ctypes.util, os, sys

EGL = ctypes.CDLL("libEGL.so.1")
EGL_SUCCESS = 0x3000
EGL_EXTENSIONS = 0x3055
EGL_VENDOR = 0x3053
EGL_VERSION = 0x3054
EGL_BLUE_SIZE, EGL_GREEN_SIZE, EGL_RED_SIZE, EGL_ALPHA_SIZE = 0x3022, 0x3023, 0x3024, 0x3025
EGL_DEPTH_SIZE = 0x3026
EGL_SURFACE_TYPE = 0x3033
EGL_WINDOW_BIT, EGL_PBUFFER_BIT, EGL_PIXMAP_BIT = 0x0001, 0x0002, 0x0004
EGL_RENDERABLE_TYPE = 0x3040
EGL_OPENGL_BIT, EGL_OPENGL_ES_BIT, EGL_OPENGL_ES2_BIT, EGL_OPENGL_ES3_BIT = 0x0008, 0x0001, 0x0004, 0x0040
EGL_NONE = 0x3038
EGL_PLATFORM_SURFACELESS_MESA = 0x31DD
EGL_PLATFORM_WAYLAND = 0x31D8
EGL_PLATFORM_GBM_MESA = 0x31D6
EGL_DEFAULT_DISPLAY = ctypes.c_void_p(0)
EGL_NO_CONTEXT = ctypes.c_void_p(0)

EGL.eglGetError.restype = ctypes.c_uint32
EGL.eglQueryString.restype = ctypes.c_char_p
EGL.eglQueryString.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
EGL.eglGetDisplay.restype = ctypes.c_void_p
EGL.eglGetDisplay.argtypes = [ctypes.c_void_p]
EGL.eglGetPlatformDisplay.restype = ctypes.c_void_p
EGL.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]  # EXT uses eglGetPlatformDisplayEXT
EGL.eglGetPlatformDisplay = EGL.eglGetPlatformDisplay
EGL.eglInitialize.restype = ctypes.c_uint
EGL.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
EGL.eglChooseConfig.restype = ctypes.c_uint
EGL.eglChooseConfig.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
EGL.eglTerminate.argtypes = [ctypes.c_void_p]
EGL.eglBindAPI.restype = ctypes.c_uint
EGL.eglBindAPI.argtypes = [ctypes.c_uint]
EGL_OPENGL_API = 0x30A2
EGL.eglCreateContext.restype = ctypes.c_void_p
EGL.eglCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]

qs = lambda d, n: (EGL.eglQueryString(d, n) or b"").decode()

print("== CLIENT extensions (EGL_NO_DISPLAY) ==")
print(qs(EGL_DEFAULT_DISPLAY, EGL_EXTENSIONS))

def try_display(name, get_dpy):
    print(f"\n== DISPLAY: {name} ==")
    dpy = get_dpy()
    if not dpy:
        print("  eglGetDisplay failed:", hex(EGL.eglGetError()))
        return None
    maj, min_ = ctypes.c_int(0), ctypes.c_int(0)
    if not EGL.eglInitialize(dpy, ctypes.byref(maj), ctypes.byref(min_)):
        print(f"  eglInitialize FAILED err=0x{EGL.eglGetError():x}")
        return None
    print(f"  eglInitialize OK {maj.value}.{min_.value} vendor={qs(dpy, EGL_VENDOR)!r} version={qs(dpy, EGL_VERSION)!r}")
    print(f"  DISPLAY extensions: {qs(dpy, EGL_EXTENSIONS)}")
    return dpy

def choose_counts(dpy):
    combos = [
        ("GLES2 + PBUFFER", [EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_DEPTH_SIZE, 24, EGL_NONE]),
        ("GLES2 + WINDOW",  [EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE]),
        ("GLES2 no-surface-type", [EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE]),
        ("GL(desktop) + PBUFFER", [EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE]),
        ("GLES3 + PBUFFER", [EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE]),
    ]
    for name, attrs in combos:
        arr = (ctypes.c_int * len(attrs))(*attrs)
        n = ctypes.c_int(0)
        ok = EGL.eglChooseConfig(dpy, arr, None, 0, ctypes.byref(n))
        err = EGL.eglGetError()
        print(f"  chooseConfig[{name}]: ok={ok} n={n.value} err=0x{err:x}" if not ok or n.value == 0
              else f"  chooseConfig[{name}]: ok={ok} n={n.value}  <-- WORKS")

dpy = try_display("default (eglGetDisplay(NULL))", lambda: EGL.eglGetDisplay(EGL_DEFAULT_DISPLAY))
if dpy:
    choose_counts(dpy)
    EGL.eglTerminate(dpy)

dpy = try_display("surfaceless MESA", lambda: EGL.eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, 0))
if dpy:
    choose_counts(dpy)
    EGL.eglTerminate(dpy)

# GBM platform on both render nodes
gbm = ctypes.CDLL("libgbm.so.1")
gbm.gbm_create_device.restype = ctypes.c_void_p
gbm.gbm_create_device.argtypes = [ctypes.c_int]
for node in ("/dev/dri/renderD128", "/dev/dri/renderD129"):
    try:
        fd = os.open(node, os.O_RDWR | os.CLOEXEC)
    except OSError as e:
        print(f"\n== GBM {node}: open failed {e} ==")
        continue
    gdev = gbm.gbm_create_device(fd)
    dpy = None
    if gdev:
        dpy = try_display(f"GBM platform on {node}", lambda g=gdev: EGL.eglGetPlatformDisplay(EGL_PLATFORM_GBM_MESA, ctypes.c_void_p(g), 0))
        if dpy:
            choose_counts(dpy)
            EGL.eglTerminate(dpy)
    else:
        print(f"\n== GBM {node}: gbm_create_device FAILED ==")
    os.close(fd)

# NVIDIA presence check
print("\n== glvnd vendor files ==")
for f in sorted(os.listdir("/usr/share/glvnd/egl_vendor.d")) if os.path.isdir("/usr/share/glvnd/egl_vendor.d") else []:
    print("  ", f, "->", open("/usr/share/glvnd/egl_vendor.d/" + f).read().strip())
