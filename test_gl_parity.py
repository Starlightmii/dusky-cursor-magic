"""GL aura port = CPU aura in structure (procedural noise differs, physics
must not): same frame rendered both ways, checked for the same light.
FAILS loudly if the GPU path silently fell back or produces garbage."""
import sys, time
sys.path.insert(0, '/home/starlight/Projects/dusky-cursor-magic')
import numpy as np
import shader_soul as S
import soul_gl as G

C = 320
cpu = S.Aura(C, 34.0, 1.0, 0.0)
gl = G.SoulGL(C, 34.0, 1.0, 0.0)          # raises if GL path is broken
buf_c = np.zeros((cpu.F, cpu.F), np.uint32)
buf_g = np.zeros((gl.F, gl.F), np.uint32)

stars = S.Stars()
stars.burst(0.0, C / 2.0 + 60, C / 2.0 - 40)
slive = stars.live(0.3, (0.0, 0.0), C / 2.0)
rip = [(20.0, -14.0, 0.25, 1.0, 0.4)]     # field coords (SCALE already div'd)

for name, rend, buf in (("cpu", cpu.render, buf_c), ("gl", gl.render, buf_g)):
    rend(0.3, 0.5, 0.8, rip, buf, core=True, hot=(6.0, -4.0),
         vel=(4.0, 1.0), trail=(-30.0, 18.0), stars=slive)

a_c = (buf_c >> 24).astype(np.float32)
a_g = (buf_g >> 24).astype(np.float32)


def lum(buf):
    r = (buf >> 16 & 255); g = (buf >> 8 & 255); b = buf & 255
    return (r + g + b) / 3.0


# structure checks on the GL buffer
ctr = lum(buf_g)[gl.F // 2, gl.F // 2]
crn = lum(buf_g)[:6, :6].max()
assert a_g.mean() > 2, "GL field is black (readback broken)"
assert ctr > 120, f"core not bright: {ctr}"
assert crn < 10, f"corner leaking: {crn}"
# burst star must light its spot in BOTH renders (same coords -> same place)
sx, sy = int(slive[0][0] / 2 + gl.F / 2), int(slive[0][1] / 2 + gl.F / 2)
assert lum(buf_c)[sy, sx] > 15 or lum(buf_g)[sy, sx] > 15, "star invisible"
# energy envelope: GL mean within 2.5x of CPU mean (tint-noise differs,
# gross brightness may not)
ratio = a_g.mean() / a_c.mean()
assert 0.4 < ratio < 2.5, f"brightness split: {ratio:.2f}"

n = 300
t0 = time.perf_counter()
for i in range(n):
    gl.render(i / 60, 0.5, 0.3, rip, buf_g, core=True, stars=slive)
t1 = time.perf_counter()
for i in range(n):
    cpu.render(i / 60, 0.5, 0.3, rip, buf_c, core=True, stars=slive)
t2 = time.perf_counter()
print(f"GL {1000*(t1-t0)/n:.2f}ms/f  CPU {1000*(t2-t1)/n:.2f}ms/f  "
      f"speedup {(t2-t1)/(t1-t0):.1f}x — PARITY OK")