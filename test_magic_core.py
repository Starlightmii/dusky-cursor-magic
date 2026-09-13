"""Zero-dep asserts: /usr/bin/python3 test_magic_core.py  (or pytest)."""
import math
from magic_core import SpeedEstimator, BurstMachine, elastic_burst

def test_speed_measures_window():
    e = SpeedEstimator(window_s=0.05)
    t0 = 1000.0
    e.add(50, 0, t0); e.add(0, 50, t0 + 0.01)      # 100px flick inside window
    assert abs(e.speed(t0 + 0.02) - 5000) < 1      # 100px over 20ms span
    assert e.speed(t0 + 0.5) == 0.0                # aged out

def test_burst_lifecycle():
    m = BurstMachine(threshold=100, cooldown_s=0.2, hold_s=1.0, shrink_s=0.5)
    assert m.update(0.0, 500)[0] == "burst"        # crosses threshold -> arm
    st, p = m.update(0.5, 10); assert st == "burst" and abs(p - 0.5) < 0.06
    st, p = m.update(1.2, 10); assert st == "shrink"
    st, p = m.update(2.0, 10); assert st == "idle"
    assert m.update(2.1, 500)[0] == "burst"        # re-fires after cooldown

def test_no_refire_during_burst():
    m = BurstMachine(threshold=100, cooldown_s=0.2)
    m.update(0.0, 500); assert m.update(0.3, 500)[0] == "burst"  # still holding

def test_spring_curve():
    assert math.isclose(elastic_burst(0.0), 0.0, abs_tol=1e-9)
    assert math.isclose(elastic_burst(1.0), 1.0, abs_tol=1e-9)
    mid = [elastic_burst(i / 50) for i in range(50)]  # below 1.0 only
    assert max(mid) > 1.05                           # must overshoot (macOS feel)

def test_pack_loading():
    import os
    from magic_core import load_packs, decode_frames
    packs = load_packs(os.path.join(os.path.dirname(__file__), "packs"))
    assert "default" in packs
    fr, du = decode_frames(packs["default"]["emotions"]["anger"]["path"])
    assert len(fr) == 8 and abs(du[0] - 0.08) < 0.01

if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("ok", fn.__name__)
    print("ALL PASS")
