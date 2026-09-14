#!/usr/bin/env python3
"""Gate: the soul field must GROW with pointer speed, measured from real
screen pixels. Spawns its own shader_soul under AURA_POS_FILE (deterministic
seam), snaps a no-soul baseline, rests, sweeps 700px/tick, compares lit-ring
coverage of (frame - baseline) so desktop content under the test point can
never saturate the metric."""
import os, signal, subprocess, sys, time
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
POSF = "/tmp/aura_pos.txt"
env = {**os.environ, "XDG_RUNTIME_DIR": "/run/user/1000",
       "WAYLAND_DISPLAY": "wayland-1", "AURA_POS_FILE": POSF}
CXX, CY = 960, 540   # sweep center (far from edges/docks)


def put(x, y):
    with open(POSF, "w") as f:
        f.write(f"{x} {y}")


def snap():
    subprocess.run(["grim", "/tmp/_qa.png"], env=env, check=True)
    return np.array(Image.open("/tmp/_qa.png").convert("RGB")).astype(int)


def lit_ring(a, cx, cy, r0, r1):
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    d = np.hypot(xs - cx, ys - cy)
    m = (d >= r0) & (d < r1)
    return 100 * float((a[m].max(1) > 25).mean()) if m.any() else 0.0


def main():
    pidf = os.path.expanduser("~/.cache/cursor-magic/soul.pid")
    def stop_live():
        try:
            pid = int(open(pidf).read().strip())
            if open(f"/proc/{pid}/comm").read().strip() == "python3":
                os.kill(pid, signal.SIGTERM)
                return True
        except (OSError, ValueError):
            pass
        return False
    stopped = stop_live()
    put(CXX, CY)
    time.sleep(0.4)
    base = snap()                        # no soul drawing
    p = subprocess.Popen(["/usr/bin/python3", "-u",
                          os.path.join(HERE, "shader_soul.py")],
                         env=env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.STDOUT)
    try:
        time.sleep(2.5)                  # settle: speed -> ~0
        rest = snap()
        end = time.monotonic() + 1.2
        while time.monotonic() < end:
            put(CXX - 350, CY); time.sleep(1 / 60)
            put(CXX + 350, CY); time.sleep(1 / 60)
        fast = snap()
        rd = np.abs(rest - base); fd = np.abs(fast - base)
        rr = [round(lit_ring(rd, CXX, CY, r, r + 40)) for r in (0, 40, 80, 120)]
        fr = [round(lit_ring(fd, CXX, CY, r, r + 40)) for r in (0, 40, 80, 120)]
        print("rest rings %:", rr)
        print("fast rings %:", fr)
        outer_rest = lit_ring(rd, CXX, CY, 80, 160)
        outer_fast = lit_ring(fd, CXX, CY, 80, 160)
        ok = outer_fast > outer_rest + 5
        print(f"OUTER GROWTH rest={outer_rest:.1f}% fast={outer_fast:.1f}% ->",
              "PASS" if ok else "FAIL")
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
