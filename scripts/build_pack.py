#!/usr/bin/env python3
"""build_pack.py — slice sprite sheets into cursor-magic packs, mirror, verify.
Subcommands:
  slice <sheet.png> --pack packs/<dir> --name <label> --fps N [--attribution S]
  mirror [--dest DIR]   # repo packs/ -> runtime mirror, only diffing packs
  verify                # run test_packs.py, echo exit status
stdlib + PIL + numpy only.
"""
import argparse, json, os, shutil, subprocess, sys

import numpy as np
from PIL import Image

SIDE = 256
ALPHA_THRESHOLD = 10
GUTTER_FLOOR = 4      # interior gutter runs narrower than this are antialias slivers
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME = os.path.expanduser("~/.config/dusky/cursor-magic/packs")
LICENSE_DEFAULT = ("Frames sliced from a third-party sprite sheet; see the pack "
                   "manifest 'attribution' field for author and license.\n")


def _gutters(mask_axis):
    """Zero (transparent) runs as (start, end) pairs."""
    z = ~mask_axis
    out, i = [], 0
    while i < len(z):
        if z[i]:
            j = i
            while j < len(z) and z[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def _cell_bounds(mask_1d, length, floor):
    """Cell edges = midpoints of interior gutters (major runs only)."""
    interior = [g for g in _gutters(mask_1d) if g[0] > 0 and g[1] < length and g[1] - g[0] >= floor]
    edges = [0] + [(s + e) // 2 for s, e in interior] + [length]
    return edges


def slice_cmd(a):
    im = Image.open(a.sheet).convert("RGBA")
    alpha = np.asarray(im)[:, :, 3]
    thr = alpha > ALPHA_THRESHOLD
    cb = _cell_bounds(thr.any(axis=0), alpha.shape[1], GUTTER_FLOOR)
    rb = _cell_bounds(thr.any(axis=1), alpha.shape[0], GUTTER_FLOOR)
    out = os.path.join(a.pack, a.name)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    n = 0
    for r0, r1 in zip(rb, rb[1:]):
        for c0, c1 in zip(cb, cb[1:]):
            cell = alpha[r0:r1, c0:c1]
            if not cell.any():
                continue
            sub = im.crop((c0, r0, c1, r1))
            bbox = sub.getbbox()  # trim to content, then center on canvas
            if bbox:
                sub = sub.crop(bbox)
            canvas = Image.new("RGBA", (SIDE, SIDE), (0, 0, 0, 0))
            if max(sub.size) > SIDE:  # downscale to fit, keep aspect
                w, h = sub.size
                k = SIDE / max(w, h)
                sub = sub.resize((round(w * k), round(h * k)), Image.Resampling.LANCZOS)
            canvas.paste(sub, ((SIDE - sub.width) // 2, (SIDE - sub.height) // 2), sub)
            canvas.save(os.path.join(out, f"f{n:03d}.png"))
            n += 1
    if n == 0:
        sys.exit(f"error: no non-transparent cells found in {a.sheet}")

    # update manifest (create if new pack, append emotion otherwise)
    mf_path = os.path.join(a.pack, "manifest.json")
    if os.path.isfile(mf_path):
        with open(mf_path) as f:
            manifest = json.load(f)
        manifest.setdefault("emotions", {})[a.name] = {
            "type": "seq", "path": f"{a.name}/", "frames": n, "fps": a.fps}
    else:
        os.makedirs(a.pack, exist_ok=True)
        manifest = {"name": os.path.basename(a.pack.rstrip("/")),
                    "attribution": a.attribution or "",
                    "emotions": {a.name: {"type": "seq", "path": f"{a.name}/",
                                          "frames": n, "fps": a.fps}}}
        lic = os.path.join(a.pack, "LICENSE.txt")
        if not os.path.isfile(lic):
            with open(lic, "w") as f:
                f.write(LICENSE_DEFAULT)
    tmp = mf_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    os.replace(tmp, mf_path)
    print(f"sliced {n} frames -> {out} (manifest frames={n}, fps={a.fps})")


def _manifest_of(d):
    p = os.path.join(d, "manifest.json")
    if not os.path.isfile(p):
        return None
    with open(p, "rb") as f:
        return f.read()


def mirror_cmd(a):
    src = os.path.abspath(a.src)
    for name in sorted(os.listdir(src)):
        s = os.path.join(src, name)
        if not os.path.isfile(os.path.join(s, "manifest.json")):
            continue
        d = os.path.join(a.dest, name)
        if _manifest_of(s) == _manifest_of(d):
            print(f"skip {name} (manifest identical)")
            continue
        if os.path.isdir(d):
            shutil.rmtree(d)
        shutil.copytree(s, d)
        print(f"mirrored {name} -> {d}")


def verify_cmd(a):
    r = subprocess.run([sys.executable, os.path.join(HERE, "test_packs.py")])
    print(f"verify exit status: {r.returncode}")
    sys.exit(r.returncode)


def main():
    p = argparse.ArgumentParser(prog="build_pack.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("slice")
    s.add_argument("sheet")
    s.add_argument("--pack", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--fps", type=int, default=15)
    s.add_argument("--attribution", default=None)
    s.set_defaults(fn=slice_cmd)
    m = sub.add_parser("mirror")
    m.add_argument("--src", default=os.path.join(HERE, "packs"))
    m.add_argument("--dest", default=RUNTIME)
    m.set_defaults(fn=mirror_cmd)
    v = sub.add_parser("verify")
    v.set_defaults(fn=verify_cmd)
    a = p.parse_args()
    if a.cmd == "slice" and not os.path.isfile(a.sheet):
        sys.exit(f"error: sheet not found: {a.sheet}")
    a.fn(a)


if __name__ == "__main__":
    main()
