#!/usr/bin/env python3
"""gpu_proof FINAL — full proof: GLES3 context on Wayland-platform display,
surfaceless, FBO render of an aura-style shader, read back pixels as numpy."""
import ctypes, ctypes.util, os, sys
import numpy as np

LOG = open("/tmp/gpu5_trace.log", "w", buffering=1)
def log(*a): print(*a, file=LOG, flush=True)

EGL = ctypes.CDLL("libEGL.so.1")
WL = ctypes.CDLL(ctypes.util.find_library("wayland-client"))

EGL_SURFACE_TYPE, EGL_RENDERABLE_TYPE = 0x3033, 0x3040
EGL_WINDOW_BIT, EGL_OPENGL_ES3_BIT = 0x0001, 0x0040
EGL_RED_SIZE, EGL_GREEN_SIZE, EGL_BLUE_SIZE, EGL_ALPHA_SIZE = 0x3024, 0x3023, 0x3022, 0x3025
EGL_NONE, EGL_PLATFORM_WAYLAND = 0x3038, 0x31D8
EGL_CONTEXT_CLIENT_VERSION, EGL_OPENGL_ES_API = 0x3098, 0x30A2

WL.wl_display_connect.restype = ctypes.c_void_p
WL.wl_display_connect.argtypes = [ctypes.c_char_p]
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
EGL.eglCreateContext.restype = ctypes.c_void_p
EGL.eglCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
EGL.eglMakeCurrent.restype = ctypes.c_uint
EGL.eglMakeCurrent.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
EGL.eglSwapInterval.restype = ctypes.c_uint
EGL.eglSwapInterval.argtypes = [ctypes.c_void_p, ctypes.c_int]

wl = WL.wl_display_connect(os.environ.get("WAYLAND_DISPLAY", "wayland-1").encode())
dpy = EGL.eglGetPlatformDisplay(EGL_PLATFORM_WAYLAND, ctypes.c_void_p(wl), None)
assert dpy
maj, min_ = ctypes.c_int(0), ctypes.c_int(0)
assert EGL.eglInitialize(dpy, ctypes.byref(maj), ctypes.byref(min_))
log("display OK vendor", (EGL.eglQueryString(dpy, 0x3053) or b"").decode())

attrs = [EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
         EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE]
arr = (ctypes.c_int * len(attrs))(*attrs)
cfg = (ctypes.c_void_p * 1)()
n = ctypes.c_int(0)
assert EGL.eglChooseConfig(dpy, arr, cfg, 1, ctypes.byref(n)) and n.value == 1
EGL.eglBindAPI(EGL_OPENGL_ES_API)
ctx_attrs = (ctypes.c_int * 3)(EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE)
ctx = EGL.eglCreateContext(dpy, cfg[0], None, ctx_attrs)
assert ctx, hex(EGL.eglGetError())
ok = EGL.eglMakeCurrent(dpy, None, None, ctx)
assert ok, hex(EGL.eglGetError())
log("context OK (surfaceless, GLES3)")

GLES = ctypes.CDLL("libGLESv2.so.2")

def P(fn, res=None, args=None):
    f = getattr(GLES, fn)
    if res is not None: f.restype = res
    if args is not None: f.argtypes = args
    return f

glGetString = P("glGetString", ctypes.c_char_p, [ctypes.c_uint])
log("GL_RENDERER:", (glGetString(0x1F01) or b"?").decode())

GL_FRAGMENT_SHADER, GL_COMPILE_STATUS, GL_LINK_STATUS = 0x8B30, 0x8B81, 0x8B82
GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D = 0x8D40, 0x8CE0, 0x0DE1
GL_FRAMEBUFFER_COMPLETE, GL_RGBA, GL_UNSIGNED_BYTE = 0x8CD5, 0x1908, 0x1401
GL_TRIANGLES, GL_NEAREST = 0x0004, 0x2600

FS = b"""#version 300 es
precision highp float;
uniform vec2 u_res; uniform float u_time;
out vec4 frag;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
float noise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x), mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ float v=0.0,a=0.5; for(int i=0;i<4;i++){ v+=a*noise(p); p*=2.03; a*=0.5;} return v; }
void main(){
  vec2 uv = (gl_FragCoord.xy - 0.5*u_res)/u_res.y;
  float r = length(uv);
  float ang = atan(uv.y, uv.x);
  // domain-warped fbm aura (cycle-1 recipe) + ring
  float w = fbm(uv*3.0 + 0.15*u_time + fbm(uv*1.5 - 0.06*u_time)*1.2);
  float glow = exp(-9.0*r*r);
  float ring = exp(-pow((r-0.35-0.03*sin(u_time*2.0+ang*4.0))/0.06,2.0))*0.8;
  float sparkle = pow(max(0.0, 1.0-abs(uv.x*uv.y*40.0)),2.0); // 4-point cross hint
  float a = clamp(glow*(0.6+0.8*w) + ring + sparkle*glow, 0.0, 1.0);
  frag = vec4(vec3(0.55,0.62,1.0)*a + vec3(0.9,0.85,1.0)*ring*0.3, a);
}
"""

glCreateShader = P("glCreateShader", ctypes.c_uint, [ctypes.c_uint])
glShaderSource = P("glShaderSource", None, [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_int)])
glCompileShader = P("glCompileShader", None, [ctypes.c_uint])
glGetShaderiv = P("glGetShaderiv", None, [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)])
glCreateProgram = P("glCreateProgram", ctypes.c_uint, [])
glAttachShader = P("glAttachShader", None, [ctypes.c_uint, ctypes.c_uint])
glLinkProgram = P("glLinkProgram", None, [ctypes.c_uint])
glGetProgramiv = P("glGetProgramiv", None, [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)])
glGenFramebuffers = P("glGenFramebuffers", None, [ctypes.c_int, ctypes.POINTER(ctypes.c_uint)])
glGenTextures = P("glGenTextures", None, [ctypes.c_int, ctypes.POINTER(ctypes.c_uint)])
glBindFramebuffer = P("glBindFramebuffer", None, [ctypes.c_uint, ctypes.c_uint])
glBindTexture = P("glBindTexture", None, [ctypes.c_uint, ctypes.c_uint])
glTexParameteri = P("glTexParameteri", None, [ctypes.c_uint, ctypes.c_uint, ctypes.c_int])
glTexImage2D = P("glTexImage2D", None, [ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p])
glFramebufferTexture2D = P("glFramebufferTexture2D", None, [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_int])
glCheckFramebufferStatus = P("glCheckFramebufferStatus", ctypes.c_uint, [ctypes.c_uint])
glUseProgram = P("glUseProgram", None, [ctypes.c_uint])
glGetUniformLocation = P("glGetUniformLocation", ctypes.c_int, [ctypes.c_uint, ctypes.c_char_p])
glUniform2f = P("glUniform2f", None, [ctypes.c_int, ctypes.c_float, ctypes.c_float])
glUniform1f = P("glUniform1f", None, [ctypes.c_int, ctypes.c_float])
glViewport = P("glViewport", None, [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int])
glDrawArrays = P("glDrawArrays", None, [ctypes.c_uint, ctypes.c_int, ctypes.c_int])
glReadPixels = P("glReadPixels", None, [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p])

sh = glCreateShader(GL_FRAGMENT_SHADER)
src = (ctypes.c_char_p * 1)(FS)
glShaderSource(sh, 1, src, None)
glCompileShader(sh)
status = ctypes.c_int(0)
glGetShaderiv(sh, GL_COMPILE_STATUS, ctypes.byref(status))
assert status.value, "compile failed"
prog = glCreateProgram()
glAttachShader(prog, sh)
glLinkProgram(prog)
glGetProgramiv(prog, GL_LINK_STATUS, ctypes.byref(status))
assert status.value, "link failed"
log("aura shader compiled+linked")

W = H = 256
fbo, tex = ctypes.c_uint(0), ctypes.c_uint(0)
glGenFramebuffers(1, ctypes.byref(fbo)); glGenTextures(1, ctypes.byref(tex))
glBindFramebuffer(GL_FRAMEBUFFER, fbo.value)
glBindTexture(GL_TEXTURE_2D, tex.value)
glTexParameteri(GL_TEXTURE_2D, GL_NEAREST, 1)
glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex.value, 0)
assert glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE
log("fbo complete")

# --- fullscreen triangle: VAO+VBO (GLES3 needs an enabled attribute array)
glGenBuffers = P("glGenBuffers", None, [ctypes.c_int, ctypes.POINTER(ctypes.c_uint)])
glBindBuffer = P("glBindBuffer", None, [ctypes.c_uint, ctypes.c_uint])
glBufferData = P("glBufferData", None, [ctypes.c_uint, ctypes.c_longlong, ctypes.c_void_p, ctypes.c_uint])
glGenVertexArrays = P("glGenVertexArrays", None, [ctypes.c_int, ctypes.POINTER(ctypes.c_uint)])
glBindVertexArray = P("glBindVertexArray", None, [ctypes.c_uint])
glEnableVertexAttribArray = P("glEnableVertexAttribArray", None, [ctypes.c_uint])
glVertexAttribPointer = P("glVertexAttribPointer", None, [ctypes.c_uint, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_void_p])
GL_ARRAY_BUFFER, GL_STATIC_DRAW, GL_FLOAT = 0x8892, 0x88E4, 0x1406
verts = np.array([-1,-1, 3,-1, -1,3], dtype=np.float32)
vao, vbo = ctypes.c_uint(0), ctypes.c_uint(0)
glGenVertexArrays(1, ctypes.byref(vao)); glGenBuffers(1, ctypes.byref(vbo))
glBindVertexArray(vao.value)
glBindBuffer(GL_ARRAY_BUFFER, vbo.value)
glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts.ctypes.data_as(ctypes.c_void_p), GL_STATIC_DRAW)
glEnableVertexAttribArray(0)
glVertexAttribPointer(0, 2, GL_FLOAT, 0, 8, None)
log("vao/vbo bound")

glUseProgram(prog)
glUniform2f(glGetUniformLocation(prog, b"u_res"), float(W), float(H))
glUniform1f(glGetUniformLocation(prog, b"u_time"), 1.25)
glViewport(0, 0, W, H)

import time
t0 = time.perf_counter()
FRAMES = 200
for i in range(FRAMES):
    glUniform1f(glGetUniformLocation(prog, b"u_time"), i * 0.016)
    glDrawArrays(GL_TRIANGLES, 0, 3)
buf = (ctypes.c_ubyte * (W * H * 4))()
glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, buf)
dt = time.perf_counter() - t0
img = np.frombuffer(buf, dtype=np.uint8).reshape(H, W, 4)
c, k = img[H//2, W//2], img[2, 2]
log(f"rendered {FRAMES} frames in {dt*1000:.0f}ms -> {dt/FRAMES*1000:.2f}ms/frame (256px)")
log("center", tuple(int(v) for v in c), "corner", tuple(int(v) for v in k))
log("GPU_PATH_PROVEN" if c[0] > 30 and k[0] < 15 else "OUTPUT_SUSPECT")

# save a PNG via PIL for visual check
try:
    from PIL import Image
    Image.fromarray(img[::-1, :, :3]).save("/tmp/gpu_aura_test.png")
    log("saved /tmp/gpu_aura_test.png")
except Exception as e:
    log("png save skipped:", e)
