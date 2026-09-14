#!/usr/bin/env python3
"""Gate: the aura must GROW with pointer speed, measured from real screen
pixels. Spawns its own shader_soul under AURA_POS_FILE (deterministic seam),
rests it, snaps, sweeps 700px/tick, snaps, compares lit-ring coverage."""
import os, signal, socket, subprocess, sys, time
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
POSF = "/tmp/aura_pos.txt"
env = {**os.environ, "XDG_RUNTIME_DIR": "/run/user/1000",
       "WAYLAND_DISPLAY": "wayland-1", "AURA_POS_FILE": POSF}
SIG = os.listdir("/run/user/1000/hypr")[0]


def hypr(msg):
    s = socket.socket(socket.AF_UNIX)
    s.connect(f"/run/user/1000/hypr/{SIG}/.socket.sock")
    s.sendall(msg.encode()); r = s.recv(4096).decode(); s.close()
    return r


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
    return 100 * float((a[m].max(1) > 40).mean()) if m.any() else 0.0


def main():
    # stop any live soul so only OUR instance draws (two layers flood the
    # field and saturate both baselines -> growth always reads 0)
    pidf = os.path.expanduser("~/.cache/cursor-magic/soul.pid")
    stopped = False
    try:
        pid = int(open(pidf).read().strip())
        if open(f"/proc/{pid}/comm").read().strip() == "python3":
            os.kill(pid, signal.SIGTERM)
            stopped = True
            time.sleep(0.7)
    except (OSError, ValueError):
        pass
    # center of screen, far from any dock/panel noise: 960,540
    put(960, 540)
    p = subprocess.Popen(["/usr/bin/python3", "-u",
                          os.path.join(HERE, "shader_soul.py")],
                         env=env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.STDOUT)
    try:
        time.sleep(2.5)                      # settle: speed -> ~0
        rest = snap()
        # sweep: alternate +/-350px at 60fps => ~700px/tick => speed pins 1.0
        end = time.monotonic() + 1.2
        while time.monotonic() < end:
            put(610, 540); time.sleep(1 / 60)
            put(1310, 540); time.sleep(1 / 60)
        fast = snap()
        cx, cy = 1310, 540
        rr = [round(lit_ring(rest, cx, cy, r, r + 40)) for r in (0, 40, 80, 120)]
        fr = [round(lit_ring(fast, cx, cy, r, r + 40)) for r in (0, 40, 80, 120)]
        print("rest rings %:", rr)
        print("fast rings %:", fr)
        outer_rest = lit_ring(rest, cx, cy, 80, 160)
        outer_fast = lit_ring(fast, cx, cy, 80, 160)
        ok = outer_fast > outer_rest + 5
        print(f"OUTER GROWTH rest={outer_rest:.1f}% fast={outer_fast:.1f}% ->",
              "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        os.kill(p.pid, signal.SIGTERM)
        if stopped:   # put the live soul back
            subprocess.Popen(["/usr/bin/python3", "-u",
                              os.path.join(HERE, "shader_soul.py")],
                             stdout=open("/tmp/soul.log", "w"),
                             stderr=subprocess.STDOUT,
                             start_new_session=True, cwd=HERE)


if __name__ == "__main__":
    sys.exit(main())
