"""Draws 3 emotion GIFs into packs/default/ with Pillow.
/usr/bin/python3 make_placeholder_pack.py"""
import os
from PIL import Image, ImageDraw

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packs", "default")
os.makedirs(HERE, exist_ok=True)
FACE = {"anger": (255, 90, 90), "happy": (255, 210, 90), "blush": (255, 150, 190)}
for name, col in FACE.items():
    frames = []
    for i in range(8):
        im = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        r = 46 + (4 if i % 2 else 0)  # cheap heartbeat
        d.ellipse([64 - r, 64 - r, 64 + r, 64 + r], fill=col + (255,),
                  outline=(20, 20, 30, 255), width=4)
        ex = 24 if name != "anger" else 30
        for sx in (-1, 1):
            d.ellipse([64 + sx * ex - 6, 52 - 6, 64 + sx * ex + 6, 52 + 6],
                      fill=(20, 20, 30, 255))
        if name == "anger":
            d.line([44, 34, 60, 42], fill=(20, 20, 30, 255), width=4)
            d.line([84, 34, 68, 42], fill=(20, 20, 30, 255), width=4)
            d.arc([48, 70, 80, 94], 200, 340, fill=(20, 20, 30, 255), width=4)
        elif name == "blush":
            d.arc([48, 66, 80, 88], 20, 160, fill=(20, 20, 30, 255), width=4)
            for sx in (-1, 1):
                d.ellipse([64 + sx * 34 - 10, 62, 64 + sx * 34 + 10, 72],
                          fill=(255, 80, 120, 160))
        else:
            d.arc([48, 62, 80, 90], 20, 160, fill=(20, 20, 30, 255), width=4)
        frames.append(im)
    frames[0].save(os.path.join(HERE, name + ".gif"), save_all=True,
                   append_images=frames[1:], duration=80, loop=0)

with open(os.path.join(HERE, "manifest.json"), "w") as f:
    f.write('{"emotions": {"anger": {"type": "gif", "path": "anger.gif"},'
            ' "happy": {"type": "gif", "path": "happy.gif"},'
            ' "blush": {"type": "gif", "path": "blush.gif"}}}')
print("built:", sorted(os.listdir(HERE)))
