# sigil3d — pre-rendered 3D turntable sprite

A fake-real-3D "chibi sigil": an extruded 4-point star rendered offline
(`scripts/render3d.py`, stdlib+PIL only — no bpy/trimesh) as a 24-frame yaw
turntable. Runtime cost: zero. The daemon just cycles PNGs.

## seq format (daemon contract)

`manifest.json` → `emotions.<name>`:

| key      | meaning |
|----------|---------|
| `type`   | `"seq"` — frame sequence (vs `"gif"` in the anime pack) |
| `path`   | directory (trailing slash) holding frames, resolved relative to this pack dir |
| `frames` | frame count; files are zero-indexed `f00.png … f{frames-1}.png` |
| `fps`    | playback rate; at `fps == frames` one loop = exactly 1 s |

Daemon loop: `frame = int(t * fps) % frames` → `cairo` paint `path + f"{frame:02d}.png"`
as an RGBA surface. Frames are **128×128 RGBA PNG, transparent background**, so they
composite directly over the overlay with no chroma key.

## Contents

- `frames/f00.png … f23.png` — the turntable (24 fps loop, seamless: f24 == f00)
- `preview.png` — every 3rd frame on a dark strip (human review only, not loaded)

## Regenerating

```sh
/usr/bin/python3 scripts/render3d.py --verify   # ~0.2 s total
```

`--verify` asserts every frame is 128px RGBA with a non-empty alpha bbox, prints the
per-frame bbox table (bbox varies across frames ⇒ rotation is real), and rebuilds
preview.png. Tuning knobs live at the top of the script: `TILT` (camera pitch),
`HZ` (thickness), `BASE`/`GLOW` (colors), `PPU` (size — keep the widest frame inside
128px), bloom radius in `render_frame()`.

## How the 3D look is made (no engine)

perspective projection → painter's-sorted convex triangles → Lambert facet shade
+ back-facing rim term → front-silhouette rim stroke + off-axis highlight gem →
Gaussian-blurred silhouette composited under the crisp body (bloom) → 3× supersample
downscaled with LANCZOS (no jaggies).
