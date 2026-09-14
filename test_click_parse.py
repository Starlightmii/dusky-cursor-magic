#!/usr/bin/env python3
"""Gate: evdev click parsing on synthetic bytes — the 'clicks never fire'
regression class. Uses clicks.EVPACK so the fixture follows the real ABI."""
import struct, sys
sys.path.insert(0, ".")
from clicks import parse, EVENT, EVPACK, BTN

def ev(t, code, val, sec=1.0):
    return struct.pack(EVPACK, int(sec), int((sec % 1) * 1e9), t, code, val, 0)

assert len(ev(1, 2, 3)) == EVENT, f"pack size {len(ev(1,2,3))} != EVENT {EVENT}"
# a left press+release, EV_KEY=1
out = parse(ev(1, 0x110, 1) + ev(1, 0x110, 0))
kinds = [(c, v) for (_, _, c, v) in out]
assert kinds == [(0x110, 1), (0x110, 0)], kinds
# EV_SYN / EV_REL noise between clicks must not become clicks
out = parse(ev(1, 0x111, 1) + ev(0, 0, 0, 1.5) + ev(2, 0, 40, 1.6))
assert [(c, v) for (_, _, c, v) in out if c in (0x110, 0x111)] == [(0x111, 1)]
print("CLICK-PARSE OK")
