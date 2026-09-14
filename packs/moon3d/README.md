# moon3d — premium 3D turntable: crescent moon + orbiting ring

The bigger sibling of `sigil3d`: an extruded crescent moon (outer circle minus
offset inner circle, triangulated into a convex quad strip + rim quads) with a
thin gold torus orbiting at a tilt, plus three pulsing billboard sparkle-stars.
Rendered fully offline by `scripts/render3d_moon.py` (stdlib + PIL only — no
bpy/trimesh). Runtime cost: zero; the daemon just cycles PNGs.

## seq format (daemon contract)

`manifest.json` → `emotions.moon`: `type:"seq"`, `path:"frames/"`,
`frames:36`, `fps:30` → one 1.2 s seamless loop (`f36 == f00`).
Daemon loop: `frame = int(t * fps) % frames` → paint `frames/f{frame:02d}.png`.
Frames are **256×256 RGBA PNG, transparent background**.

## Contents

- `frames/f00.png … f35.png` — the 36-frame yaw turntable
- `preview.png` — every 6th frame on a dark strip (review only, not loaded)

## Regenerating

```sh
/usr/bin/python3 scripts/render3d_moon.py --verify   # ~2 s total
```

`--verify` asserts 36× 256px RGBA, per-frame alpha bboxes all differ (rotation
is real), no frame touches the border, and >30 distinct shaded facet colors.
Knobs at the top: `TILT`, `RING_R/TUBE_R/TX` (orbit size/tilt), `HZ` (moon
thickness), `MOON`/`RING_C`/`GLOW` (colors), `PPU` (keep widest frame < 256px),
bloom radii in `render_frame()`.

## How the 3D look is made (no engine)

perspective projection → back-face culling + painter's-sorted convex quads →
Lambert facet shade + Blinn specular + back-facing rim term → front-silhouette
rim stroke → two-pass Gaussian bloom (crisp halo + wide aura) composited under
the crisp body → 4× supersample (1024px) downscaled with LANCZOS.
