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


if __name__ == "__main__":
    for fn in (t_u1_energy_melts, t_u3_spring_band, t_u2_burst_scales,
               t_reduced_motion):
        fn()
        print("ok", fn.__name__)
    print("MOTION OK")
