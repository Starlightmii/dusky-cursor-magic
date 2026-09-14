import subprocess, numpy as np
from PIL import Image
cp = subprocess.run(["hyprctl","cursorpos"],capture_output=True,text=True).stdout
cx,cy = [int(x) for x in cp.split(",")][:2]
subprocess.run(["grim","/tmp/now.png"])
a = np.array(Image.open("/tmp/now.png").convert("RGBA")).astype(int)
print("cursor at",cx,cy)
for name,(dx,dy) in {"core":(0,0),"ring":(14,0),"glow":(30,0)}.items():
    x,y = cx+dx, cy+dy
    box = a[max(0,y-6):y+6,max(0,x-6):x+6,:3].reshape(-1,3).max(0)
    print(f"{name}: rgb={tuple(a[y,x,:3])} box-max={tuple(box)}")
