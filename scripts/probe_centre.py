import subprocess, time, numpy as np
from PIL import Image
# warp pointer to screen centre via hyprctl, then probe
subprocess.run(["hyprctl","dispatch","mousemove","960","540"])
time.sleep(1.2)
subprocess.run(["grim","/tmp/probe.png"])
a = np.array(Image.open("/tmp/probe.png").convert("RGBA")).astype(int)
c = a[540-40:540+40, 960-40:960+40, :3]
px = a[540,960,:3]
print("center px:", tuple(px))
print("box-max:", tuple(c.reshape(-1,3).max(0)), " box-min:", tuple(c.reshape(-1,3).min(0)))
# a lit cursor should show a bright blob near (960,540)
bright = (c.sum(2) > 200).sum()
print("bright px within 40:", bright)
