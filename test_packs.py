#!/usr/bin/env python3
"""Integration gate: every pack in a dir must load via the real daemon code
(magic_core.load_packs + decode_frames) and look sane. Run:
    /usr/bin/python3 test_packs.py [pack_dir ...]
Default dirs: repo packs/ and the runtime mirror. Exit 1 on any failure.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from magic_core import load_packs, decode_frames

DEFAULTS = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "packs"),
            os.path.expanduser("~/.config/dusky/cursor-magic/packs")]
MAX_SIDE = 512  # frames bigger than this hurt the 8ms tick budget

def check(pack_dir):
    fails, rows = [], []
    packs = load_packs(pack_dir)
    if not packs:
        fails.append(f"{pack_dir}: no packs found")
    for name, m in sorted(packs.items()):
        assert "name" in m and "emotions" in m, name
        for label, spec in sorted(m["emotions"].items()):
            key = f"{name}/{label}"
            try:
                t = spec["type"]
                if t == "emoji":
                    assert spec["char"], key
                    rows.append((key, "emoji", "-", 1)); continue
                if t == "seq":
                    d = spec["path"]
                    files = sorted(f for f in os.listdir(d) if f.endswith(".png"))
                    n_manifest = spec.get("frames")
                    if n_manifest is not None and n_manifest != len(files):
                        raise AssertionError(f"seq {key}: manifest says {n_manifest}, found {len(files)}")
                    frames = [os.path.join(d, f) for f in files]
                    ims = []
                    for fp in frames:
                        ims.append(__import__("PIL.Image", fromlist=["Image"]).open(fp).convert("RGBA"))
                    n = len(ims)
                    sizes = {im.size for im in ims}
                    if len(sizes) != 1:
                        raise AssertionError(f"{key}: non-uniform sizes {sizes}")
                    side = max(next(iter(sizes)))
                    alpha = max(im.getbbox() is not None for im in ims)
                    opaque = any(sum(px[3] for px in im.getdata()) > 0 for im in ims[:1])
                    if not opaque:
                        raise AssertionError(f"{key}: frame 0 fully transparent")
                    rows.append((key, t, f"{side}px", n))
                    if side > MAX_SIDE:
                        fails.append(f"{key}: {side}px > {MAX_SIDE} budget")
                else:  # gif / png
                    frames, durs = decode_frames(spec["path"])
                    if not frames:
                        raise AssertionError(f"{key}: decoded 0 frames")
                    side = max(frames[0].size)
                    if side > MAX_SIDE:
                        fails.append(f"{key}: {side}px > {MAX_SIDE} budget")
                    if t == "gif" and len(frames) < 2:
                        print(f"  warn: {key}: 1-frame gif (acts as static)")
                    rows.append((key, t, f"{side}px", len(frames)))
            except Exception as e:
                fails.append(f"{key}: {e!r}")
    return rows, fails

def mirror_check(repo_dir, runtime_dir):
    """Runtime mirror must not lag the repo: same packs, same frame counts."""
    fails = []
    rp, up = load_packs(repo_dir), load_packs(runtime_dir)
    for name, m in sorted(rp.items()):
        u = up.get(name)
        if u is None:
            fails.append(f"mirror: repo pack '{name}' missing in runtime"); continue
        for label, spec in m["emotions"].items():
            us = u["emotions"].get(label)
            if us is None:
                fails.append(f"mirror: {name}/{label} missing in runtime")
            elif spec.get("frames") != us.get("frames"):
                fails.append(f"mirror drift: {name}/{label} repo={spec.get('frames')} runtime={us.get('frames')}")
    return fails

def main():
    dirs = [os.path.expanduser(d) for d in (sys.argv[1:] or DEFAULTS)]
    all_fails = []
    for d in dirs:
        d = os.path.expanduser(d)
        if not os.path.isdir(d):
            print(f"skip (missing): {d}"); continue
        rows, fails = check(d)
        print(f"== {d}: {len(rows)} emotions ==")
        for k, t, s, n in rows:
            print(f"  {k:34s} {t:5s} {s:>6s} {n:3d}f")
        all_fails += fails
    if len(dirs) >= 2:
        all_fails += mirror_check(dirs[0], dirs[1])
    if all_fails:
        print("\nFAILURES:")
        [print("  " + f) for f in all_fails]
        sys.exit(1)
    print("\nALL PACKS OK (decoded via real load_packs/decode_frames)")

if __name__ == "__main__":
    main()
