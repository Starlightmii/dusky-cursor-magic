#!/usr/bin/env python3
"""TDD gate for scripts/build_pack.py. Run: /usr/bin/python3 test_build_pack.py
Slices /tmp/spell/sphere_blue.png into a temp pack and asserts:
  - frame count == packs/spells/orbsoul (27)
  - every frame is 256x256 RGBA with nonzero alpha
  - manifest.json written with real count; LICENSE.txt created
Also exercises `mirror` against a temp dir (never the runtime mirror).
"""
import json, os, shutil, subprocess, sys, tempfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = [sys.executable, os.path.join(HERE, "scripts", "build_pack.py")]
SHEET = "/tmp/spell/sphere_blue.png"

def main():
    assert os.path.isfile(SHEET), f"missing {SHEET}"
    ref = len([f for f in os.listdir(os.path.join(HERE, "packs/spells/orbsoul")) if f.endswith(".png")])
    assert ref == 26, f"orbsoul ref count moved: {ref}"

    tmp = tempfile.mkdtemp(prefix="build_pack_")
    try:
        # --- slice into a brand-new pack ---
        pack = os.path.join(tmp, "packs", "orbsoul_test")
        r = subprocess.run(TOOL + ["slice", SHEET, "--pack", pack, "--name", "orbsoul_test",
                                   "--fps", "15", "--attribution", "test attr"], cwd=HERE)
        assert r.returncode == 0, "slice failed"
        frames_dir = os.path.join(pack, "orbsoul_test")
        frames = sorted(os.listdir(frames_dir))
        assert len(frames) == 26, f"expected 26 frames, got {len(frames)}"
        assert frames[0] == "f000.png" and frames[-1] == "f025.png", frames[:2] + frames[-2:]
        for f in frames:
            im = Image.open(os.path.join(frames_dir, f))
            assert im.size == (256, 256) and im.mode == "RGBA", (f, im.size, im.mode)
            assert sum(px[3] for px in im.getdata()) > 0, f"{f} fully transparent"
        m = json.load(open(os.path.join(pack, "manifest.json")))
        assert m["name"] == "orbsoul_test" and m["attribution"] == "test attr"
        spec = m["emotions"]["orbsoul_test"]
        assert spec == {"type": "seq", "path": "orbsoul_test/", "frames": 26, "fps": 15}, spec  # 26 after residue-frame drop
        assert os.path.isfile(os.path.join(pack, "LICENSE.txt")), "new pack needs LICENSE.txt"

        # --- mirror into a temp dir: copies diffing packs, skips identical ---
        dest = os.path.join(tmp, "runtime")
        r = subprocess.run(TOOL + ["mirror", "--dest", dest], cwd=HERE)
        assert r.returncode == 0, "mirror failed"
        assert os.path.isfile(os.path.join(dest, "spells", "manifest.json")), "spells not mirrored"
        # idempotent second run must not recopy (no diff)
        mt0 = os.path.getmtime(os.path.join(dest, "spells", "manifest.json"))
        r = subprocess.run(TOOL + ["mirror", "--dest", dest], cwd=HERE, capture_output=True, text=True)
        assert "skip" in r.stdout and os.path.getmtime(os.path.join(dest, "spells", "manifest.json")) == mt0

        # --- pack still loads via the real daemon loader ---
        sys.path.insert(0, HERE)
        from magic_core import load_packs
        packs = load_packs(os.path.join(tmp, "packs"))
        assert "orbsoul_test" in packs
        assert os.path.isdir(packs["orbsoul_test"]["emotions"]["orbsoul_test"]["path"])
        print("ALL CHECKS PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
