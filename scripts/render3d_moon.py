#!/usr/bin/python3
"""Pre-render a premium 3D turntable sprite: crescent moon + orbiting tilted ring.

Offline math only (zero runtime cost), same recipe as scripts/render3d.py:
perspective-project an extruded crescent (outer-circle-minus-inner-circle,
triangulated as a convex quad strip + rim quads) plus a sampled torus ring
tilted around it. Painter's algorithm, Lambert + Blinn specular + rim term,
additive two-pass Gaussian bloom. Stdlib + PIL.

Usage:  /usr/bin/python3 scripts/render3d_moon.py [--verify]
Out:    packs/moon3d/frames/f00..f35.png  RGBA 256px transparent bg
"""
import math
import os
import sys
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.normpath(os.path.join(HERE, "..", "packs", "moon3d"))
FRAMES_DIR = os.path.join(PACK, "frames")

OUT = 256            # final sprite size
SS = 4               # supersample (1024 render -> LANCZOS -> 256)
CANVAS = OUT * SS
N_FRAMES = 36
FOCAL, CAM_Z, PPU = 5.0, 9.0, 420.0
TILT = -0.18                               # fixed x-tilt (3/4 view)

# crescent: outer circle r=1 @ origin minus inner circle r=0.86 @ (0.42, 0)
R_OUT, R_IN, IN_DX = 1.0, 0.86, 0.42
HZ = 0.14                                  # moon half-thickness
N_ARC = 32                                 # strip quads along each arc
# orbiting ring: tube around a tilted circle
RING_R, TUBE_R, TX = 1.52, 0.045, 0.52     # major radius, tube radius, tilt
U_SEG, V_SEG = 44, 8

MOON = (198, 206, 240)                     # pearl-silver moon
RING_C = (240, 188, 98)                    # gold ring
GLOW = (188, 178, 235)                     # bloom tint
SPARK = (255, 246, 220)                    # sparkle stars
def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v) if n > 1e-12 else (0.0, 0.0, 1.0)


L = _norm((0.45, -0.55, 0.70))
V = (0.0, 0.0, 1.0)
H = _norm((L[0] + V[0], L[1] + V[1], L[2] + V[2]))   # Blinn half-vector


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


# --- crescent outline --------------------------------------------------------
_xs = (R_OUT ** 2 - R_IN ** 2 + IN_DX ** 2) / (2 * IN_DX)   # crossing x
_ys = math.sqrt(R_OUT ** 2 - _xs ** 2)
_a_o = math.atan2(_ys, _xs)              # outer arc from a_o .. 2pi-a_o (through pi)
_a_i = math.atan2(_ys, _xs - IN_DX)      # inner arc from a_i .. 2pi-a_i (through pi)


def crescent_arcs():
    outer, inner = [], []
    for i in range(N_ARC + 1):
        t = i / N_ARC
        ao = _a_o + t * (2 * math.pi - 2 * _a_o)
        ai = _a_i + t * (2 * math.pi - 2 * _a_i)
        outer.append((R_OUT * math.cos(ao), R_OUT * math.sin(ao), ao))
        inner.append((IN_DX + R_IN * math.cos(ai), R_IN * math.sin(ai), ai))
    return outer, inner


OUTER, INNER = crescent_arcs()


def build_faces():
    """(verts_model, normal_model, base_color) — all convex quads."""
    f = [(x, y, HZ) for x, y, _ in OUTER]
    b = [(x, y, -HZ) for x, y, _ in OUTER]
    fi = [(x, y, HZ) for x, y, _ in INNER]
    bi = [(x, y, -HZ) for x, y, _ in INNER]
    faces = []
    for i in range(N_ARC):
        j = i + 1
        # front/back strip quads (flat normals ±z) — the crescent triangulated
        faces.append(([f[i], f[j], fi[j], fi[i]], (0, 0, 1), MOON))
        faces.append(([bi[i], bi[j], b[j], b[i]], (0, 0, -1), MOON))
        # outer rim
        ao = OUTER[i][2] + math.pi / N_ARC
        faces.append(([f[i], f[j], b[j], b[i]],
                      (math.cos(ao), math.sin(ao), 0), MOON))
        # inner rim (normal points into the cut-out)
        ai = INNER[i][2] + math.pi / N_ARC
        faces.append(([fi[i], fi[j], bi[j], bi[i]],
                      (-math.cos(ai), -math.sin(ai), 0), MOON))
    # torus: tube ring, tilted around the x-axis at build time
    er = lambda u: (math.cos(u), math.sin(u) * math.cos(TX), math.sin(u) * math.sin(TX))
    en = (0.0, -math.sin(TX), math.cos(TX))
    def pt(u, v):
        n = _norm((math.cos(v) * er(u)[0] + math.sin(v) * en[0],
                   math.cos(v) * er(u)[1] + math.sin(v) * en[1],
                   math.cos(v) * er(u)[2] + math.sin(v) * en[2]))
        c = (RING_R * er(u)[0], RING_R * er(u)[1], RING_R * er(u)[2])
        return (c[0] + TUBE_R * n[0], c[1] + TUBE_R * n[1], c[2] + TUBE_R * n[2])
    for i in range(U_SEG):
        u0, u1 = 2 * math.pi * i / U_SEG, 2 * math.pi * (i + 1) / U_SEG
        um, vmh = 0.5 * (u0 + u1), 0.0
        for k in range(V_SEG):
            v0, v1 = 2 * math.pi * k / V_SEG, 2 * math.pi * (k + 1) / V_SEG
            vm = 0.5 * (v0 + v1)
            faces.append(([pt(u0, v0), pt(u1, v0), pt(u1, v1), pt(u0, v1)],
                          _norm((math.cos(vm) * er(um)[0] + math.sin(vm) * en[0],
                                 math.cos(vm) * er(um)[1] + math.sin(vm) * en[1],
                                 math.cos(vm) * er(um)[2] + math.sin(vm) * en[2])),
                          RING_C))
    return faces


FACES = build_faces()
PALETTE = set()


def rot(p, th):
    c, s = math.cos(th), math.sin(th)
    ct, st = math.cos(TILT), math.sin(TILT)
    x, y, z = p
    x1, z1 = x * c + z * s, -x * s + z * c
    return (x1, y * ct - z1 * st, y * st + z1 * ct)


def project(p):
    k = FOCAL / (CAM_Z - p[2])
    return (CANVAS / 2 + p[0] * k * PPU, CANVAS / 2 - p[1] * k * PPU, p[2])


def shade(n, base):
    d = max(0.0, n[0] * L[0] + n[1] * L[1] + n[2] * L[2])
    rim = 0.42 * max(0.0, -n[2]) ** 1.5
    spec = max(0.0, n[0] * H[0] + n[1] * H[1] + n[2] * H[2]) ** 26
    b = 0.26 + 0.72 * d + rim
    return tuple(min(255, int(c * b + 60 * rim + 235 * spec)) for c in base)


SPARKS = [(0.62, 0.30, 0.16), (-0.35, 0.60, 0.11), (0.45, -0.55, 0.09)]
#             x     y   size (billboard 4-point stars orbiting the moon)


def render_frame(i):
    th = 2 * math.pi * i / N_FRAMES
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    polys = []
    for verts, nrm, base in FACES:
        rv = [rot(p, th) for p in verts]
        n = rot(nrm, th)
        if n[2] <= 0.02:                 # backface cull (closed convex parts)
            continue
        pv = [project(p) for p in rv]
        col = shade(n, base)
        PALETTE.add(col)
        zc = sum(z for _, _, z in rv) / len(pv)
        polys.append((zc, [(x, y) for x, y, _ in pv], col))
    polys.sort(key=lambda t: t[0])       # painter: far first
    for _, pts, col in polys:
        d.polygon(pts, fill=col + (255,), outline=col + (255,))

    # rim-light silhouette stroke on the moon's front outline
    sil = [(x, y) for x, y, _ in map(project, [rot((px, py, HZ + 0.001), th) for px, py, _ in OUTER])]
    d.polygon(sil, outline=(236, 232, 255, 150), width=2 * SS)

    # sparkle stars: camera-facing diamonds pulsing through the loop
    pulse = 0.55 + 0.45 * math.sin(3 * th)
    for sx, sy, ssz in SPARKS:
        p = project(rot((sx, sy, HZ + 0.05), th))
        if p[2] < HZ + 0.15:  # occluded behind the moon body: skip
            continue
        x, y = p[0], p[1]
        r1, r2 = ssz * PPU * pulse, ssz * PPU * 0.30 * pulse
        pts = []
        for a in range(8):
            ang = a * math.pi / 4
            rr = r1 if a % 2 == 0 else r2
            pts.append((x + rr * math.cos(ang), y - rr * math.sin(ang)))
        k = min(1.0, pulse + 0.35)
        d.polygon(pts, fill=tuple(int(c * k) for c in SPARK) + (255,))

    # two-pass additive bloom: crisp halo + wide soft aura
    alpha_body = img.getchannel("A")
    base_glow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    for rad, gain in ((14, 3), (34, 1)):
        ga = alpha_body.filter(ImageFilter.GaussianBlur(rad)).point(lambda v: v * 3 // 4)
        glow = Image.merge("RGB", [ga.point(lambda v, c=c: c * v // 255) for c in GLOW])
        base_glow = Image.alpha_composite(
            base_glow, Image.merge("RGBA", (*glow.split(), ga.point(lambda v: min(255, v * gain)))))
    res = Image.alpha_composite(base_glow, img)
    return res.resize((OUT, OUT), Image.LANCZOS)


def verify_and_montage():
    files = sorted(f for f in os.listdir(FRAMES_DIR) if f.endswith(".png"))
    assert len(files) == N_FRAMES, files
    print("frame   bbox (L,T,R,B)        w x h")
    boxes = []
    for f in files:
        im = Image.open(os.path.join(FRAMES_DIR, f))
        assert im.size == (OUT, OUT) and im.mode == "RGBA", (f, im.size, im.mode)
        strong = im.split()[3].point(lambda v: 255 if v >= 6 else 0)
        bbox = strong.getbbox()
        assert bbox, (f, "empty frame")
        assert bbox[0] > 2 and bbox[1] > 2 and bbox[2] < OUT - 2 and bbox[3] < OUT - 2, \
            (f, "clipped at border", bbox)
        boxes.append(bbox)
        print(f"{f}    {bbox}   {bbox[2]-bbox[0]}x{bbox[3]-bbox[1]}")
    uniq = len(set(boxes))
    print(f"{uniq} distinct bboxes / {N_FRAMES} frames")
    assert uniq >= N_FRAMES - 2, "rotation not visible"
    print(f"distinct facet colors: {len(PALETTE)}")
    assert len(PALETTE) > 30
    picks = [Image.open(os.path.join(FRAMES_DIR, files[j])) for j in range(0, N_FRAMES, 6)]
    m = Image.new("RGBA", (OUT * len(picks), OUT), (16, 12, 26, 255))
    for k, p in enumerate(picks):
        m.paste(p, (k * OUT, 0), p)
    m.save(os.path.join(PACK, "preview.png"))
    print("OK: preview.png built with", len(picks), "frames")


if __name__ == "__main__":
    t0 = __import__("time").time()
    os.makedirs(FRAMES_DIR, exist_ok=True)
    for i in range(N_FRAMES):
        render_frame(i).save(os.path.join(FRAMES_DIR, f"f{i:02d}.png"))
    print(f"rendered {N_FRAMES} frames in {__import__('time').time()-t0:.1f}s")
    if "--verify" in sys.argv:
        verify_and_montage()
