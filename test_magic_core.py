"""Zero-dep asserts: /usr/bin/python3 test_magic_core.py  (or pytest)."""
import math
from magic_core import SpeedEstimator, AuraMachine, WiggleDetector, StarField


def approx(v, tol=1e-6):
    class A:
        def __eq__(s, o):
            return abs(o - v) <= tol
        def __req__(s, o):
            return s.__eq__(o)
    return A()

def test_wiggle_needs_reversals():
    d = WiggleDetector()
    # one straight fast sweep: 200px in ~50ms -> must NOT fire
    for i in range(4):
        assert d.feed(0.100 + i*0.016, 100 + i*80, 300) is False
    d2 = WiggleDetector()
    pts = [(0,0),(0,120),(0,10),(0,130)]             # x sweeps back and forth
    fired = [d2.feed(0.1 + i*0.03, 400 + p[1], 400 + p[0]) for i, p in enumerate(pts)]
    assert fired.count(True) == 1 and fired[-1]

def test_speed_measures_window():
    e = SpeedEstimator(window_s=0.05)
    t0 = 1000.0
    e.add(50, 0, t0); e.add(0, 50, t0 + 0.01)      # 100px flick inside window
    assert abs(e.speed(t0 + 0.02) - 5000) < 1      # 100px over 20ms span
    assert e.speed(t0 + 0.5) == 0.0                # aged out

# ---- heat: macOS-like "alive" accumulation ------------------------------

def _shake(d, t0, reversals, speed_px=100.0):
    fired = 0
    for i in range(reversals + 1):
        x = 400 + (i % 2) * speed_px
        if d.feed(t0 + i*0.04, x, 400):
            fired += 1
    return fired

def test_heat_rises_with_vigour():
    gentle = WiggleDetector(); wild = WiggleDetector()
    _shake(gentle, 0.0, 3, speed_px=95)     # ~2400 px/s reversals
    _shake(wild, 0.0, 7, speed_px=160)      # ~4000 px/s, more reversals
    assert wild.heat > gentle.heat > 0.1
    assert wild.heat <= 1.0                 # capped

def test_heat_decays_when_still():
    d = WiggleDetector()
    _shake(d, 0.0, 5)                       # 6 moves -> 4 velocity reversals
    h0 = d.heat
    for i in range(10):
        d.feed(1.0 + i*0.05, 400, 400)      # parked mouse, no motion
    assert 0.0 < d.heat < h0 * 0.7          # exponential decay, no refire
    assert d.rev_count == 4

def test_rev_count_sparks_stars():
    d = WiggleDetector(); _shake(d, 0.0, 5)
    assert d.rev_count == 4                 # monotonic, daemon diffs it

# ---- aura: spring follower, butter both directions ----------------------

def test_aura_follows_heat_smoothly():
    a = AuraMachine(peak_scale=2.2, start_scale=0.35)
    a.update(0.0, 0.0)
    prev = None; worst = 0.0
    for i in range(40):                     # heat snaps to 1.0 at t=0
        a.update(i * 0.008, 1.0)
        if prev is not None:
            worst = max(worst, abs(a.scale - prev))
        prev = a.scale
    assert a.scale > 2.0                    # reaches peak
    assert worst < 0.12                     # grows smooth, never jumps
def test_aura_shrinks_when_calm():
    a = AuraMachine(); a.update(0.0, 0.0)
    for i in range(60): a.update(i * 0.008, 1.0)          # fully grown
    peak = a.scale
    for i in range(120): a.update(0.5 + i * 0.008, 0.0)   # mouse calms
    assert a.scale < peak * 0.35 and a.alpha < 0.15       # shrinks back
    assert a.settled(1.6)

def test_aura_scales_between():
    a = AuraMachine(); a.update(0.0, 0.0)
    for i in range(40): a.update(i * 0.008, 0.3)          # gentle wiggle
    calm = a.scale
    for i in range(40): a.update(0.4 + i * 0.008, 1.0)    # then wild
    assert calm > 0.5 and a.scale > calm + 0.4            # proportional

def test_reduced_motion_no_scale_change():
    a = AuraMachine(profile="reduced"); a.update(0.0, 0.0)
    for i in range(60): a.update(i * 0.008, 1.0)
    assert a.scale == 1.0 and a.alpha > 0.9

# ---- starfield: Starlight's signature ------------------------------------

def test_stars_burst_and_live():
    s = StarField(n=10)
    s.burst(0.0); assert s.count == 10
    at = list(s.stars(0.3))
    assert len(at) == 10
    assert all(r > 8 for _, r, _, _, _ in at)           # spread outward
    assert all(0.0 < al <= 1.0 for *_, al in at)
    s.burst(0.4)
    assert len(list(s.stars(1.6))) >= 6                  # survivors keep flying
    assert len(list(s.stars(2.5))) == 0                  # all dead by 2.5s

def test_star_cap():
    s = StarField(n=40)
    for i in range(6): s.burst(i * 0.5)
    assert s.count <= 120

def test_pack_loading():
    import os
    from magic_core import load_packs, decode_frames, load_config
    cfg = load_config()
    assert cfg["stars"]["per_burst"] == 10
    assert cfg["wiggle"]["need"] == 2
    mo = cfg["motion"]
    assert 1.4 <= mo["peak_scale"] <= 3.0
    assert load_config.__doc__
    packs = load_packs(os.path.join(os.path.dirname(__file__), "packs"))
    assert set(packs) == {"anime"}
    fr, du = decode_frames(packs["anime"]["emotions"]["girl"]["path"])
    assert len(fr) == 8

if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("ok", fn.__name__)
    print("ALL PASS")
