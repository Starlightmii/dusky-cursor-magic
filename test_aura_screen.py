#!/usr/bin/env python3
"""Gate: EVENT-ONLY soul — measured from real screen pixels.
Rest: NO glow. Moving fast: NO glow. The ONLY light is the long-stay
supernova: park the pointer, wait out the 9-15s window, the detonation
must light the screen. Spawns its own soul under AURA_POS_FILE and
snapshots with grim, diffing against a no-soul baseline."""
import os, signal, subprocess, sys, time
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
POSF = "/tmp/aura_pos.txt"
env = {**os.environ, "XDG_RUNTIME_DIR": "/run/user/1000",
       "WAYLAND_DISPLAY": "wayland-1", "AURA_POS_FILE": POSF}
CXX, CY = 960, 540   # park point (far from edges/docks)


def put(x, y):
    with open(POSF, "w") as f:
        f.write(f"{x} {y}")


def snap():
    subprocess.run(["grim", "/tmp/_qa.png"], env=env, check=True)
    return np.array(Image.open("/tmp/_qa.png").convert("RGB")).astype(int)


def lit_pct(a, cx, cy, r0, r1):
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    d = np.hypot(xs - cx, ys - cy)
    m = (d >= r0) & (d < r1)
    return 100 * float((a[m].max(1) > 25).mean()) if m.any() else 0.0


def main():
    subprocess.run(["systemctl", "--user", "stop", "cursor-soul.service"],
                   check=True)                    # kill+restart race otherwise
    time.sleep(1.0)

    put(CXX, CY)
    base = snap()                      # no soul
    p = subprocess.Popen(["/usr/bin/python3", "-u",
                          os.path.join(HERE, "shader_soul.py")],
                         env=env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.STDOUT)
    try:
        put(CXX, CY); time.sleep(2.5)          # settle, pointer still
        rest = snap()
        end = time.monotonic() + 1.2
        while time.monotonic() < end:           # fast sweep, pointer moving
            put(CXX - 350, CY); time.sleep(1 / 60)
            put(CXX + 350, CY); time.sleep(1 / 60)
        fast = snap()
        # park out the full re-armed 9-15s window (motion re-arms it); the
        # nova flash (life < 1s) is sampled at 0.4s cadence so it can't hide
        put(CXX, CY)
        best = 0.0
        t_end = time.monotonic() + 22.0
        while time.monotonic() < t_end:
            time.sleep(0.15)
            a = np.abs(snap() - base)
            best = max(best, lit_pct(a, CXX, CY, 0, 220))
        rd = np.abs(rest - base); fd = np.abs(fast - base)
        rest_lit = lit_pct(rd, CXX, CY, 0, 160)
        fast_lit = lit_pct(fd, CXX, CY, 0, 160)
        print(f"rest-glow={rest_lit:.1f}% fast-glow={fast_lit:.1f}% "
              f"nova-glow={best:.1f}%")
        ok = rest_lit < 5 and fast_lit < 5 and best > 20
        print("EVENT-ONLY SOUL ->", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        os.kill(p.pid, signal.SIGTERM)
        time.sleep(0.5)
        # restart live soul fresh so it self-writes its pidfile
        subprocess.Popen(["/usr/bin/python3", "-u",
                          os.path.join(HERE, "shader_soul.py")],
                         stdout=open("/tmp/soul.log", "w"),
                         stderr=subprocess.STDOUT,
                         start_new_session=True, cwd=HERE)


if __name__ == "__main__":
    sys.exit(main())
