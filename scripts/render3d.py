#!/usr/bin/python3
"""Pre-render a real-3D-looking turntable sprite for the 2D cairo overlay.

Offline math only (zero runtime cost): perspective-project an extruded
4-point star "chibi sigil", painter's algorithm, Lambert + rim shading,
additive bloom. Stdlib + PIL.

Usage:  /usr/bin/python3 scripts/render3d.py [--verify]
Out:    packs/sigil3d/frames/f00..f23.png  RGBA 128px transparent bg
"""
import math
import os
import sys
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.normpath(os.path.join(HERE, "..", "packs", "sigil3d"))
FRAMES_DIR = os.path.join(PACK, "frames")

OUT = 128            # final sprite size
SS = 3               # supersample (384 render -> LANCZOS -> 128): no jaggies
CANVAS = OUT * SS
N_FRAMES = 24
FOCAL, CAM_Z, PPU = 5.0, 9.0, 135.0       # persp strength, camera z, px/unit
TILT = -0.16                              # fixed x-tilt: shows top bevel, 3/4 view
R_OUT, R_IN, HZ = 1.0, 0.30, 0.12         # star outer/inner radius, half-thick
GEM = (0.22, 0.22, HZ + 0.001)            # chibi highlight diamond, off-axis
GEM_R = 0.14
BASE = (148, 108, 216)                    # amethyst face
GLOW = (196, 150, 255)                    # bloom tint
L = (0.45, -0.55, 0.70)              # key light (upper-left, toward cam)


def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def star_ring():
    pts = []
    for i in range(8):
        a = -math.pi / 2 + i * math.pi / 4   # tip at top
        r = R_OUT if i % 2 == 0 else R_IN
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


RING = star_ring()


def yaw(pts, th):
    c, s = math.cos(th), math.sin(th)
    ct, st = math.cos(TILT), math.sin(TILT)
    out = []
    for (x, y, z) in pts:
        x1, z1 = x * c + z * s, -x * s + z * c
        out.append((x1, y * ct - z1 * st, y * st + z1 * ct))
    return out


def project(p):
    k = FOCAL / (CAM_Z - p[2])
    return (CANVAS / 2 + p[0] * k * PPU, CANVAS / 2 - p[1] * k * PPU, p[2])


def shade(n):
    d = max(0.0, n[0] * L[0] + n[1] * L[1] + n[2] * L[2])
    rim = 0.38 * max(0.0, -n[2])            # edge light when faces turn away
    b = 0.30 + 0.70 * d + rim
    return tuple(min(255, int(c * b + 14 * rim)) for c in BASE)


def build_faces():
    front = [(x, y, HZ) for x, y in RING]
    back = [(x, y, -HZ) for x, y in RING]
    Cf, Cb = (0.0, 0.0, HZ), (0.0, 0.0, -HZ)
    faces = []
    for i in range(8):
        j = (i + 1) % 8
        faces.append([front[i], front[j], Cf])            # front kites (fan: convex)
        faces.append([back[j], back[i], Cb])              # back kites, reversed winding
        faces.append([front[i], front[j], back[j], back[i]])  # side quads
    return faces


FACES = build_faces()


def render_frame(i):
    th = 2 * math.pi * i / N_FRAMES
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    polys = []
    for face in FACES:
        rv = yaw(face, th)
        pv = [project(p) for p in rv]
        n = _norm(cross(tuple(rv[1][k] - rv[0][k] for k in range(3)),
                        tuple(rv[2][k] - rv[0][k] for k in range(3))))
        zc = sum(z for _, _, z in pv) / len(pv)
        polys.append((zc, [(x, y) for x, y, _ in pv], shade(n)))
    polys.sort(key=lambda t: t[0])            # painter: far (-z) first
    for _, pts, col in polys:
        d.polygon(pts, fill=col + (255,), outline=col + (255,))
    # chibi gem on the front face (only while the face points at camera)
    gn = yaw([(0, 0, 1)], th)[0]
    if gn[2] > 0.05:
        gx, gy, gz = GEM
        pts2 = [(gx + GEM_R * math.cos(a), gy + GEM_R * math.sin(a), gz)
                for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
        sp = [(x, y) for x, y, _ in map(project, yaw(pts2, th))]
        k = 0.55 + 0.45 * max(0.0, gn[2])
        d.polygon(sp, fill=tuple(min(255, 110 + int(c * k)) for c in (235, 215, 255)) + (255,))
    # rim light: stroke the front face silhouette
    sil = [(x, y) for x, y, _ in map(project, yaw([(*xy, HZ) for xy in RING], th))]
    d.polygon(sil, outline=(235, 215, 255, 170), width=2 * SS)

    # additive glow bloom: blurred silhouette, alpha-composited over the body
    alpha_body = img.getchannel("A")
    glow_a = alpha_body.filter(ImageFilter.GaussianBlur(14)).point(lambda v: v * 3 // 4)
    glow = Image.merge("RGB", [glow_a.point(lambda v, c=c: c * v // 255) for c in GLOW])
    galpha = glow_a.point(lambda v: min(255, v * 3 // 2))
    # glow layer *under* the crisp body = screen-style bloom on transparency
    res = Image.alpha_composite(Image.merge("RGBA", (*glow.split(), galpha)), img)
    return res.resize((OUT, OUT), Image.LANCZOS)


def verify_and_montage():
    files = sorted(f for f in os.listdir(FRAMES_DIR) if f.endswith(".png"))
    assert len(files) == N_FRAMES, files
    print("frame   bbox (L,T,R,B)      w x h")
    boxes = []
    for f in files:
        im = Image.open(os.path.join(FRAMES_DIR, f))
        assert im.size == (OUT, OUT) and im.mode == "RGBA", (f, im.size, im.mode)
        bbox = im.split()[3].getbbox()   # non-transparent region
        assert bbox, (f, "empty frame")
        boxes.append(bbox)
        print(f"{f}    {bbox}   {bbox[2]-bbox[0]}x{bbox[3]-bbox[1]}")
    uniq = len(set(boxes))
    assert uniq >= 2, "identical bboxes across frames -> rotation not visible"
    print(f"OK: {uniq} distinct bboxes / {N_FRAMES} frames (yaw rotation proven)")
    picks = [Image.open(os.path.join(FRAMES_DIR, files[j])) for j in range(0, N_FRAMES, 3)]
    m = Image.new("RGBA", (OUT * len(picks), OUT), (18, 14, 28, 255))
    for k, p in enumerate(picks):
        m.paste(p, (k * OUT, 0), p)
    m.save(os.path.join(PACK, "preview.png"))
    print("preview.png:", os.path.join(PACK, "preview.png"))


if __name__ == "__main__":
    t0 = __import__("time").time()
    os.makedirs(FRAMES_DIR, exist_ok=True)
    for i in range(N_FRAMES):
        render_frame(i).save(os.path.join(FRAMES_DIR, f"f{i:02d}.png"))
    print(f"rendered {N_FRAMES} frames in {__import__('time').time()-t0:.1f}s")
    if "--verify" in sys.argv:
        verify_and_montage()
