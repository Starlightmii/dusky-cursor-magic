#!/usr/bin/python3
"""render3d_pro: premium 3D turntables for the 2D cairo overlay.

numpy raymarch-lite: analytic sphere + star-prism SDFs, Lambert + Blinn-Phong
spec + rim, HSV banded surface, additive glow pass, SSAA 512->256 LANCZOS.
Seamless loop (yaw 0->2pi). Stdlib + numpy + PIL (numpy verified installed).

Usage:  /usr/bin/python3 scripts/render3d_pro.py [orb3d|star3d|both] [--verify]
Out:    packs/orb3d/frames/f000..f059.png, packs/star3d/frames/f000..f047.png
        256px RGBA transparent bg + per-pack preview.png + manifest.json
"""
import math, os, sys, time, json
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PK = os.path.normpath(os.path.join(HERE, "..", "packs"))

OUT, SS = 256, 2
CANVAS = OUT * SS          # 512 -> LANCZOS -> 256
Y_LIGHT = np.array([0.45, -0.55, 0.71])


def hsv(h, s, v):
    """Vectorized HSV->RGB; h,s,v numpy arrays or scalars."""
    h = np.asarray(h, float) % 1.0 * 6.0
    s = np.asarray(s, float); v = np.asarray(v, float)
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s + s * f), v * (1 - s * f)
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return r, g, b


def frame_grid(canvas):
    n = np.arange(canvas) + 0.5
    xy = (n - canvas / 2) / (canvas / 2)      # -1..1
    x, y = np.meshgrid(xy, xy)
    return x, y


def trace_orb(px, py, yaw):
    px, py = px / 0.84, py / 0.84  # frame headroom: nothing touches the edge
    """Moon orb: lighting FIXED in view space (spec stays under the light as
    the surface scrolls); texture in periodic longitude -> seamless, no poles
    except visual pinch; halo behind the disk only."""
    r2 = px * px + py * py
    z = np.sqrt(np.maximum(0.0, 1.0 - r2))
    hit = (z > 0) & (r2 <= 1.0)
    # ---- fixed lighting on view normal n=(px,py,z)
    ld = np.maximum(0.0, px * Y_LIGHT[0] + py * Y_LIGHT[1] + z * Y_LIGHT[2])
    h = np.stack([px + Y_LIGHT[0], py + Y_LIGHT[1], z + Y_LIGHT[2]])
    h /= np.maximum(1e-6, np.linalg.norm(h, axis=0))
    rim = np.power(np.maximum(0.0, 1.0 - z), 3.0) * 0.7
    # ---- true sphere UV with a tilted spin axis so the pole never
    # faces the camera -> continuous rotation visible at f0 vs f_half.
    tilt = -0.26
    ct, st = math.cos(tilt), math.sin(tilt)
    # rotate view point into spin frame: tilt about X, then yaw about Y
    y1, z1 = py * ct - z * st, py * st + z * ct
    c, sn = math.cos(yaw), math.sin(yaw)
    sx, sz = px * c - z1 * sn, px * sn + z1 * c
    lon = np.arctan2(sz, sx)            # -pi..pi around the tilted spin axis
    lat = np.clip(y1, -1.0, 1.0)        # orthographic latitude on spin frame
    band = (np.sin(lon * 3 + lat * 2) * 0.5 + 0.5) * np.sqrt(np.maximum(0.0, 1 - lat * lat * 0.9))
    hue = (0.60 + 0.04 * band) % 1.0
    sat = 0.28 + 0.20 * band
    val = 0.62 + 0.16 * band - 0.10 * np.abs(lat)
    r, g, b = hsv(hue, sat, val)
    # matte moon surface: broad soft spec (lower power, ~1/3 energy)
    inten = 0.32 + 0.75 * ld + 0.35 * (np.maximum(0.0, (np.stack([px, py, z]) * h).sum(0)) ** 10) + rim
    col = np.stack([r * inten, g * inten, b * inten])
    col = np.clip(col, 0.0, 1.15)
    # ---- halo ring behind the sphere (additive, outside the disk only)
    rr = np.sqrt(r2)
    ring = np.exp(-((rr - 0.62) ** 2) * 260.0) * 0.55
    ring += np.exp(-((rr - 0.62) ** 2) * 26.0) * 0.28
    outside = (~hit).astype(float)
    tint = np.array([0.72, 0.82, 1.0])[:, None, None]
    col = col * hit + tint * ring * outside
    alpha = np.maximum(hit.astype(float), np.clip(ring, 0, 1))
    return col, alpha


def trace_star(px, py, yaw):
    px, py = px / 0.76, py / 0.76  # frame headroom (soft halo tail needs more)
    """Sharp 4-point sparkle: exact polygon-boundary SDF, alternating facet
    shading, headroom for the halo so glow never clips frame edges."""
    c, s_ = math.cos(yaw), math.sin(yaw)
    ux = px * c + py * s_
    uy = -px * s_ + py * c
    TIP, INNER = 0.78, 0.30
    r = np.hypot(ux, uy)
    ang = np.arctan2(uy, ux) + math.pi
    a2 = ang % (math.pi / 2)
    a2 = np.minimum(a2, math.pi / 2 - a2)          # fold into half-sector
    # boundary segment tip->inner for this half-sector
    Psx, Psy = TIP, 0.0
    Qsx, Qsy = INNER * math.cos(math.pi / 4), INNER * math.sin(math.pi / 4)
    Ex, Ey = Qsx - Psx, Qsy - Psy
    ca, sa = np.cos(a2), np.sin(a2)
    rb = (Ex * Psy - Ey * Psx) / (Ex * sa - Ey * ca)
    k = np.floor(ang / (math.pi / 2)).astype(int) % 4
    sd = r - rb
    hit = sd < 0
    # bevel extrusion shading
    edge = np.abs(sd)
    zsh = np.clip(1.0 - edge * 3.2, 0, 1)
    nlen = np.maximum(1e-6, np.sqrt(ux * ux + uy * uy + (zsh * 2.0) ** 2))
    nx, ny, nz = ux / nlen, uy / nlen, zsh * 2.0 / nlen
    ld = np.maximum(0.0, nx * Y_LIGHT[0] + ny * Y_LIGHT[1] + nz * Y_LIGHT[2])
    spec = np.power(ld, 40.0) * 1.1
    facet = np.where(k % 2 == 0, 1.0, 0.80)         # alternating gem facets
    hue = (0.11 + 0.03 * np.sin(k * 1.7)) % 1.0
    r_, g_, b_ = hsv(hue, 0.55, 0.97)
    inten = (0.28 + 0.85 * ld) * facet + spec + np.power(1 - zsh, 2.0) * 0.3
    col = np.stack([r_ * inten, g_ * inten, b_ * inten])
    glow = np.exp(-np.maximum(0, sd) * 5.5) * 0.9 + np.exp(-np.maximum(0, sd) * 2.2) * 0.28
    tint = np.array([1.0, 0.88, 0.55])[:, None, None]
    col = col * hit + tint * glow * (1.0 - hit)
    alpha = np.maximum(hit.astype(float), np.clip(glow, 0, 1))
    return np.clip(col, 0.0, 1.15), alpha



def render(name, n_frames, trace):
    pack = os.path.join(PK, name)
    fdir = os.path.join(pack, "frames")
    os.makedirs(fdir, exist_ok=True)
    x, y = frame_grid(CANVAS)
    t0 = time.time()
    for i in range(n_frames):
        col, alpha = trace(x, y, 2 * math.pi * i / n_frames)
        a = np.clip(alpha, 0, 1)
        rgb = np.clip(col, 0, 1)
        # premultiplied-ish composite onto transparent
        out = np.zeros((CANVAS, CANVAS, 4))
        out[..., :3] = np.moveaxis(rgb, 0, -1)   # (3,H,W) -> (H,W,3)
        out[..., 3] = a
        im = Image.fromarray((out * 255).astype(np.uint8), "RGBA")
        im.resize((OUT, OUT), Image.Resampling.LANCZOS).save(os.path.join(fdir, f"f{i:03d}.png"))
    manifest = {"name": name,
                "emotions": {name: {"type": "seq", "path": "frames/", "frames": n_frames, "fps": 24}}}
    open(os.path.join(pack, "manifest.json"), "w").write(json.dumps(manifest, indent=1))
    print(f"{name}: {n_frames} frames @256px in {time.time()-t0:.1f}s")


def verify(name, n_frames):
    fdir = os.path.join(PK, name, "frames")
    files = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
    assert len(files) == n_frames == int(json.load(open(os.path.join(PK, name, "manifest.json")))["emotions"][name]["frames"]), files
    im0 = Image.open(os.path.join(fdir, files[0])).convert("RGBA")
    im1 = Image.open(os.path.join(fdir, files[-1])).convert("RGBA")
    dmax = np.abs(np.asarray(im0, int) - np.asarray(im1, int)).max()
    mid = Image.open(os.path.join(fdir, files[n_frames // 2])).convert("RGBA")
    dmid = np.abs(np.asarray(im0, int) - np.asarray(mid, int)).max()
    assert im0.size == (OUT, OUT), im0.size
    assert np.asarray(im0).any(), "empty frame"
    print(f"{name}: {len(files)} frames uniform 256px, f0-vs-f{len(files)//2} delta={dmid} (>0 proves motion), loop wrap f_last-vs-f0 delta={dmax}")
    # luminance ASCII preview of frame 0 (32 cols)
    lum = (np.asarray(im0.convert('L'), float) / 255)
    rows = []
    for r in range(0, CANVAS if False else OUT, OUT // 8):
        row = lum[r]
        line = "".join(" .:-=+*#%@"[min(9, int(v * 10))] for v in row[::OUT // 32])
        rows.append(line)
    print("\n".join(rows))
    picks = [Image.open(os.path.join(fdir, files[j])) for j in range(0, n_frames, max(1, n_frames // 8))]
    m = Image.new("RGBA", (OUT * len(picks), OUT), (18, 14, 28, 255))
    for k, p in enumerate(picks):
        m.paste(p, (k * OUT, 0), p)
    m.save(os.path.join(PK, name, "preview.png"))
    print(f"preview: {os.path.join(PK, name, 'preview.png')}")


if __name__ == "__main__":
    what = "both" if len(sys.argv) < 2 or sys.argv[1].startswith("-") else sys.argv[1]
    v = "--verify" in sys.argv
    if what in ("orb3d", "both"):
        render("orb3d", 60, trace_orb)
        if v: verify("orb3d", 60)
    if what in ("star3d", "both"):
        render("star3d", 48, trace_star)
        if v: verify("star3d", 48)
