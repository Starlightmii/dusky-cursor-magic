"""Synthetic 128bpm track -> analyser must see bass dominate + beat on the
quarter-note grid. Fails if flux logic, bands, or refractory break."""
import math
import sys

import numpy as np

sys.path.insert(0, "/home/starlight/Projects/dusky-cursor-magic")
from music import Music

m = Music()
m._alive = True
sr = 12000
beat_sr = sr / 128.0 * 60.0                # 4687.5 samples per beat
track = np.zeros(sr * 8, np.float32)
k = np.arange(int(beat_sr * 0.28))
kick = (np.sin(2 * math.pi * 45 * k / sr) * np.exp(-k / (sr * 0.05))
        + 0.25 * np.exp(-k / (sr * 0.004)))          # click = broadband onset
for b in range(14):
    i = int(b * beat_sr)
    track[i:i + len(k)] += kick * 0.8
hat = np.random.uniform(-0.05, 0.05, int(beat_sr * 0.06)).astype(np.float32)
for b in range(24):                                   # 8ths
    i = int(b * beat_sr / 2) + int(beat_sr / 4)
    track[i:i + len(hat)] += hat

pos = 0
now = 0.0
prev_beat = 0.0
beats = []
bass_max = mid_max = 0.0
while now < 6.0:
    with m._lock:
        m._ring = np.roll(m._ring, -600)
        n = min(600, len(track) - pos)
        m._ring[-n:] = track[pos:pos + n]
    pos += 600
    now += 600 / sr
    bb, mb, tb, beat = m.poll(now)
    bass_max, mid_max = max(bass_max, m.raw[0]), max(mid_max, m.raw[1])
    if beat > 0.3 and beat > prev_beat:               # rising edge = onset
        beats.append(now)
    prev_beat = beat

# 12 kicks in 6s at 128bpm -> expect >=10 detections (refractory may swallow 1-2)
assert len(beats) >= 9, f"beats={len(beats)}: {beats}"
gaps = np.diff(beats)
assert abs(gaps.mean() - beat_sr / sr) < 0.05, f"off-grid: mean gap {gaps.mean():.3f}"
assert bass_max > mid_max * 1.2 and bass_max > 0.5, \
    f"bands wrong: bass={bass_max:.2f} mid={mid_max:.2f}"
assert 120 < m.bpm < 140, f"bpm={m.bpm}"
print(f"BEAT TEST OK — {len(beats)} beats on grid, bpm={m.bpm:.1f}, "
      f"bass={bass_max:.2f} mid={mid_max:.2f}")
