#!/usr/bin/python3
"""Two more premium 3D turntable packs, adapted from scripts/render3d.py.

  packs/crystal3d  hexagonal bipyramid, flat-shaded amethyst->cyan facets
  packs/crown3d    chibi 5-point crown extrusion + band, gold + red gem

Usage:  /usr/bin/python3 scripts/render3d_gem.py [crystal|crown] [--verify]
Out:    packs/<name>/frames/f00..fNN.png  RGBA 256px transparent bg
"""
import math
import os
import sys
import time
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, ".."))

OUT = 256            # final sprite size
SS = 2               # 512 render -> LANCZOS -> 256
CANVAS = OUT * SS
FOCAL, CAM_Z, PPU = 5.0, 9.0, 240.0
TILT = -0.16
L = (0.45, -0.55, 0.70)                    # key light (upper-left, toward cam)


def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


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


def lambert(n):
    d = max(0.0, n[0] * L[0] + n[1] * L[1] + n[2] * L[2])
    rim = 0.38 * max(0.0, -n[2])
    return 0.30 + 0.70 * d + rim, rim


# ---------------------------------------------------------------- crystal3d
CRY_N = 36
TOP_H, BOT_H, R_G = 1.35, 1.05, 0.62       # apex heights, girdle radius
AMETHYST = (148, 96, 216)
CYAN = (72, 214, 224)
CRY_GLOW = (140, 200, 255)


def crystal_faces():
    ring = [(R_G * math.cos(i * math.pi / 3), 0.0, R_G * math.sin(i * math.pi / 3))
            for i in range(6)]
    T, B = (0.16, TOP_H, 0.10), (0.0, -BOT_H, 0.0)   # tilted top apex: fantasy
    faces = []
    for i in range(6):
        j = (i + 1) % 6
        faces.append([T, ring[i], ring[j]])             # 6 top facets
        faces.append([ring[i], ring[j], B])             # 6 bottom facets
    return ring, faces


def crystal_shade(n):
    t = 0.5 + 0.5 * n[1]                                # normal y -> amethyst..cyan
    base = tuple(int(a + (b - a) * t) for a, b in zip(AMETHYST, CYAN))
    b, rim = lambert(n)
    return tuple(min(255, int(c * b + 14 * rim)) for c in base)


CRY_RING, CRY_FACES = crystal_faces()


def render_crystal(i):
    th = 2 * math.pi * i / CRY_N
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    polys = []
    for face in CRY_FACES:
        rv = yaw(face, th)
        pv = [project(p) for p in rv]
        n = _norm(cross(tuple(rv[1][k] - rv[0][k] for k in range(3)),
                        tuple(rv[2][k] - rv[0][k] for k in range(3))))
        cen = [sum(v[k] for v in rv) / len(rv) for k in range(3)]
        if sum(a * b for a, b in zip(n, cen)) < 0:      # point facets outward
            n = tuple(-c for c in n)
        zc = sum(z for _, _, z in pv) / len(pv)
        polys.append((zc, [(x, y) for x, y, _ in pv], n, crystal_shade(n)))
    polys.sort(key=lambda t: t[0])                      # painter: far first
    # spec: boost the 2 facets most facing the light
    ranked = sorted(range(len(polys)), key=lambda k: -max(0.0, polys[k][2][0] * L[0]
                                                          + polys[k][2][1] * L[1]
                                                          + polys[k][2][2] * L[2]))[:2]
    spec = set(ranked)
    for idx, (_, pts, _, col) in enumerate(polys):
        if idx in spec:
            col = tuple(min(255, c + 110) for c in col)
        d.polygon(pts, fill=col + (255,), outline=col + (255,))
    girdle = [(x, y) for x, y, _ in map(project, yaw(CRY_RING, th))]
    d.polygon(girdle, outline=(220, 245, 255, 150), width=2 * SS)
    return bloom(img, CRY_GLOW)


# ------------------------------------------------------------------ crown3d
CRW_N = 24
R_OUT, R_IN, HZ = 1.0, 0.62, 0.14
CROWN_LIFT = 0.34                                       # points sit on the band
BAND_W, BAND_H, BAND_TOP = 0.95, 0.34, -0.15
BAND_Z = HZ * 1.7                                       # band is thicker than plate
GEM = (0.0, BAND_TOP - BAND_H / 2, BAND_Z + 0.001)      # jewel set in the band
GEM_R = 0.13
GOLD = (222, 168, 62)
GEM_RED = (235, 60, 90)
CRW_GLOW = (255, 190, 90)


def crown_ring():
    pts = []
    for i in range(10):                                 # 5 points, 10 verts
        a = math.pi / 2 + i * math.pi / 5               # tip at top
        r = R_OUT if i % 2 == 0 else R_IN
        pts.append((r * math.cos(a), r * math.sin(a) + CROWN_LIFT))
    return pts


CRW_RING = crown_ring()


def crown_faces():
    front = [(x, y, HZ) for x, y in CRW_RING]
    back = [(x, y, -HZ) for x, y in CRW_RING]
    faces = [front, [p for p in reversed(back)]]        # cap faces (concave ok)
    # band: thicker extruded box strip under the points (hides lower tips)
    bw, by1, by0, BZ = BAND_W, BAND_TOP, BAND_TOP - BAND_H, BAND_Z
    band = [(-bw, by1), (bw, by1), (bw, by0), (-bw, by0)]
    bf = [(x, y, BZ) for x, y in band]
    bb = [(x, y, -BZ) for x, y in band]
    for i in range(10):
        j = (i + 1) % 10
        faces.append([front[i], front[j], back[j], back[i]])   # crown side quads
    for i in range(4):
        j = (i + 1) % 4
        faces.append([bf[i], bf[j], bb[j], bb[i]])              # band walls
    faces.append(list(reversed(bf)))                            # front cap +z
    faces.append(bb)                                            # back cap -z
    return faces


CRW_FACES = crown_faces()


def gold_shade(n):
    b, rim = lambert(n)
    return tuple(min(255, int(c * b + 18 * rim)) for c in GOLD)


def render_crown(i):
    th = 2 * math.pi * i / CRW_N
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    polys = []
    for face in CRW_FACES:
        rv = yaw(face, th)
        pv = [project(p) for p in rv]
        n = _norm(cross(tuple(rv[1][k] - rv[0][k] for k in range(3)),
                        tuple(rv[2][k] - rv[0][k] for k in range(3))))
        zc = sum(z for _, _, z in pv) / len(pv)
        polys.append((zc, [(x, y) for x, y, _ in pv], gold_shade(n)))
    polys.sort(key=lambda t: t[0])
    for _, pts, col in polys:
        d.polygon(pts, fill=col + (255,), outline=col + (255,))
    # red gem diamond on the front face (like sigil3d, only while it faces cam)
    gn = yaw([(0, 0, 1)], th)[0]
    if gn[2] > 0.05:
        gx, gy, gz = GEM
        pts2 = [(gx + GEM_R * math.cos(a), gy + GEM_R * math.sin(a), gz)
                for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
        sp = [(x, y) for x, y, _ in map(project, yaw(pts2, th))]
        k = 0.55 + 0.45 * max(0.0, gn[2])
        d.polygon(sp, fill=tuple(min(255, 40 + int(c * k)) for c in GEM_RED) + (255,))
    sil = [(x, y) for x, y, _ in map(project, yaw([(*xy, HZ) for xy in CRW_RING], th))]
    d.polygon(sil, outline=(255, 235, 180, 170), width=2 * SS)
    return bloom(img, CRW_GLOW)


# --------------------------------------------------------------- shared io
def bloom(img, tint):
    alpha_body = img.getchannel("A")
    glow_a = alpha_body.filter(ImageFilter.GaussianBlur(14)).point(lambda v: v * 3 // 4)
    glow = Image.merge("RGB", [glow_a.point(lambda v, c=c: c * v // 255) for c in tint])
    galpha = glow_a.point(lambda v: min(255, v * 3 // 2))
    res = Image.alpha_composite(Image.merge("RGBA", (*glow.split(), galpha)), img)
    return res.resize((OUT, OUT), Image.LANCZOS)


def manifest(name, n):
    return ('{\n  "name": "%s",\n  "emotions": {\n    "%s": {\n'
            '      "type": "seq",\n      "path": "frames/",\n'
            '      "frames": %d,\n      "fps": 24\n    }\n  }\n}\n'
            % (name, name, n))


PACKS = {"crystal": ("crystal3d", CRY_N, render_crystal),
         "crown": ("crown3d", CRW_N, render_crown)}


def verify_and_montage(pack, n_frames):
    files = sorted(f for f in os.listdir(pack) if f.endswith(".png"))
    files = [f for f in files if f.startswith("f")]
    assert len(files) == n_frames, files
    boxes, imgs = [], []
    for f in files:
        im = Image.open(os.path.join(pack, f))
        assert im.size == (OUT, OUT) and im.mode == "RGBA", (f, im.size, im.mode)
        bbox = im.split()[3].getbbox()
        assert bbox, (f, "empty frame")
        boxes.append(bbox)
        imgs.append(im)
    uniq = len(set(boxes))
    assert uniq >= 2, "identical bboxes across frames -> rotation not visible"
    a = imgs[0]
    # bipyramid is symmetric: f0 == f(N/2); find first visually distinct frame
    for j in (n_frames // 2, n_frames // 4, 1):
        b = imgs[j]
        pa, pb = list(a.getdata()), list(b.getdata())
        delta = sum(abs(u - v) for x, y in zip(pa, pb) for u, v in zip(x, y)) / (len(pa) * 4)
        if delta > 0:
            partner = j
            break
    print(f"{os.path.basename(pack)}: {n_frames} frames, {uniq} distinct bboxes, "
          f"f0-vs-f{partner} mean pixel delta = {delta:.2f}")
    assert delta > 0
    picks = [Image.open(os.path.join(pack, files[j])) for j in range(0, n_frames, max(1, n_frames // 8))]
    m = Image.new("RGBA", (OUT * len(picks), OUT), (18, 14, 28, 255))
    for k, p in enumerate(picks):
        m.paste(p, (k * OUT, 0), p)
    m.save(os.path.join(os.path.dirname(pack), "preview.png"))
    print("preview.png:", os.path.join(os.path.dirname(pack), "preview.png"))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "crystal"
    name, n, render = PACKS[which]
    pack = os.path.join(REPO, "packs", name)
    frames = os.path.join(pack, "frames")
    t0 = time.time()
    os.makedirs(frames, exist_ok=True)
    for i in range(n):
        render(i).save(os.path.join(frames, f"f{i:02d}.png"))
    print(f"rendered {n} frames in {time.time() - t0:.1f}s")
    with open(os.path.join(pack, "manifest.json"), "w") as f:
        f.write(manifest(name, n))
    verify_and_montage(frames, n)
