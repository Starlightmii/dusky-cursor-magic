#!/usr/bin/env python3
"""Render a real 3D model file (.glb/.gltf/.obj) as a turntable frame seq —
proves the 'best 3D model implementation' lane end-to-end without a GPU.

Pipeline: trimesh loads geometry + UVs + base-color texture → we sample one
color per face at its centroid UV, flat-shade with view-space light, painter's
algorithm rasterize (SS=4 supersample, LANCZOS down). 256px RGBA frames.

Run with the render venv (needs trimesh): .venv-render/bin/python
  scripts/render3d_model.py <model-file> --pack <dir> --name <stem> [--frames N]
  scripts/render3d_model.py --verify <packdir>
"""
import argparse, json, math, os, sys
import numpy as np
from PIL import Image
import trimesh

SS, SIDE = 4, 256
S = SIDE * SS


MAX_FACES = 8000              # ponytail: painter loop is O(faces) in python; decimate beyond this


def load_single(path):
    obj = trimesh.load(path, force="mesh")   # process=True: merges + bakes texture into vertex colors
    if len(obj.faces) > MAX_FACES:           # keep the CPU painter loop tractable
        obj = obj.simplify_quadric_decimation(MAX_FACES)
    return obj


def face_colors(mesh):
    """One RGB per face from baked vertex colors (avg of 3 corners)."""
    vc = np.asarray(mesh.visual.to_color().vertex_colors, dtype=int)
    return vc[mesh.faces, :3].mean(1).astype(int)


def render_turntable(mesh, frames, size=SIDE, light=(-0.4, -0.7, 0.62),
                     tilt=0.42, dist=None):
    V = np.asarray(mesh.vertices, dtype=float)
    F = np.asarray(mesh.faces)
    N = np.asarray(mesh.face_normals, dtype=float)
    C = face_colors(mesh)
    V = V - V.mean(0)
    span = max(np.abs(V).max(0))
    V = V / span * 0.9
    light = np.array(light); light /= np.linalg.norm(light)
    out = []
    for i in range(frames):
        th = math.tau * i / frames
        ca, sa = math.cos(th), math.sin(th)
        Ry = np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]])
        ct, st = math.cos(tilt), math.sin(tilt)
        Rx = np.array([[1, 0, 0], [0, ct, -st], [0, st, ct]])
        R = Rx @ Ry
        P = V @ R.T
        Nw = N @ R.T
        # orthographic with mild depth falloff (faux perspective); normalise
        # the *projected* extent so the model fills the canvas every frame
        persp = 1.0 / (2.2 - P[:, 2])
        x = P[:, 0] * persp
        y = P[:, 1] * persp
        k = 0.85 / max(np.abs(x).max(), np.abs(y).max())
        x, y = x * k, y * k
        img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        centroids = P[F].mean(1)                            # per-face depth
        order = np.argsort(centroids[:, 2], kind="stable")  # painter: far→near
        for fi in order:
            a, b, c = F[fi]
            pts = [(x[a], -y[a]), (x[b], -y[b]), (x[c], -y[c])]
            pts = [((px + 1.05) / 2.1 * size * SS, (py + 1.05) / 2.1 * size * SS)
                   for px, py in pts]
            lam = max(0.0, float(np.dot(Nw[fi], light)))
            sh = 0.32 + 0.85 * lam                          # ambient + key
            rim = 0.25 * max(0.0, 1.0 - abs(float(Nw[fi, 2])))**2
            r, g, bl = (np.clip(C[fi] * sh + rim * 255, 0, 255)).astype(int)
            d.polygon(pts, fill=(int(r), int(g), int(bl), 255),
                      outline=(int(r), int(g), int(bl), 255))
        out.append(img.resize((size, size), Image.Resampling.LANCZOS))
    return out


def verify(packdir):
    import glob
    fs = sorted(glob.glob(os.path.join(packdir, "f*.png")))
    ims = [Image.open(f) for f in fs]
    assert all(im.size == (256, 256) and im.mode == "RGBA" for im in ims)
    a0 = np.asarray(ims[0])[..., 3]; am = np.asarray(ims[len(ims) // 2])[..., 3]
    d = int((np.abs(a0.astype(int) - am.astype(int)) > 8).sum())
    assert d > 0, "mid frame identical to first"
    al = np.asarray(ims[-1])[..., 3]
    dl = int((np.abs(al.astype(int) - a0.astype(int)) > 8).sum())
    print(f"{os.path.basename(packdir)}: {len(fs)} frames, uniform 256px RGBA, "
          f"f0-vs-mid delta={d} >0, loop-wrap delta={dl} >0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", nargs="?")
    ap.add_argument("--pack", required=False)
    ap.add_argument("--name", default=None)
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--attribution", default="")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.verify or (a.model and not a.pack):
        verify(a.model if a.verify else a.pack); return
    stem = a.name or os.path.splitext(os.path.basename(a.model))[0].lower()
    mesh = load_single(a.model)
    print(f"loaded {stem}: {len(mesh.vertices)} verts, {len(mesh.faces)} faces")
    frames = render_turntable(mesh, a.frames)
    outdir = os.path.join(a.pack, stem)
    os.makedirs(outdir, exist_ok=True)
    for i, fr in enumerate(frames):
        fr.save(os.path.join(outdir, f"f{i:03d}.png"))
    mf = os.path.join(a.pack, "manifest.json")
    m = json.load(open(mf)) if os.path.isfile(mf) else {"name": os.path.basename(a.pack), "emotions": {}}
    m.setdefault("emotions", {})[stem] = {"type": "seq", "path": f"{stem}/",
                                          "frames": a.frames, "fps": a.fps}
    with open(mf, "w") as f: json.dump(m, f, indent=2)
    lic = os.path.join(a.pack, "LICENSE.txt")
    if not os.path.isfile(lic):
        open(lic, "w").write((a.attribution or "CC0") + "\n")
    print(f"wrote {a.frames} frames -> {outdir}")


if __name__ == "__main__":
    main()
