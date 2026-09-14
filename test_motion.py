#!/usr/bin/env python3
"""Regression gates for the motion upgrades (U1-U8 public behaviour).
Keeps the butter honest: energy must melt, spring must stay in the
KWin-tight band, burst size must actually scale. Run:
    /usr/bin/python3 test_motion.py  -> MOTION OK
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from magic_core import AuraMachine, StarField


def t_u1_energy_melts():
    a = AuraMachine()
    t = 0.0
    for _ in range(60):          # violent flick
        t += 1 / 120; a.update(t, 1.0)
    assert a.energy > 0.8, f"energy did not heat: {a.energy}"
    for _ in range(int(2.7 * 120)):   # calm 2.7 s
        t += 1 / 120; a.update(t, 0.0)
    assert a.energy < 0.35, f"energy did not decay: {a.energy}"


def t_u3_spring_band():
    p = AuraMachine.PROFILES["macos"]
    assert p["k"] >= 220.0, p          # tightened from 180 (t95 ~250ms)
    assert p["zeta"] < 0.95, p         # <1 keeps a hair of life, no pop


def t_u2_burst_scales():
    s1, s2 = StarField(), StarField()
    s1.burst(0.0, 8, size=0.6)
    s2.burst(0.0, 8, size=2.8)
    big1 = max(st[3] for st in s1._stars)
    big2 = max(st[3] for st in s2._stars)
    assert big2 > big1, (big1, big2)   # size multiplier must reach frame size


def t_reduced_motion():
    a = AuraMachine(profile="reduced")
    t = 0.0
    for _ in range(60):
        t += 1 / 120; a.update(t, 1.0)
    assert a.scale == 1.0, "reduced-motion must pin scale"


def t_c3_playback_scales():
    """Cycle-3: playback rate rises with energy+speed, clamps at cap,
    is exactly base at rest (default no-op), and reduced-motion never boosts."""
    from magic_core import playback_boost
    rest = playback_boost(0.0, 0.0)
    assert abs(rest - 1.0) < 1e-9, rest            # no-op at rest
    fast = playback_boost(1.0, 4000.0)
    mid = playback_boost(0.5, 2000.0)
    assert rest < mid < fast, (rest, mid, fast)   # monotone in both terms
    assert fast <= 2.5, fast                      # clamp per brief
    assert playback_boost(10.0, 99999.0) == 2.5  # clamps hard on garbage
    assert playback_boost(0.3, 500.0, base=1.5) > 1.5   # base configures floor


def t_c4_ambient_curve():
    """Cycle-4: glide speed -> perceptible butter ramp (1.3-2.2x at typical
    glides), smooth monotone, no-op at rest, legacy-linear reproducible."""
    from magic_core import ambient_gain, AuraMachine, load_config
    cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "config.default.json"))
    am = cfg["ambient"]; mo = cfg["motion"]
    # rest & dead-zone
    assert ambient_gain(0.0, **am_keys(am)) == 0.0
    assert ambient_gain(am["min_speed"], **am_keys(am)) == 0.0
    # monotone across the whole band
    prev = -1.0
    for sp in range(int(am["min_speed"]) + 1, 6000, 250):
        g = ambient_gain(sp, **am_keys(am))
        assert g >= prev, (sp, g, prev)
        prev = g
    assert g <= am["max_gain"] + 1e-9
    # perceptible: steady-state scale at a 500 px/s glide inside 1.3-2.2x
    a = AuraMachine(peak_scale=mo["peak_scale"], start_scale=mo["start_scale"],
                    profile="macos")
    t = 0.0
    for _ in range(int(2.5 * 120)):
        t += 1 / 120
        a.update(t, 0.0, ambient_gain(500.0, **am_keys(am)))
    assert 1.3 <= a.scale <= 2.2, f"500px/s glide scale {a.scale}"
    # high speed approaches the ceiling but never overshoots peak
    a2 = AuraMachine(peak_scale=mo["peak_scale"], start_scale=mo["start_scale"],
                     profile="macos")
    t = 0.0
    for _ in range(int(2.5 * 120)):
        t += 1 / 120
        a2.update(t, 0.0, ambient_gain(4000.0, **am_keys(am)))
    assert a2.scale <= a2.peak + 1e-9
    # legacy: gamma=1 with old params reproduces the old linear ramp
    lin = ambient_gain(1050.0, min_speed=150.0, speed_range=900.0,
                       gamma=1.0, max_gain=0.35)
    assert abs(lin - 0.35) < 1e-9, lin


def am_keys(am):
    return {k: am[k] for k in ("min_speed", "speed_range", "gamma", "max_gain")}


if __name__ == "__main__":
    for fn in (t_u1_energy_melts, t_u3_spring_band, t_u2_burst_scales,
               t_reduced_motion, t_c3_playback_scales, t_c4_ambient_curve):
        fn()
        print("ok", fn.__name__)
    print("MOTION OK")
