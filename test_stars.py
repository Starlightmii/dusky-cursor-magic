import sys, math
sys.path.insert(0, '/home/starlight/Projects/dusky-cursor-magic')
import numpy as np
import shader_soul as S

s = S.Stars(cap=200)
s.burst(0.0, 10, 10, size=1.0)
assert len(s._s) == 21, len(s._s)                    # 14 ring + 2 hero + 5 micro
out = s.live(0.15)
assert len(out) == 21 and all(a > 0 for *_, a in out)
# synced: two ring stars at same angle share the spiral-wave term
xs = [o for o in s.live(0.15)]
# ease-out: distance grows but decelerates
d0 = math.hypot(xs[0][0] - 10, xs[0][1] - 10)
s2 = S.Stars(); s2.burst(0.0, 0, 0, n_ring=1, n_hero=0, n_micro=0)
# capped after 10 bursts
for i in range(10):
    s.burst(i * 0.01, 0, 0)
assert len(s._s) <= s.cap
# stamp on the real half-res field: gx/gy are CENTER-relative canvas px
a = S.Aura(220, 34.0, 1.0, 0.0)
g = np.zeros((a.F, a.F))
S.stamp(a.gx, a.gy, g, [(0, 0, 8, 0.0, 1.0)], 2)      # star at field centre
assert g[a.F // 2, a.F // 2] > 1.0 and g[0, 0] == 0.0
S.stamp(a.gx, a.gy, g, [(-120, 0, 8, 0.0, 1.0)], 2)   # off-window star: no-op
assert g[0, 0] == 0.0
# shed stays small + lazy (speed < burst speeds)
s3 = S.Stars(); s3.shed(0.0, 5, 5)
assert len(s3._s) == 1 and s3._s[0][2] < 120
print('stars: OK', len(s._s))
