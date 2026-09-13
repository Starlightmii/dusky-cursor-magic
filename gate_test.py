#!/usr/bin/env /usr/bin/python3
"""Decisive click-through gate. Run as root (uinput)."""
import json, subprocess, time
from evdev import UInput, ecodes as e

ui = UInput({e.EV_REL: [e.REL_X, e.REL_Y], e.EV_KEY: [e.BTN_LEFT]}, name="gate-mouse")

def cur():
    return json.loads(subprocess.run(["hyprctl", "cursorpos", "-j"],
        capture_output=True, text=True).stdout)

def active():
    return json.loads(subprocess.run(["hyprctl", "activewindow", "-j"],
        capture_output=True, text=True).stdout)["class"]

def slow_move(tx, ty):
    j = cur(); dx, dy = tx - j["x"], ty - j["y"]
    n = max(1, int((abs(dx) + abs(dy)) / 40))
    for i in range(n):  # ~40px steps, slow => libinput accel ~1x
        ui.write(e.EV_REL, e.REL_X, round(dx * (i + 1) / n) - round(dx * i / n))
        ui.write(e.EV_REL, e.REL_Y, round(dy * (i + 1) / n) - round(dy * i / n))
        ui.syn(); time.sleep(0.045)

def click():
    time.sleep(0.12)
    ui.write(e.EV_KEY, e.BTN_LEFT, 1); ui.syn(); time.sleep(0.05)
    ui.write(e.EV_KEY, e.BTN_LEFT, 0); ui.syn(); time.sleep(0.15)

def overlay_rect():
    d = json.loads(subprocess.run(["hyprctl", "layers", "-j"],
        capture_output=True, text=True).stdout)
    for lvl in d["eDP-1"]["levels"].values():
        for l in lvl:
            if l["namespace"] == "dusky-cursor-magic":
                return l["x"], l["y"], l["x"] + l["w"], l["y"] + l["h"]
    return None

T = (1200, 600)  # inside foot(gatetest): 964..1913 x 50..1073
FIREFOX = (400, 300)

subprocess.run(["pkill", "-f", "/usr/bin/python3 spike.py"])
time.sleep(0.4)
subprocess.Popen(["setsid", "/usr/bin/python3", "spike.py"],
                 stdout=open("/tmp/gate_spike.log", "w"), stderr=subprocess.STDOUT)
time.sleep(1.5)

slow_move(*T)
time.sleep(0.5)
r = overlay_rect()
print("overlay rect:", r, "| T inside:", r and r[0] <= T[0] <= r[2] and r[1] <= T[1] <= r[3])
print("cursor now:", cur())

# 1) click on firefox area (no overlay there) -> firefox gains focus (mechanism sanity)
slow_move(*FIREFOX); click()
print("after firefox click, active:", active())

# 2) park overlay exactly on foot center, click -> pass = gatetest focuses
slow_move(*T)
time.sleep(0.5)
r = overlay_rect()
inside = r and r[0] <= T[0] <= r[2] and r[1] <= T[1] <= r[3]
print("rect recheck:", r, "inside:", inside)
click()
a = active()
print("after overlay click, active:", a)
print("GATE:", "PASS (click-through)" if a == "gatetest" else "FAIL (blocked)" )
