"""soul_gl — GPU aura field for shader_soul (Intel iGPU, GLES3 surfaceless).

Subclasses Aura: same attributes, same call signature, writes the same
premultiplied ARGB32 numpy buffer. The field renders on Mesa's iGPU
(~0.3ms/frame) instead of ~14ms of numpy; the cairo/layer-shell window
is untouched. make() falls back to the CPU Aura if any GL step fails.

ctypes pattern from research/gpu/gpu_proof5.py (proven): the attribute
combo matters — GLES3 + RGBA8 yields configs, GLES2+alpha8+D24 yields
zero (the old "no GPU on this box" artifact)."""
import ctypes
import ctypes.util
import os

import numpy as np

import shader_soul as S

GL_TEXTURE_2D = 0x0DE1
GL_RGBA, GL_RGBA8, GL_UNSIGNED_BYTE = 0x1908, 0x8058, 0x1401
MAX_STARS, MAX_RIPPLES = 120, 8

_VERT = """#version 300 es
void main(){
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}"""

_FRAG = """#version 300 es
precision highp float;
#define NS %NS%
#define NR %NR%
#define LIFE %LIFE%
uniform float u_t, u_speed, u_energy, u_R, u_R0, u_ascale, u_coreOn, u_seed;
uniform vec2 u_hot, u_vel, u_trail;
uniform vec3 u_cool, u_warm;
uniform vec4 u_starP[NS];   // x,y,size,rot (canvas px, centre-relative)
uniform float u_starA[NS];
uniform vec4 u_rip[NR];     // x,y,age,strength (canvas px, centre-relative)
uniform float u_ripE[NR];   // expansion exponent
out vec4 o;
float hash2(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float grid(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
  return mix(mix(hash2(i),hash2(i+vec2(1,0)),f.x),
             mix(hash2(i+vec2(0,1)),hash2(i+vec2(1,1)),f.x),f.y);}
float fbm3(vec2 p){float s=0.,a=.5;for(int k=0;k<3;k++){s+=a*grid(p);p*=2.03;a*=.5;}return s;}
float fbm2(vec2 p){float s=0.,a=.5;for(int k=0;k<2;k++){s+=a*grid(p);p*=2.03;a*=.5;}return s;}
void main(){
  vec2 q = vec2(gl_FragCoord.x - %HF% - 0.5, %HF% + 1.0 - gl_FragCoord.y - 0.5) * 2.0;
  vec2 pp = q - u_hot;                             // pointer frame
  float r = length(pp);
  float wob = fbm3(vec2(q.x * 0.028 + u_seed,
                        q.y * 0.028 + u_t * 0.18)
                   + vec2(0.0, fbm2(vec2(q.x * 0.014 - u_t * 0.06,
                                         q.y * 0.014)) * 0.9));
  float glow = exp(-pow(r / u_R, 2.0))
             + exp(-pow((r - u_R * 0.82) / (u_R * 0.35), 2.0)) * (0.30 + 0.25 * u_speed);
  glow *= 1.0 + (wob - 0.5) * (0.55 + 0.35 * u_speed);
  glow += u_energy * exp(-pow(r / u_R, 2.0)) * 0.6;
  for (int k = 0; k < NR; k++) {
    if (u_rip[k].w > 0.0 && u_rip[k].z >= 0.0 && u_rip[k].z < LIFE) {
      float u = u_rip[k].z / LIFE;
      float rr = u_R0 * 4.2 * pow(u, u_ripE[k]);
      // Sedov pressure decay t^-1.2 x life-fade, top-clamped 2.2 (see CPU)
      float amp = (u_ripE[k] < 1.0)
        ? min(pow(0.3 / max(u, 0.05), 1.2) * (1.0 - u), 2.2)
        : (1.0 - u);
      glow += exp(-pow((length(q - u_rip[k].xy) - rr) / (u_R0 * 0.18), 2.0))
            * amp * u_rip[k].w * 0.8;
    }
  }
  float pulse = 0.9 + 0.10 * sin(u_t * 2.6) + 0.06 * sin(u_t * 5.1);
  glow += exp(-pow((r - u_R0 * 0.20 * (1.0 - 0.25 * u_speed) * pulse) / (u_R0 * 0.05), 2.0))
        * (0.55 + 0.25 * u_energy) * pulse;
  glow = max(glow, 0.0);
  float coreW = 0.0;
  if (u_coreOn > 0.5) {
    float cr_ = u_R0 * 0.24 * (1.0 + 0.12 * sin(u_t * 2.6));
    float vm = min(length(u_vel) * 0.05, 1.0);
    if (vm > 0.02) {
      vec2 uv_ = normalize(u_vel);
      float al = dot(pp, uv_) / (cr_ * (1.0 + 0.5 * vm));
      float pe = (pp.x * uv_.y - pp.y * uv_.x) / (cr_ * (1.0 - 0.28 * vm));
      coreW = exp(-(al * al + pe * pe));
    } else coreW = exp(-pow(r / cr_, 2.0));
    glow += coreW * 2.2;
    if (length(u_trail) > 6.0)
      glow += exp(-pow(length(pp - u_trail) / (cr_ * 0.8), 2.0)) * 0.8
            * min(length(u_trail) / 40.0, 1.0);
  } else {
    glow *= clamp((r - 10.0) / 24.0, 0.0, 1.0);
  }
  for (int k = 0; k < NS; k++) {
    float a = u_starA[k];
    if (a > 0.01) {
      vec2 d = q - u_starP[k].xy;
      float c = cos(u_starP[k].w), s_ = sin(u_starP[k].w);
      vec2 rv = vec2(d.x * c + d.y * s_, -d.x * s_ + d.y * c);
      float sig = u_starP[k].z * 0.28;
      glow += (exp(-(rv.x * rv.x) / (sig * sig) - (rv.y * rv.y) / (sig * sig * 9.0))
             + exp(-(rv.y * rv.y) / (sig * sig) - (rv.x * rv.x) / (sig * sig * 9.0))) * a * 1.4;
      glow += exp(-dot(d, d) / (sig * sig)) * a * 0.9;
    }
  }
  float al = clamp(glow * u_ascale, 0.0, 1.0);
  float tint = clamp(wob * 0.6 + u_speed * 0.55 + u_energy * 0.35, 0.0, 1.0);
  vec3 rgb = mix(u_cool, u_warm, tint);
  if (coreW > 0.0) rgb += (1.0 - rgb) * clamp(coreW * 3.0, 0.0, 1.0);
  o = vec4(rgb * al, al);                          // premultiplied, like cairo
}"""


def _sig(GL):
    """restype/argtypes — pointers as bare ints would truncate on 64-bit."""
    cp = ctypes.c_void_p
    pu = ctypes.POINTER(ctypes.c_uint)
    pi = ctypes.POINTER(ctypes.c_int)
    pf = ctypes.POINTER(ctypes.c_float)
    tab = {
        "glCreateShader": (ctypes.c_uint, [ctypes.c_uint]),
        "glShaderSource": (None, [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p), pi]),
        "glCompileShader": (None, [ctypes.c_uint]),
        "glGetShaderiv": (None, [ctypes.c_uint, ctypes.c_uint, pi]),
        "glGetShaderInfoLog": (None, [ctypes.c_uint, ctypes.c_int, pi,
                                      ctypes.c_char_p]),
        "glCreateProgram": (ctypes.c_uint, []),
        "glAttachShader": (None, [ctypes.c_uint, ctypes.c_uint]),
        "glLinkProgram": (None, [ctypes.c_uint]),
        "glGetProgramiv": (None, [ctypes.c_uint, ctypes.c_uint, pi]),
        "glUseProgram": (None, [ctypes.c_uint]),
        "glGetUniformLocation": (ctypes.c_int, [ctypes.c_uint, ctypes.c_char_p]),
        "glGenVertexArrays": (None, [ctypes.c_int, pu]),
        "glBindVertexArray": (None, [ctypes.c_uint]),
        "glGenTextures": (None, [ctypes.c_int, pu]),
        "glBindTexture": (None, [ctypes.c_uint, ctypes.c_uint]),
        "glTexImage2D": (None, [ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_uint, ctypes.c_uint, cp]),
        "glTexParameteri": (None, [ctypes.c_uint, ctypes.c_uint, ctypes.c_int]),
        "glGenFramebuffers": (None, [ctypes.c_int, pu]),
        "glBindFramebuffer": (None, [ctypes.c_uint, ctypes.c_uint]),
        "glFramebufferTexture2D": (None, [ctypes.c_uint] * 4 + [ctypes.c_int]),
        "glCheckFramebufferStatus": (ctypes.c_uint, [ctypes.c_uint]),
        "glViewport": (None, [ctypes.c_int] * 4),
        "glUniform1f": (None, [ctypes.c_int, ctypes.c_float]),
        "glUniform2f": (None, [ctypes.c_int, ctypes.c_float, ctypes.c_float]),
        "glUniform3f": (None, [ctypes.c_int] + [ctypes.c_float] * 3),
        "glUniform4fv": (None, [ctypes.c_int, ctypes.c_int, pf]),
        "glUniform1fv": (None, [ctypes.c_int, ctypes.c_int, pf]),
        "glDrawArrays": (None, [ctypes.c_uint, ctypes.c_int, ctypes.c_int]),
        "glReadPixels": (None, [ctypes.c_int] * 4 + [ctypes.c_uint,
                             ctypes.c_uint, cp]),
    }
    for name, (rt, at) in tab.items():
        f = getattr(GL, name)
        f.restype, f.argtypes = rt, at


class SoulGL(S.Aura):
    def __init__(self, canvas, radius, strength, warp_seed, grow=1.6,
                 ascale=0.55, tints=None):
        super().__init__(canvas, radius, strength, warp_seed, grow, ascale,
                         tints)
        EGL = ctypes.CDLL("libEGL.so.1")
        GL = ctypes.CDLL("libGLESv2.so.2")
        WL = ctypes.CDLL(ctypes.util.find_library("wayland-client"))
        WL.wl_display_connect.restype = ctypes.c_void_p
        WL.wl_display_connect.argtypes = [ctypes.c_char_p]
        EGL.eglGetPlatformDisplay.restype = ctypes.c_void_p
        EGL.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p,
                                              ctypes.c_void_p]
        EGL.eglInitialize.restype = ctypes.c_int
        EGL.eglInitialize.argtypes = [ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.c_int),
                                      ctypes.POINTER(ctypes.c_int)]
        EGL.eglChooseConfig.restype = ctypes.c_int
        EGL.eglChooseConfig.argtypes = [ctypes.c_void_p,
                                        ctypes.POINTER(ctypes.c_int),
                                        ctypes.POINTER(ctypes.c_void_p),
                                        ctypes.c_int,
                                        ctypes.POINTER(ctypes.c_int)]
        EGL.eglBindAPI.restype = ctypes.c_int
        EGL.eglBindAPI.argtypes = [ctypes.c_uint]
        EGL.eglCreateContext.restype = ctypes.c_void_p
        EGL.eglCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_void_p,
                                         ctypes.POINTER(ctypes.c_int)]
        EGL.eglMakeCurrent.restype = ctypes.c_int
        EGL.eglMakeCurrent.argtypes = [ctypes.c_void_p] * 4
        EGL.eglGetError.restype = ctypes.c_uint
        _sig(GL)
        self._GL = GL

        wl = WL.wl_display_connect(
            os.environ.get("WAYLAND_DISPLAY", "wayland-1").encode())
        assert wl, "no wayland display"
        dpy = EGL.eglGetPlatformDisplay(0x31D8, ctypes.c_void_p(wl), None)
        assert dpy, "eglGetPlatformDisplay"
        maj, mi = ctypes.c_int(0), ctypes.c_int(0)
        assert EGL.eglInitialize(dpy, ctypes.byref(maj), ctypes.byref(mi)), \
            "eglInitialize"
        # the combo that matters: GLES3 + RGBA8 (NOT alpha8+D24 -> 0 configs)
        attrs = [0x3033, 0x0001, 0x3040, 0x0040, 0x3024, 8, 0x3023, 8,
                 0x3022, 8, 0x3025, 8, 0x3038]
        arr = (ctypes.c_int * len(attrs))(*attrs)
        cfgs = (ctypes.c_void_p * 1)()
        n = ctypes.c_int(0)
        assert EGL.eglChooseConfig(dpy, arr, cfgs, 1, ctypes.byref(n)) \
            and n.value == 1, "zero configs"
        assert EGL.eglBindAPI(0x30A2), "bindAPI"
        ctx = EGL.eglCreateContext(dpy, cfgs[0], None,
                                   (ctypes.c_int * 3)(0x3098, 3, 0x3038))
        assert ctx, "ctx %s" % hex(EGL.eglGetError())
        assert EGL.eglMakeCurrent(dpy, None, None, ctx), "surfaceless"

        def shader(typ, src):
            sh = GL.glCreateShader(typ)
            b = src.encode()
            GL.glShaderSource(sh, 1, ctypes.byref(ctypes.c_char_p(b)), None)
            GL.glCompileShader(sh)
            ok = ctypes.c_int(0)
            GL.glGetShaderiv(sh, 0x8B81, ctypes.byref(ok))
            if not ok.value:                       # GLSL errors are opaque
                ln = ctypes.c_int(0)               # without the info log
                GL.glGetShaderiv(sh, 0x8B84, ctypes.byref(ln))
                buf = ctypes.create_string_buffer(ln.value + 1)
                GL.glGetShaderInfoLog(sh, ln.value + 1, None, buf)
                raise RuntimeError(buf.value.decode()[:600])
            return sh

        prog = GL.glCreateProgram()
        GL.glAttachShader(prog, shader(0x8B31, _VERT))
        GL.glAttachShader(prog, shader(0x8B30, _FRAG.replace(
            "%NS%", str(MAX_STARS)).replace("%NR%", str(MAX_RIPPLES))
            .replace("%LIFE%", repr(float(S.RIPPLE_LIFE)))
            .replace("%HF%", f"{self.F // 2}.0")))
        GL.glLinkProgram(prog)
        ok = ctypes.c_int(0)
        GL.glGetProgramiv(prog, 0x8B82, ctypes.byref(ok))
        assert ok.value, "program link failed"
        GL.glUseProgram(prog)
        vao = ctypes.c_uint(0)
        GL.glGenVertexArrays(1, ctypes.byref(vao))
        GL.glBindVertexArray(vao.value)

        tex, fbo = ctypes.c_uint(0), ctypes.c_uint(0)
        GL.glGenTextures(1, ctypes.byref(tex))
        GL.glBindTexture(GL_TEXTURE_2D, tex.value)
        GL.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, self.F, self.F, 0,
                        GL_RGBA, GL_UNSIGNED_BYTE, None)
        GL.glTexParameteri(GL_TEXTURE_2D, 0x2800, 0x2600)
        GL.glTexParameteri(GL_TEXTURE_2D, 0x2801, 0x2600)
        GL.glGenFramebuffers(1, ctypes.byref(fbo))
        GL.glBindFramebuffer(0x8D40, fbo.value)
        GL.glFramebufferTexture2D(0x8D40, 0x8CE0, GL_TEXTURE_2D, tex.value, 0)
        assert GL.glCheckFramebufferStatus(0x8D40) == 0x8CD5, "fbo"
        self._prog, self._fbo, self._tex = prog, fbo.value, tex.value

        def U(name):
            return GL.glGetUniformLocation(prog, name.encode())
        self._u = {n: U(n) for n in (
            "u_t", "u_speed", "u_energy", "u_R", "u_R0", "u_ascale",
            "u_coreOn", "u_seed", "u_hot", "u_vel", "u_trail", "u_cool",
            "u_warm", "u_starP[0]", "u_starA[0]", "u_rip[0]", "u_ripE[0]")}
        self._px = np.empty((self.F, self.F, 4), np.uint8)
        self._starP = (ctypes.c_float * (MAX_STARS * 4))()
        self._starA = (ctypes.c_float * MAX_STARS)()
        self._rip = (ctypes.c_float * (MAX_RIPPLES * 4))()
        self._ripE = (ctypes.c_float * MAX_RIPPLES)()

    def render(self, t, speed, energy, ripples, out, core=False,
               hot=(0.0, 0.0), vel=(0.0, 0.0), trail=(0.0, 0.0), stars=()):
        GL = self._GL
        u = self._u
        GL.glUseProgram(self._prog)
        GL.glBindFramebuffer(0x8D40, self._fbo)
        GL.glViewport(0, 0, self.F, self.F)
        GL.glUniform1f(u["u_t"], t)
        GL.glUniform1f(u["u_speed"], speed)
        GL.glUniform1f(u["u_energy"], energy)
        GL.glUniform1f(u["u_R"],
                       self.R0 * (1.0 + self.grow * speed) * self.strength)
        GL.glUniform1f(u["u_R0"], self.R0)
        GL.glUniform1f(u["u_ascale"], self.ascale)
        GL.glUniform1f(u["u_coreOn"], 1.0 if core else 0.0)
        GL.glUniform1f(u["u_seed"], self.seed)
        GL.glUniform2f(u["u_hot"], hot[0], hot[1])
        GL.glUniform2f(u["u_vel"], vel[0], vel[1])
        GL.glUniform2f(u["u_trail"], trail[0] - hot[0], trail[1] - hot[1])
        cool, warm = self.tints or ((0.42, 0.62, 1.00), (1.00, 0.72, 0.38))
        GL.glUniform3f(u["u_cool"], *cool)
        GL.glUniform3f(u["u_warm"], *warm)
        for k in range(MAX_RIPPLES):
            b = k * 4
            if k < len(ripples):
                (x, y, age, s, e) = ripples[k]
                self._rip[b] = x * self.SCALE      # field -> canvas px
                self._rip[b + 1] = y * self.SCALE
                self._rip[b + 2], self._rip[b + 3] = age, s
                self._ripE[k] = e
            else:
                self._rip[b + 3] = 0.0
        GL.glUniform4fv(u["u_rip[0]"], 1, self._rip)
        GL.glUniform1fv(u["u_ripE[0]"], 1, self._ripE)
        for k in range(MAX_STARS):
            b = k * 4
            if k < len(stars):
                (x, y, size, rot, a) = stars[k]
                self._starP[b:b + 4] = (x, y, size, rot)
                self._starA[k] = a
            else:
                self._starA[k] = 0.0
        GL.glUniform4fv(u["u_starP[0]"], 1, self._starP)
        GL.glUniform1fv(u["u_starA[0]"], 1, self._starA)
        GL.glDrawArrays(0x0004, 0, 3)              # TRIANGLES
        GL.glReadPixels(0, 0, self.F, self.F, GL_RGBA, GL_UNSIGNED_BYTE,
                        ctypes.c_void_p(self._px.ctypes.data))
        # GL bottom-up -> top-down; RGBA bytes -> premult ARGB32 (BGRA mem)
        f = self._px[::-1][:, :, (2, 1, 0, 3)].copy()
        out[...] = f.view(np.uint32).reshape(self.F, self.F)


def make(canvas, radius, strength, seed, grow, ascale, tints):
    """SoulGL if the iGPU path comes up clean, else the CPU Aura."""
    try:
        g = SoulGL(canvas, radius, strength, seed, grow=grow, ascale=ascale,
                   tints=tints)
        buf = np.zeros((g.F, g.F), np.uint32)
        g.render(0.0, 0.0, 0.0, [], buf, core=True)
        if int(buf.max()) > 0:
            return g, "GL"
    except Exception:
        pass
    return S.Aura(canvas, radius, strength, seed, grow=grow, ascale=ascale,
                  tints=tints), "CPU"
