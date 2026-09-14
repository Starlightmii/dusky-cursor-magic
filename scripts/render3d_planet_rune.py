#!/usr/bin/python3
"""Two more procedural turntable packs (see render3d_pro / render3d_gem for style).

  planet3d  60f  banded gas giant, tilted ring w/ sphere shadow + occlusion,
                 lighting fixed in view space, texture yaw 0->2pi -> seamless
  rune3d    48f  flat stone tablet (value noise + bevel) + extruded glowing
                 rune glyph spinning yaw 0->2pi -> seamless

Usage:  /usr/bin/python3 scripts/render3d_planet_rune.py [planet3d|rune3d] [--verify]
Out:    packs/<name>/f000..png RGBA 256px transparent bg + manifest.json +
        LICENSE.txt (+ preview.jpg)
"""
import math
import os
import sys
import time
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, ".."))
PK = os.path.join(REPO, "packs")

OUT, SS = 256, 2
CANVAS = OUT * SS                        # 512 render -> LANCZOS -> 256
L = np.array([0.45, -0.55, 0.71])        # key light, view space
L = L / np.linalg.norm(L)

PLANET_N, RUNE_N = 60, 48
PACKS = {"planet3d": PLANET_N, "rune3d": RUNE_N}
LABEL = {"planet3d": "planet", "rune3d": "rune"}
LICENSE = ("Procedural renderer in scripts/render3d_planet_rune.py, "
           "no third-party assets, MIT (project license)\n")


def nrm3(v):
    return v / np.maximum(1e-9, np.linalg.norm(v, axis=0))


def hsv(h, s, v):
    h = np.asarray(h, float) % 1.0 * 6.0
    s, v = np.asarray(s, float), np.asarray(v, float)
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s + s * f), v * (1 - s * f)
    return (np.choose(i, [v, q, p, p, t, v]),
            np.choose(i, [t, v, v, q, p, p]),
            np.choose(i, [p, p, t, v, v, q]))


def smooth(a):
    return np.clip(a, 0.0, 1.0) ** 2 * (3 - 2 * np.clip(a, 0.0, 1.0))


XY = None
def grid():
    global XY
    if XY is None:
        n = np.arange(CANVAS) + 0.5
        xy = (n - CANVAS / 2) / (CANVAS / 2)
        XY = np.meshgrid(xy, xy)
    return XY


# ---------------------------------------------------------------- planet3d
R = 0.60                                   # sphere radius in view units
RING_IN, RING_OUT = 1.06 * R, 1.92 * R      # inner/outer ring radii
ALPHA_TILT, BETA_ROLL = math.radians(62), math.radians(-10)
# ring-plane orthonormal basis in view space: U,V in-plane, W = normal
cA, sA, cB, sB = math.cos(ALPHA_TILT), math.sin(ALPHA_TILT), math.cos(BETA_ROLL), math.sin(BETA_ROLL)
# local -> world: Rx(tilt) then Rz(roll); columns are U,V,W
U = np.array([cB, sB, 0.0])
V = np.array([-sB * cA, cB * cA, sA])
W = np.array([sB * sA, -cB * sA, cA])


def render_planet(i):
    x, y = grid()
    px, py = x / 0.72, y / 0.72            # headroom so nothing touches edges
    yaw = 2 * math.pi * i / PLANET_N
    r2 = px * px + py * py
    zs = np.sqrt(np.maximum(0.0, R * R - r2))     # sphere front-surface depth
    hit = r2 < R * R
    n = nrm3(np.stack([px, py, zs]))
    ld = np.maximum(0.0, (n * L.reshape(3, 1, 1)).sum(0))
    h = nrm3(n + L.reshape(3, 1, 1))
    spec = np.maximum(0.0, (n * h).sum(0)) ** 18
    rim = 0.5 * np.maximum(0.0, 1 - zs / R) ** 3
    # texture in spin frame: local = M^T @ view dir; spin about W (ring normal
    # = planet's rotation axis, so the bands sit on the ring plane = equator)
    lv = np.stack([px, py, np.where(hit, zs, 0.0) / R])
    lx = (lv * U.reshape(3, 1, 1)).sum(0)
    ly = (lv * V.reshape(3, 1, 1)).sum(0)
    lz = (lv * W.reshape(3, 1, 1)).sum(0)
    lon = np.arctan2(ly, lx) + yaw
    lat = np.clip(lz, -1, 1)
    turb = np.sin(lon * 2 + lat * 3) * 0.7 + np.sin(lon * 5 - lat * 2) * 0.3
    bnd = 0.5 + 0.5 * np.sin(lat * 13.0 + 0.9 * turb * np.sqrt(np.maximum(0.0, 1 - lat * lat)))
    hue = 0.075 + 0.010 * np.sin(lon * 3 + lat * 5)
    r_, g_, b_ = hsv(hue, 0.32 + 0.20 * bnd, smooth(0.58 + 0.24 * bnd - 0.10 * np.abs(lat)))
    dspot = ((lon - 1.15) * 0.8) ** 2 + ((lat + 0.2) * 2.0) ** 2
    spot = np.clip(1 - dspot / 0.12, 0, 1) * hit
    r_, g_, b_ = r_ + 0.30 * spot, g_ - 0.08 * spot, b_ - 0.14 * spot
    inten = 0.30 + 0.70 * ld + 0.30 * spec + rim
    sph = np.stack([r_, g_, b_]) * inten
    # ---- ring: ray (px,py,t) meets plane-at-origin (normal W) at t:
    t = -(px * W[0] + py * W[1]) / W[2]
    pv3 = np.stack([px, py, t])
    ru = (pv3 * U.reshape(3, 1, 1)).sum(0)
    rv = (pv3 * V.reshape(3, 1, 1)).sum(0)
    rho = np.hypot(ru, rv)
    ang = np.arctan2(rv, ru)
    prof = 0.75 + 0.25 * np.sin(rho * 90.0) + 0.18 * np.sin(rho * 233.0 + 1.3)
    prof *= 1 - 0.8 * smooth(1 - np.abs(rho - 1.62 * R) * 60)        # Cassini gap
    edge = smooth((rho - RING_IN) * 60 / R) * smooth((RING_OUT - rho) * 50 / R)
    a_ring = np.clip(prof, 0.0, 1.25) * edge * 0.95
    # sphere shadow: ray from ring point toward light hits sphere?
    ql = px * L[0] + py * L[1] + t * L[2]
    q2 = px * px + py * py + t * t
    disc = ql * ql - (q2 - R * R)
    shadow = (disc > 0) & (-ql + np.sqrt(np.maximum(0, disc)) > 0)
    rlight = 0.34 + 0.66 * max(0.0, float(abs(W @ L)))
    col_ring = np.array([0.85, 0.78, 0.66]).reshape(3, 1, 1) * rlight * np.where(shadow, 0.35, 1.0)
    col_ring *= (0.85 + 0.15 * np.sin(ang * 2))
    # occlusion: hidden by sphere if hit and ring point inside/front-depth < zs
    front = ~hit | (t > zs)
    a_vis = a_ring * np.where(front, 1.0, 0.0)
    a_hid = a_ring * np.where(front, 0.0, 1.0)
    # painter: hidden ring, sphere, front ring
    rgb = col_ring * a_hid[None]
    rgb = np.where(hit, sph, rgb)
    rgb = rgb + (col_ring - rgb) * a_vis[None]        # front ring: alpha blend
    edge_aa = smooth((R - np.sqrt(r2)) * CANVAS / 2.0)   # 1px sphere rim AA
    alpha = np.clip(np.maximum(np.maximum(a_hid, a_vis), edge_aa), 0, 1)
    return _to_img(rgb, alpha)


def _to_img(rgb3, alpha):
    a = np.clip(alpha, 0, 1)
    rgb = np.clip(np.moveaxis(np.clip(rgb3, 0, 1), 0, -1), 0, 1)
    comp = np.dstack([rgb, a])
    im = Image.fromarray((comp * 255).astype(np.uint8), "RGBA")
    return im.resize((OUT, OUT), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------- rune3d
FOCAL, CAM_Z, PPU = 5.0, 9.0, 150.0
TZ_FRONT = 0.24                            # tablet front face z (unit-ish)
GZ0, GZ1 = 0.30, 0.44                      # glyph extrusion, always in front
# rune centerline (asymmetric), mitered to a closed polygon
SPINE = [(-0.22, -0.85), (-0.22, 0.80), (0.34, 0.50), (-0.02, 0.22), (0.46, -0.85)]
HALF = 0.11


def _miter_poly(spine, half):
    pts, Ls, Rs = [], [], []
    n = len(spine)
    for k in range(n):
        if 0 < k < n - 1:
            a1 = math.atan2(spine[k][1] - spine[k - 1][1], spine[k][0] - spine[k - 1][0])
            a2 = math.atan2(spine[k + 1][1] - spine[k][1], spine[k + 1][0] - spine[k][0])
            na = (a1 + a2) / 2 + math.pi / 2
            slant = 1.0 / max(0.35, math.cos((a2 - a1) / 2))
        else:
            nxt = spine[1] if k == 0 else spine[n - 2]
            na = math.atan2(spine[k][1] - nxt[1], spine[k][0] - nxt[0]) + math.pi / 2
            slant = 1.0
        ox, oy = math.cos(na) * half * slant, math.sin(na) * half * slant
        Ls.append((spine[k][0] + ox, spine[k][1] + oy))
        Rs.append((spine[k][0] - ox, spine[k][1] - oy))
    return Ls + list(reversed(Rs))


RUNE_POLY = _miter_poly(SPINE, HALF)


def _face_n(rv):
    a = np.array(rv[1]) - np.array(rv[0])
    b = np.array(rv[2]) - np.array(rv[0])
    n = np.cross(a, b)
    n = n / max(1e-9, np.linalg.norm(n))
    if n @ np.mean(rv, axis=0) < 0:
        n = -n
    return n


def project(p):
    k = FOCAL / (CAM_Z - p[2])
    return (CANVAS / 2 + p[0] * k * PPU, CANVAS / 2 - p[1] * k * PPU, p[2])


_TABLET = None
def tablet():
    global _TABLET
    if _TABLET is not None:
        return _TABLET
    m = Image.new("L", (CANVAS, CANVAS), 0)
    ImageDraw.Draw(m).rounded_rectangle([110, 110, CANVAS - 110, CANVAS - 110], 40, fill=255)
    M = np.asarray(m, float) / 255.0
    soft = np.asarray(m.filter(ImageFilter.GaussianBlur(6)), float) / 255.0
    gy, gx = np.gradient(soft)
    n = nrm3(np.stack([-gx * 2.6, gy * 2.6, np.ones_like(gx)]))
    ld = np.maximum(0.0, (n * L.reshape(3, 1, 1)).sum(0))
    rim = 0.38 * np.maximum(0.0, -n[2])
    lit = 0.30 + 0.70 * ld + rim
    rng = np.random.default_rng(7)
    def h(ix, iy, k):
        return np.mod(np.sin((ix + 13 * k) * 127.1 + (iy + 7 * k) * 311.7) * 43758.5453, 1.0)
    noise = np.zeros((CANVAS, CANVAS))
    step = 64
    while step >= 8:
        g = h(np.arange(CANVAS // step + 1)[:, None], np.arange(CANVAS // step + 1)[None, :], step)
        tile = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize(
            (CANVAS, CANVAS), Image.Resampling.BILINEAR), float) / 255.0
        noise += tile * step / 64.0
        step //= 2
    noise /= noise.max()
    grain = np.asarray(Image.fromarray((h(np.arange(CANVAS // 2)[:, None], np.arange(CANVAS // 2)[None, :], 1) * 255).astype(np.uint8))
                       .resize((CANVAS, CANVAS)), float) / 255.0
    base = 0.40 + 0.20 * noise + 0.06 * grain
    col = np.stack([base + 0.02, base + 0.005, base + 0.06]) * lit * M
    comp = np.dstack([np.clip(col, 0, 1).transpose(1, 2, 0), M])
    _TABLET = Image.fromarray((comp * 255).astype(np.uint8), "RGBA")
    return _TABLET


def render_rune(i):
    th = 2 * math.pi * i / RUNE_N
    bob = 1 + 0.008 * math.sin(th)                      # 1 cycle -> seamless
    c, s = math.cos(th), math.sin(th)
    ring = [(X * c * bob, Y * bob) for (X, Y) in RUNE_POLY]
    polys = []
    nf = len(ring)
    for k in range(nf):
        j = (k + 1) % nf
        quad = [(ring[k][0], ring[k][1], GZ1), (ring[j][0], ring[j][1], GZ1),
                (ring[j][0], ring[j][1], GZ0), (ring[k][0], ring[k][1], GZ0)]
        qv = [list(p) for p in quad]
        n = _face_n(qv[:3])
        zc = sum(project(p)[2] for p in qv) / 4
        shade, rim = _shade(n)
        base = (70, 120, 135)
        col = tuple(min(255, int(bv * shade + 30 * rim)) for bv in base)
        polys.append((zc, [(project(p)[0], project(p)[1]) for p in qv], col))
    for zcap, outward in ((GZ1, 1.0), (GZ0, -1.0)):
        cap = [(X, Y, zcap) for (X, Y) in ring]
        rv = [list(p) for p in cap]
        n = _face_n(rv[:3])
        if n[2] * outward < 0:
            n = -n
        shade, rim = _shade(n)
        face = max(0.0, n[2] * outward)                 # how much this cap faces cam
        em = np.array([95.0, 225.0, 255.0])
        col = tuple(min(255, int(45 * shade + em[k] * (0.35 + 0.75 * face) + 20 * rim))
                    for k in range(3))
        zc = zcap - 0.02 if outward > 0 else zcap - 0.5
        polys.append((zc, [(project(p)[0], project(p)[1]) for p in rv], col))
    img = tablet().copy()
    d = ImageDraw.Draw(img)
    polys.sort(key=lambda t: t[0])                     # far first
    for _, pl, col in polys:
        d.polygon(pl, fill=col + (255,), outline=col + (255,))
    # additive glow from a blurred silhouette of the glyph
    gl = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gl)
    for _, pl, _ in polys:
        gd.polygon(pl, fill=(110, 235, 255, 120))
    gl = gl.filter(ImageFilter.GaussianBlur(10))
    a = np.asarray(img, float)
    b = np.asarray(gl, float)
    ga = b[..., 3:4] / 255.0
    out = a[..., :3] * (1 - ga * 0.55) + b[..., :3] * ga + a[..., :3] * ga * 0.55
    alpha = np.clip(a[..., 3] + b[..., 3], 0, 255)
    comp = np.dstack([np.clip(out, 0, 255), alpha]).astype(np.uint8)
    return Image.fromarray(comp, "RGBA").resize((OUT, OUT), Image.Resampling.LANCZOS)


def _shade(n):
    d = max(0.0, float(np.dot(n, L)))
    return 0.30 + 0.70 * d, 0.38 * max(0.0, -n[2])


# ---------------------------------------------------------------- drivers
def manifest(name, n):
    return ('{\n  "name": "%s",\n  "attribution": "procedural: scripts/'
            'render3d_planet_rune.py",\n  "emotions": {\n    "%s": {\n'
            '      "type": "seq",\n      "path": "",\n'
            '      "frames": %d,\n      "fps": 20\n    }\n  }\n}\n'
            % (name, LABEL[name], n))


def render_pack(name):
    n = PACKS[name]
    pack = os.path.join(PK, name)
    os.makedirs(pack, exist_ok=True)
    t0 = time.time()
    fn = render_planet if name == "planet3d" else render_rune
    for i in range(n):
        fn(i).save(os.path.join(pack, f"f{i:03d}.png"))
    open(os.path.join(pack, "manifest.json"), "w").write(manifest(name, n))
    open(os.path.join(pack, "LICENSE.txt"), "w").write(LICENSE)
    print(f"{name}: {n} frames @256px in {time.time()-t0:.1f}s")


def mean_delta(a, b):
    return float(np.abs(np.asarray(a, int) - np.asarray(b, int)).sum() / np.asarray(a, int).size)


def verify(name):
    pack = os.path.join(PK, name)
    n = PACKS[name]
    files = sorted(f for f in os.listdir(pack) if f.endswith(".png") and f.startswith("f"))
    assert len(files) == n, (name, len(files), n)
    mf = json.load(open(os.path.join(pack, "manifest.json")))["emotions"][LABEL[name]]
    assert mf["type"] == "seq" and mf["frames"] == n and mf["fps"] == 20, mf
    ims = [Image.open(os.path.join(pack, f)).convert("RGBA") for f in files]
    assert {im.size for im in ims} == {(OUT, OUT)}, "non-uniform size"
    for im in ims:
        assert im.split()[3].getbbox(), "empty frame"
    d_mid = max(mean_delta(ims[0], ims[n // 2]), mean_delta(ims[0], ims[n // 4]))
    assert d_mid > 0, "f0 identical to mid frames -> no rotation"
    d_wrap = mean_delta(ims[-1], ims[0])
    assert d_wrap > 0, "f_last == f0 exactly -> suspicious"
    print(f"{name}: {len(files)} frames, uniform {OUT}px RGBA, f0-vs-mid delta={d_mid:.3f} >0, "
          f"loop-wrap f_last-vs-f0 delta={d_wrap:.3f} >0")
    picks = [ims[j] for j in range(0, n, max(1, n // 8))]
    m = Image.new("RGBA", (OUT * len(picks), OUT), (18, 14, 28, 255))
    for k, p in enumerate(picks):
        m.paste(p, (k * OUT, 0), p)
    m.convert("RGB").save(os.path.join(pack, "preview.jpg"))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    which = args[0] if args else "planet3d"
    if which not in PACKS:
        sys.exit(f"unknown pack '{which}' (want planet3d|rune3d)")
    if "--verify" in sys.argv:
        verify(which)
    else:
        render_pack(which)
        verify(which)
