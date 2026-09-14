import sys, math
sys.path.insert(0, '/home/starlight/Projects/dusky-cursor-magic')
import numpy as np
import shader_soul as S

# A nova shockwave (exp=0.4, Sedov-Taylor) must sit AHEAD of a click ripple
# (exp=1.0, linear) at the same age — blast physics: fast breakout, decelerates.
a = S.Aura(220, 34.0, 1.0, 0.0)
base = np.zeros((a.F, a.F), np.uint32)
a.render(1.0, 0.0, 0.0, [], base, core=False)   # everything except the ring

def ring_radius(rip):
    buf = np.zeros((a.F, a.F), np.uint32)
    a.render(1.0, 0.0, 0.0, [rip], buf, core=False)
    d = (buf.astype(np.int64) - base.astype(np.int64)).clip(0)
    ys, xs = np.unravel_index(d.argmax(), d.shape)
    return math.hypot(xs * a.SCALE - a.C / 2.0, ys * a.SCALE - a.C / 2.0)

# ripple tuples are (x, y, AGE, strength, expansion)
mid = S.RIPPLE_LIFE / 2.0
r_lin = ring_radius((0.0, 0.0, mid, 1.0, 1.0))    # linear (click) at half-life
r_nova = ring_radius((0.0, 0.0, mid, 1.0, 0.4))   # Sedov blast at half-life
assert r_nova > r_lin * 1.25, (r_lin, r_nova)
print(f'SHOCKWAVE OK lin={r_lin:.0f}px blast={r_nova:.0f}px')
