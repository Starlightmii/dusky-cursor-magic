"""Eyeball proxy for U4/U5/U8 (the math-verified, un-eyeballed effects).
Shimmer breathes on a ~10.5s cycle so one snapshot can land in its trough —
sample phases. Asserts effects INK real cairo pixels and stay whisper-faint."""
import os, sys, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cairo
import cursor_magic as cm
from magic_core import load_config, AuraMachine, StarField, SpeedEstimator

cfg = load_config(os.path.expanduser("~/.config/dusky/cursor-magic/config.json"))
C = cfg["canvas_px"]

def make():
    d = cm.Daemon.__new__(cm.Daemon)
    d.cfg = cfg; d.demo = None; d._demo_t = None; d.disabled = False
    d.aura = AuraMachine(peak_scale=cfg["motion"]["peak_scale"],
                         start_scale=cfg["motion"]["start_scale"], profile="macos")
    d.stars = StarField(n=10, seed=1); d.click_fx = []; d.trail = []
    d.speed_est = SpeedEstimator(window_s=0.05); d._sm = None
    d._last_alive = time.perf_counter() - 3
    d.center = (C / 2, C / 2); d._anchor = d.center
    d.pixbufs = []; d.sprite_on = False; d._idle = True; d._reduced = False
    d.durations = []; d.total = 0.0; d.pack_t0 = 0.0; d.pack = None
    d._prev = real_pc()
    return d

def ink_of(fn):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, C, C)
    fn(cairo.Context(surf)); surf.flush()
    buf = surf.get_data()
    return sum(1 for b in buf[3::4] if b), max(buf[3::4])

# U8: sample 12 breathe phases across one 10.5s cycle
real_pc = time.perf_counter
best = (0, 0)
try:
    for i in range(12):
        d = make()
        time.perf_counter = lambda base=real_pc(), ph=i * 10.472 / 12: base + ph
        best = max(best, ink_of(d._shimmer))
finally:
    time.perf_counter = real_pc
print(f"U8 shimmer peak-phase: {best[0]} px, max alpha {best[1]}/255")
assert best[0] > 30, "shimmer never paints"
assert best[1] <= 40, f"shimmer not whisper-faint ({best[1]})"

# U5: sustained 0.35-ambient glide -> breath converges, comet paints
d = make()
now = real_pc()
for step in range(60):                       # ~1s of glide at 16ms ticks
    d.aura.update(now + step * 0.016, 0.0, amb=0.35)
    d._last_alive = now                       # pretend not idle
def full_draw(cr):
    d.center = (d.center[0] + 6, d.center[1])   # glide so the comet has trail
    d.trail.append((real_pc(), d.center[0], d.center[1]))
    d.draw(None, cr)
n, mx = ink_of(full_draw)
print(f"U5 whisper steady: scale={d.aura.scale:.2f} alpha={d.aura.alpha:.3f} "
      f"-> {n} px, max alpha {mx}/255")
assert 1.0 < d.aura.scale < 2.0, f"breath too big: {d.aura.scale}"  # peak is 3.0
assert n > 400, "comet paints nothing during glide"
# ponytail: alpha guard is scale-band, not pixel cap — ta=0.35+0.65*h by
# design puts amb=0.35 at 0.58; scale<2.0 is the real "never near peak" check
# reduced-motion: same glide must stay near-dead
d2 = make()
d2.aura = AuraMachine(peak_scale=cfg["motion"]["peak_scale"],
                      start_scale=cfg["motion"]["start_scale"],
                      profile="reduced")
d2._reduced = True
for step in range(60):
    d2.aura.update(now + step * 0.016, 0.0, amb=0.35)
assert d2.aura.scale == 1.0, "reduced-motion not flattened"
print("VISUAL-PROXY OK")
