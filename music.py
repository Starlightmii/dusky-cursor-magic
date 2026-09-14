"""music — PipeWire monitor tap + beat/band analyser for the soul.

pw-record streams the speakers' monitor node as raw f32 mono @12kHz into a
background reader thread; poll() returns smoothed (bass, mid, treble) in
[0,1] plus a beat strength from adaptive-peak spectral flux. No playback?
All zeros, active=False — the soul just behaves normally.

Bands (12k bin = 11.7Hz): bass 30-150Hz, mid 300-2000, treble 4-9kHz.
ponytail: fixed bin sums, no mel scale — visuals don't need pitch accuracy.
"""
import collections
import math
import subprocess
import threading

import numpy as np

RATE = 12000
N = 2048                      # window: ~170ms — 45Hz kick needs ~4 cycles
TARGET = "alsa_output.pci-0000_00_1f.3.analog-stereo.monitor"


def _target():
    return default_monitor() or TARGET


def _bins(lo, hi):
    return int(lo * N / RATE), int(hi * N / RATE) + 1


BASS, MID, TREB = _bins(30, 150), _bins(300, 2000), _bins(4000, 9000)


def default_monitor():
    """Monitor node of PipeWire's default sink; None if no audio device."""
    try:
        import subprocess
        name = subprocess.run(
            ["wpctl", "get-status", "/defaults/audio-sink"],
            capture_output=True, text=True, timeout=2).stdout
        node = None
        for line in name.splitlines():
            if "Audio Sink" in line and "Monitor" not in line:
                node = line.split("]")[0].strip(" [")
                break
        if not node:
            return None
        for line in subprocess.run(["wpctl", "status", str(node)],
                                   capture_output=True, text=True,
                                   timeout=2).stdout.splitlines():
            if ".monitor" in line:
                return line.split(None, 1)[1].strip()
    except Exception:
        pass
    return None


class Music:
    def __init__(self, target=None):
        self.target = target or _target()
        self._ring = np.zeros(N * 2, np.float32)
        self._fill = [0]
        self._lock = threading.Lock()
        self._proc = None
        self._alive = False
        self._flux = collections.deque(maxlen=32)
        self._bands = np.zeros(3, np.float32)   # smoothed
        self._peak = np.full(3, 0.05)           # rolling loudness normaliser
        self._pk_age = 0.0
        self.beat = 0.0                         # 0..1+ strength, decays fast
        self.bpm = 0.0
        self._last_beat = -9.0
        self._ivls = collections.deque(maxlen=8)
        self.t = 0.0

    # ---- capture ----------------------------------------------------------
    def start(self):
        try:
            self._proc = subprocess.Popen(
                ["pw-record", "-a", "--rate", str(RATE), "--channels", "1",
                 "--format", "f32", "--target", self.target, "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return False
        th = threading.Thread(target=self._pump, daemon=True)
        th.start()
        return True

    def _pump(self):
        assert self._proc is not None and self._proc.stdout is not None
        stream = self._proc.stdout
        step = N // 2                           # 50% hop
        while True:
            try:
                raw = stream.read(step * 4)
            except (OSError, ValueError):
                break
            if len(raw) < step * 4:
                break                           # node gone / process died
            x = np.frombuffer(raw, np.float32)
            with self._lock:
                self._ring = np.roll(self._ring, -step)
                self._ring[-len(x):] = x
                self._alive = True

    def stop(self):
        if self._proc:
            self._proc.terminate()

    # ---- analysis ---------------------------------------------------------
    def poll(self, now):
        """Returns (bass, mid, treble, beat). Call once per frame."""
        if not self._alive:
            return 0.0, 0.0, 0.0, 0.0
        if now - self.t < 0.02:                      # return held values,
            bb, mb, tb = self._bands                 # never flicker to 0
            return float(bb), float(mb), float(tb), float(self.beat)
        self.t = now
        with self._lock:
            x = self._ring[-N:].copy()
        sp = np.abs(np.fft.rfft(x * np.hanning(N)))
        e = (sp[BASS[0]:BASS[1]].max(), sp[MID[0]:MID[1]].max(),
             sp[TREB[0]:TREB[1]].max())
        raw = np.array(e, np.float32)
        self.raw = raw                          # test hook + debug
        self._pk_age += 0.02
        self._peak = np.maximum(self._peak * 0.9995, raw)   # slow leak
        b = np.clip(raw / (self._peak + 1e-6), 0, 4)
        self._bands = self._bands * 0.70 + b * 0.30         # ~140ms attack
        # onset: bass rising vs its own recent mean (works for soft attacks
        # too; refractory is the anti-double-trigger, not an absolute gate)
        bass_now = raw[0]
        prev = self._flux[-1] if self._flux else bass_now
        self._flux.append(bass_now)
        mean = sum(self._flux) / len(self._flux)
        rise = bass_now > prev and bass_now > mean * 1.25 + 0.02
        beat = 0.0
        if rise and now - self._last_beat > 0.22:     # refractory 272bpm
            iv = now - self._last_beat
            if 0.25 < iv < 2.0:
                self._ivls.append(iv)
                med = sorted(self._ivls)[len(self._ivls) // 2]
                self.bpm = 60.0 / med
            self._last_beat = now
            beat = min(2.0, bass_now / max(mean, 1e-6) * 0.28)
        self.beat = max(beat, self.beat * 0.85)
        bb, mb, tb = self._bands
        return float(bb), float(mb), float(tb), float(self.beat)
