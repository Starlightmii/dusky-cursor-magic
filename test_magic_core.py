"""Zero-dep asserts: /usr/bin/python3 test_magic_core.py  (or pytest)."""
import math
from magic_core import SpeedEstimator, BurstMachine, elastic_burst

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
    m = BurstMachine(hold_s=1.0, enter_s=0.25, exit_s=0.3, cooldown_s=0.2)
    m.trigger(0.0)
    assert m.update(0.0)[0] == "enter"
    assert m.update(0.10)[0] == "enter" and 0.0 < m.alpha < 1.0 and 0.8 <= m.scale <= 1.05
    assert m.update(0.30)[0] == "hold"  and m.alpha > 0.99 and abs(m.scale - 1.0) < 0.05
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
        m.update(i * 0.01)
        if prev is not None:
            worst = max(worst, abs(m.scale - prev))
        prev = m.scale
    assert worst < 0.05          # no 3am "pop" between phases

def test_spring_curve():
    assert math.isclose(elastic_burst(0.0), 0.0, abs_tol=1e-9)
    assert math.isclose(elastic_burst(1.0), 1.0, abs_tol=1e-9)
    mid = [elastic_burst(i / 50) for i in range(50)]  # below 1.0 only
    assert max(mid) > 1.05                           # must overshoot (macOS feel)

def test_pack_loading():
    import os
    from magic_core import load_packs, decode_frames, load_config
    assert load_config()["wiggle"]["need"] == 2
    assert load_config.__doc__
    packs = load_packs(os.path.join(os.path.dirname(__file__), "packs"))
    assert set(packs) == {"anime"}
    fr, du = decode_frames(packs["anime"]["emotions"]["girl"]["path"])
    assert len(fr) == 8

if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("ok", fn.__name__)
    print("ALL PASS")
