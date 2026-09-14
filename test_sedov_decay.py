import sys, math
sys.path.insert(0, '/home/starlight/Projects/dusky-cursor-magic')
import numpy as np
import shader_soul as S

# Sedov pressure decay: the blast ring must hit HARD early and fade FAST late.
# Old fade was linear (1-u): at quarter-life amp=0.75, at 3/4-life amp=0.25.
# True Sedov t^-1.2 (normalised so amp(0.3LIFE)=1): 1/4-life >> linear, 3/4-life
# << linear. Gate on the *rendered peak delta* so the shader path is covered too.
a = S.Aura(220, 34.0, 1.0, 0.0)
base = np.zeros((a.F, a.F), np.uint32)
a.render(1.0, 0.0, 0.0, [], base, core=False)

def peak(rip):
    buf = np.zeros((a.F, a.F), np.uint32)
    a.render(1.0, 0.0, 0.0, [rip], buf, core=False)
    return float((buf.astype(np.int64) - base.astype(np.int64)).clip(0).max())

L = S.RIPPLE_LIFE
# NOTE: with the OLD linear fade the early/late peak ratio is exactly
# (1-0.25)/(1-0.75) = 3.0. The gate: Sedov t^-1.2 decay must be visibly
# MORE front-loaded than the linear fade it replaces (>4x early/late).
q1 = peak((0.0, 0.0, L * 0.25, 1.0, 0.4))
q3 = peak((0.0, 0.0, L * 0.75, 1.0, 0.4))
r_early = q1 / max(q3, 1)
assert r_early > 4.0, (q1, q3, r_early)
print(f'SEDOV DECAY OK q1={q1:.0f} q3={q3:.0f} ratio={r_early:.1f} (linear was 3.0)')
