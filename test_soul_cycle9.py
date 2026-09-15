"""Cycle-9 gate: the full choreography the user asked for.

  rest            -> default Dusky arrow, field pitch black (arrow visible)
  implode@5s      -> black-hole VOID + particles falling IN, then
  nova@9-15s      -> the blast
  moving          -> smooth tail of SMALL stars, no halo
  fast sustained  -> BIGGEST galaxy blast, shockwave crosses the WHOLE
                     screen (no hidden box: window is 320px, ring ->3x+)

Tests: pure state machine phases, void render, big ripple radius, tail
star visibility at low alpha cap.
"""
import sys
sys.path.insert(0, '/home/starlight/Projects/dusky-cursor-magic')
import numpy as np
import shader_soul as S

# ---- 1. state machine -------------------------------------------------
def phase_of(now, still, last_nova, fire_at, collapse_at, moving,
             fast=False, blast_at=0.0):
    return S.soul_phase(now, still, last_nova, fire_at, collapse_at,
                        moving, fast=fast, blast_at=blast_at)[:3]

# still pointer: nothing until 5s, then gathering, then nova at 10s
p, fa, ca = phase_of(2.0, 0.0, -9.0, 10.0, 5.0, False)
assert p == "rest" and fa == 10.0 and ca == 5.0
p, fa, ca = phase_of(5.0, 0.0, -9.0, 10.0, 5.0, False)
assert p == "gather" and fa == 10.0 and ca == 5.0
p, fa, ca = phase_of(10.0, 0.0, -9.0, 10.0, 5.0, False)
assert p == "nova" and 19.0 <= fa <= 25.0 and 14.0 <= ca <= 20.0
# every park repeats the cycle: the re-armed window carries its OWN gather
# (collapse sits 5s BEFORE the next detonation)
p, fa, ca = phase_of(12.0, 0.0, 10.0, 20.0, 15.0, False)
assert p == "rest"                       # remnant still fading
p, fa, ca = phase_of(16.0, 0.0, 10.0, 20.0, 15.0, False)
assert p == "gather"                     # black hole before the next blast
# movement: full re-arm from the move instant
p, fa, ca = phase_of(30.0, 29.0, 10.0, 25.0, 20.0, True)
assert p == "rest" and 39.0 <= fa <= 45.0 and 34.0 <= ca <= 40.0
# sustained fast sweep -> blast, own cooldown window
res = S.soul_phase(40.0, 29.0, 10.0, 50.0, 45.0, True, fast=True,
                   blast_at=39.0)
assert res[0] == "blast" and 45.0 <= res[3] <= 48.0, res
# blast cooldown: not again before blast_at
res = S.soul_phase(41.0, 29.0, 10.0, 50.0, 45.0, True, fast=True,
                   blast_at=46.0)
assert res[0] == "rest", res
# slow movement never blasts
res = S.soul_phase(40.0, 29.0, 10.0, 50.0, 45.0, True, fast=False,
                   blast_at=0.0)
assert res[0] == "rest", res
print("PHASE OK")

# ---- 2. dark void render ------------------------------------------------
# void=1.0 must put FULLY-OVERFLOWED BLACK (a>=200, rgb<20) in the disk
import inspect
sig = inspect.signature(S.Aura.render)
assert "void" in sig.parameters, "Aura.render needs a void channel"
a = S.Aura(320, 34.0, 1.0, 0.0)
buf = np.zeros((a.F, a.F), np.uint32)
a.render(0.5, 0.0, 0.0, [], buf, stars=[(0.0, 0.0, 6.0, 0.0, 0.5),
                                        (68.0, 0.0, 14.0, 0.0, 0.8)],
         void=1.0)
argb = buf.view(np.uint32)
al = (argb >> 24) & 0xFF
rgb_ok = ((argb >> 16) & 0xFF) < 20
cx, cy = a.F // 2, a.F // 2
assert al[cy, cx] > 240 and rgb_ok[cy, cx], "void centre not black-opaque"
nvoid = int(((al > 200) & rgb_ok).sum())
assert nvoid > a.F * a.F * 0.02, f"void too small: {nvoid}"
# the tail stars still print OUTSIDE the void
assert al[cy, cx + 34] > 6, "stars swallowed by void"
print(f"VOID OK  nvoid_px={nvoid}")

# ---- 3. whole-space blast ripple ---------------------------------------
# a big ripple (exponent marker 2.0) must reach >2.5x the window by end-life
RIP_MAX = S.RIPPLE_LIFE
a = S.Aura(320, 34.0, 1.0, 0.0)
buf = np.zeros((a.F, a.F), np.uint32)
# big ripple at age 0.85*LIFE: rr = R0*4.2*BIGK*(u**0.4)
u = 0.85
rr_small = a.R0 * 4.2 * (u ** 0.4)
rr_big = a.R0 * 4.2 * S.BIG_K * (u ** 0.4)
assert rr_big / (320 / 2) > 2.5, f"big blast only covers {rr_big}px"
assert rr_big / rr_small == S.BIG_K
a.render(0.5, 0.0, 0.0, [(0.0, 0.0, 0.5 * RIP_MAX, 2.2, 0.4)], buf,
         big=True)
n = int((((buf >> 24) & 0xFF) > 40).sum())
assert n > a.F * a.F * 0.02, "big ripple band not visible"
print(f"BIG RIPPLE OK  cover={rr_big:.0f}px band_px={n}")

# ---- 4. tail stars: small and capped ------------------------------------
s = S.Stars(cap=200)
s.shed(0.0, 100, 100)
assert s._s[-1][3] < 12, "tail stars must be small"
s2 = S.Stars(cap=200)
for i in range(30):
    s2.shed(i * 0.02, 100 + i * 4, 100)
live = s2.live(0.4, org=(0, 0), half=160.0)
assert len(live) > 8, "tail died too fast"
assert max(l[4] for l in live) < 0.8
print("TAIL STARS OK")

# ---- 5. field_only + nova-with-void wiring --------------------------------
rest = S.field_only(320, 34.0, 0.5, 0.0, 0.0)
void = S.field_only(320, 34.0, 0.5, 0.0, 0.0, void=1.0)
al_v = (void >> 24) & 0xFF
assert int(((al_v > 200)).sum()) > 320 // 2, "field_only void not plumbed"
print("PHASE OK  VOID OK  BIG RIPPLE OK  TAIL STARS OK -> CYCLE-9 GATE WRITTEN")
