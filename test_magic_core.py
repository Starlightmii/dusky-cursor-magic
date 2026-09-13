"""Zero-dep asserts: /usr/bin/python3 test_magic_core.py  (or pytest)."""
import math
from magic_core import SpeedEstimator, BurstMachine


def approx(v, tol=1e-6):
    class A:
        def __eq__(s, o):
            return abs(o - v) <= tol
        def __req__(s, o):
            return s.__eq__(o)
    return A()

def test_wiggle_needs_reversals():
    from magic_core import WiggleDetector
    d = WiggleDetector()
    # one straight fast sweep: 200px in ~50ms -> must NOT fire
    for i in range(4):
        assert d.feed(0.100 + i*0.016, 100 + i*80, 300) is False
    d2 = WiggleDetector()
    # left-right-left wiggle at >=900 px/s -> fires exactly once
    # (plan fix: last reversal is the firing sample, so drop the trailing
    #  point that would fire it mid-gesture and assert fired[-1])
    pts = [(0,0),(0,120),(0,10),(0,130)]             # x sweeps back and forth
    fired = [d2.feed(0.1 + i*0.03, 400 + p[1], 400 + p[0]) for i, p in enumerate(pts)]
    assert fired.count(True) == 1 and fired[-1]

def test_speed_measures_window():
    e = SpeedEstimator(window_s=0.05)
    t0 = 1000.0
    e.add(50, 0, t0); e.add(0, 50, t0 + 0.01)      # 100px flick inside window
    assert abs(e.speed(t0 + 0.02) - 5000) < 1      # 100px over 20ms span
    assert e.speed(t0 + 0.5) == 0.0                # aged out

def test_burst_lifecycle():
    m = BurstMachine(hold_s=1.0, enter_s=0.25, exit_s=0.3, cooldown_s=0.2,
                     peak_scale=1.8, start_scale=0.35)
    m.trigger(0.0)
    assert m.update(0.0)[0] == "enter"
    assert m.update(0.10)[0] == "enter" and 0.0 < m.alpha < 1.0 and 0.35 < m.scale < 1.8
    assert m.update(0.30)[0] == "hold"  and m.alpha > 0.99 and abs(m.scale - 1.8) < 0.1
    assert m.update(1.40)[0] == "exit"
    assert m.update(1.75)[0] == "idle"  and m.alpha == 0.0

def test_no_refire_during_burst():
    m = BurstMachine(hold_s=1.0, enter_s=0.25, exit_s=0.3, cooldown_s=0.2)
    m.trigger(0.0); m.trigger(0.1)                 # 2nd ignored while active
    assert m.update(0.15)[0] == "enter"            # still first burst
    # burst ends at 0.25+1.0+0.3 = 1.55, cooldown 0.2 -> no re-arm before 1.75
    assert m.update(1.6)[0] == "idle"              # advance past end
    assert m.trigger(1.6) is False                 # inside cooldown
    assert m.trigger(2.1) is True                  # cooldown passed
    assert m.update(2.15)[0] == "enter"

def test_scale_continuous_across_phases():
    m = BurstMachine(hold_s=1.0, enter_s=0.25, exit_s=0.3, cooldown_s=0.2)
    m.trigger(0.0)
    prev = None; worst = 0.0
    for i in range(220):
        m.update(i * 0.008)   # daemon ticks at 8ms now (tick_ms=8)
        if m.alpha > 0.02:    # only judge motion while actually visible
            if prev is not None:
                worst = max(worst, abs(m.scale - prev))
            prev = m.scale
        else:
            prev = None
    assert worst < 0.10          # grow from 0.35->1.8: steeper than old settle, but invisible while alpha~0 (see footprint test)

# ---- I1: envelope grows from cursor size, smooth shrink, ring, reduced ----

def test_envelope_grows_from_start_scale():
    m = BurstMachine(enter_s=0.35, hold_s=1.4, exit_s=0.28, peak_scale=1.8,
                     start_scale=0.35, profile="macos")
    m.trigger(0.0)
    assert m.update(0.0)[2] == approx(0.35)
    prev = None
    for i in range(0, 44):                 # through all of enter
        m.update(i * 0.008)
        if prev is not None:
            assert m.scale >= prev - 1e-9  # monotonic grow
        prev = m.scale
    assert m.update(0.35)[2] == approx(1.8, 0.05)

def test_exit_shrinks_back_and_fades():
    m = BurstMachine(enter_s=0.35, hold_s=1.4, exit_s=0.28, peak_scale=1.8,
                     start_scale=0.35, profile="macos")
    m.trigger(0.0)
    m.update(0.4)
    assert m.state == "hold" and m.scale > 1.7
    m.update(0.35 + 1.4 + 0.14)            # mid exit
    assert m.state == "exit" and 0.6 < m.scale < 1.8 and 0.0 < m.alpha < 1.0
    m.update(0.35 + 1.4 + 0.28)            # end exit -> idle
    assert m.state == "idle" and m.alpha == 0.0

def test_visible_footprint_continuous():
    # what the eye sees = scale*alpha; no step > 0.12 at 8ms ticks
    m = BurstMachine(enter_s=0.35, hold_s=1.4, exit_s=0.28, peak_scale=1.8,
                     start_scale=0.35, profile="macos")
    m.trigger(0.0)
    prev = None; worst = 0.0
    for i in range(260):
        m.update(i * 0.008)
        f = m.scale * m.alpha
        if prev is not None:
            worst = max(worst, abs(f - prev))
        prev = f
    assert worst < 0.12

def test_ring_expands_on_enter_then_gone():
    m = BurstMachine(enter_s=0.35, hold_s=1.4, exit_s=0.28, peak_scale=1.8,
                     start_scale=0.35, profile="macos", ring=True)
    m.trigger(0.0)
    m.update(0.175)
    assert 0.3 < m.ring < 0.8 and m.ring_alpha > 0.0
    m.update(0.4)                          # hold: ring finished, faded
    assert m.ring_alpha == 0.0
    m2 = BurstMachine(profile="macos", ring=False); m2.trigger(0); m2.update(0.1)
    assert m2.ring_alpha == 0.0

def test_reduced_profile_alpha_only():
    m = BurstMachine(enter_s=0.35, hold_s=1.4, exit_s=0.28, peak_scale=1.8,
                     start_scale=0.35, profile="reduced")
    m.trigger(0.0)
    m.update(0.1)
    assert m.scale == 1.0                  # no movement at all
    assert 0.0 < m.alpha < 1.0
    m.update(0.36)
    assert m.scale == 1.0 and approx(1.0, 0.01) == m.alpha

def test_breathe_scales_with_config():
    def mk(b):
        m = BurstMachine(enter_s=0.35, hold_s=1.4, exit_s=0.28, peak_scale=1.8,
                         start_scale=0.35, profile="macos", breathe_sine=b)
        m.trigger(0.0)
        for _ in range(6):                 # settle: avoid sine trough start
            m.update(0.36 + _ * 0.02)
        vals = []
        for i in range(160):                       # stay inside hold (0.35..1.75)
            m.update(0.37 + i * 0.008)
            vals.append(m.scale)
        return max(vals) - min(vals)
    assert mk(0.0) < 0.005                 # config 0 = no wobble
    assert 0.02 < mk(1.0) < 0.12           # default: ~3% of peak visible

def test_pack_loading():
    import os
    from magic_core import load_packs, decode_frames, load_config
    assert load_config()["wiggle"]["need"] == 2
    mo = load_config()["motion"]
    assert mo["profile"] in ("macos", "smooth", "snappy", "auto")
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
