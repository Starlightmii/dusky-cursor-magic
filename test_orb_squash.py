#!/usr/bin/env python3
"""Gate: orb squashes along motion, round at rest. FAILS if tilt breaks."""
import importlib.util, numpy as np, sys
spec = importlib.util.spec_from_file_location("ss", "shader_soul.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def extent(buf, ax):
    a = ((buf >> 24) & 255) > 128
    if ax == 0:
        row = a[a.shape[0]//2, :]
    else:
        row = a[:, a.shape[1]//2]
    idx = np.flatnonzero(row)
    return idx[-1] - idx[0] if len(idx) else 0

a = m.Aura(220, 34.0, 0.5, 3, grow=1.2, ascale=0.5)
F = a.F
rest = np.zeros((F, F), np.uint32); a.render(1.0, 0, 0, [], rest, core=True)
mv = np.zeros((F, F), np.uint32); a.render(1.0, 0, 0, [], mv, core=True, vel=(18.0, 0.0))
x_rest, y_rest = extent(rest, 0), extent(rest, 1)
x_mv, y_mv = extent(mv, 0), extent(mv, 1)
assert 0.85 <= x_rest / y_rest <= 1.15, f"rest not round: {x_rest}/{y_rest}"
assert x_mv / x_rest >= 1.15, f"no stretch: {x_mv}/{x_rest}"
assert y_mv / y_rest <= 0.92, f"no squash: {y_mv}/{y_rest}"
print(f"SQUASH OK rest={x_rest}/{y_rest} move={x_mv}/{y_mv}")
