# Cursor Soul ✨

**Alive cursor magic for Hyprland / Dusky.** Flick the mouse and an aura blooms
under the pointer — spring-scaled glow, comet trail, stars on every reversal,
click ripples, and an optional animated sprite (GIF, PNG, or a 3D frame-seq
turntable) that bobs and spins with your movement. The real cursor is never
replaced or blocked: the overlay is a fully click-through layer-shell surface.

No root, no new packages on Dusky — GTK3 + layer-shell via `python-gobject`,
Pillow, and the Hyprland socket are already there.

## Features

- **Continuous heat→spring aura** — shaking the mouse deposits "heat"
  (WiggleDetector); the glow scales toward a spring target and decays
  exponentially, like macOS/KWin's shake-to-find but always live, no gate.
- **Stars on every flick reversal**, click stars, and click ripples
  (press/release/double) — read-only evdev, never injected.
- **Comet trail** behind the aura while moving fast.
- **Sprite packs** — animated character over the cursor: GIFs (own timing),
  single PNGs, emoji chars, or numbered frame sequences (`seq`) for 3D
  turntables. Ships with `anime`, `sigil3d` (24-frame turntable), `moon3d`
  (36-frame crescent+ring), and `starlight` (39 OpenMoji/Noto/Commons sprites).
  Bob + spin + looping frames, all tunable.
- **Profiles** — `macos` (peak 3.0), `snappy` (3.2), `smooth` (2.6),
  `reduced` (motion-restrained, alpha-only fade).
- **Cursor Soul Studio** (`cursor_ctl.py`) — GTK controller: on/off, profile
  picker, sliders, pack chooser with sequence thumbnails, GIF import,
  test-shake button, and a live 60 fps preview that runs the *same*
  `magic_core` math as the daemon.
- **Hot reload** — save `config.json` and the daemon picks it up via mtime
  polling; no restart.

## Requirements

- Arch Linux running **Hyprland** (Dusky config layout recommended)
- `python-gobject` (`gi`) with **GTK 3** and the **zwlr layer-shell** protocol
- `Pillow` (sprite/GIF decoding)
- `evdev` *(optional)* — needed only for click FX; the daemon runs fine as the
  `input` group without special privileges (read-only device access)
- Run with **`/usr/bin/python3`** (system Python has `gi` + `PIL`; conda
  Python does not)

## Install

```bash
git clone https://github.com/Starlightmii/dusky-cursor-magic ~/Projects/dusky-cursor-magic
cd ~/Projects/dusky-cursor-magic && ./install.sh
```

`install.sh` copies packs + a default config to
`~/.config/dusky/cursor-magic/`, starts the daemon now, and adds an autostart
line to `~/.config/hypr/source/autostart.lua` (a `.bak` is kept):

```lua
hl.exec_cmd("~/Projects/dusky-cursor-magic/cursor_magic.py")
```

Restart the daemon: `pkill -f '[c]ursor_magic.py' && ~/Projects/dusky-cursor-magic/cursor_magic.py &`

## Using the Studio

```bash
/usr/bin/python3 cursor_ctl.py        # GUI controller
/usr/bin/python3 cursor_ctl.py --selftest   # headless smoke test (exit 0 = ok)
```

Toggle the overlay, switch profiles, tune sliders, pick a pack, or import any
GIF (it's copied into `~/.config/dusky/cursor-magic/packs/`). Changes write to
`config.json` and the daemon hot-reloads them.

## Configuration reference

`~/.config/dusky/cursor-magic/config.json`, merged over
`config.default.json`. Every key:

| Key | Default | Meaning |
|---|---|---|
| `wiggle.window_s` | `0.35` | Velocity/reversal sliding-window length (s) |
| `wiggle.min_speed` | `900.0` | px/s a sample pair needs to count as a reversal |
| `wiggle.need` | `2` | (legacy) reversals kept in window |
| `wiggle.tau_s` | `0.42` | Heat decay time-constant ≈ 1.5 s visible sustain |
| `wiggle.gain` | `0.45` | Heat deposited per qualifying reversal |
| `wiggle.reversal_speed` | `4000.0` | px/s at which a reversal deposits full gain |
| `wiggle.arm_heat` | `0.55` | Heat level that fires the one-shot pulse |
| `motion.profile` | `"macos"` | `macos` / `snappy` / `smooth` / `reduced` |
| `motion.peak_scale` | `3.0` | Aura magnification at full heat (profile preset value) |
| `motion.start_scale` | `0.35` | Resting aura scale |
| `stars.enabled` | `true` | Star bursts on flick reversals |
| `stars.per_burst` | `10` | Stars emitted per burst |
| `stars.color` | `[1.0, 0.95, 0.75]` | Star RGB (0–1 floats) |
| `sprite.bob` | `true` | Vertical bob while the sprite is up |
| `sprite.spin` | `true` | Slow rotation of the sprite |
| `sprite.size` | `1.0` | Sprite scale multiplier |
| `sprite.frame_loop` | `true` | Loop GIF/seq frames continuously |
| `aura.trail` | `true` | Comet trail while moving fast |
| `canvas_px` | `512` | Overlay canvas size (px, square) |
| `glow.color` | `[0.78, 0.82, 1.0]` | Aura tint RGB |
| `glow.soft_alpha` | `0.1` | Outer soft-glow layer opacity |
| `glow.inner_alpha` | `0.16` | Inner ring opacity |
| `glow.outer_r` | `0.49` | Outer glow radius (fraction of canvas) |
| `glow.bloom_alpha` | `0.12` | Bloom pass opacity |
| `sparkles` | `8` | Ambient sparkle particles around the aura |
| `tick_ms` | `8` | Frame tick (≈125 Hz cap; draw throttles to ~60 fps) |
| `blur_layerrule` | `true` | Add Hyprland blur windowrule for the overlay surface |
| `pack_dir` | `~/.config/dusky/cursor-magic/packs` | Where packs live |
| `emotion` | `"girl"` | Emotion label to draw from the active pack |
| `clicks.stars` | `true` | Star burst on mouse press |
| `clicks.ripples` | `true` | Expanding ring on click; double-click = bigger ring |
| `disabled` | `false` | Master off switch (Studio writes this) |
| `sprite_pack` | `""` | Active pack name; `""` = no sprite, aura only |

## Sprite pack format

A pack is a directory containing `manifest.json`:

```json
{
  "name": "sigil3d",
  "attribution": "optional credits string",
  "emotions": {
    "sigil": { "type": "seq",   "path": "frames/", "frames": 24, "fps": 24 },
    "girl":  { "type": "gif",   "path": "girl.gif" },
    "star":  { "type": "png",   "path": "star.png" },
    "wow":   { "type": "emoji", "char": "✨" }
  }
}
```

- `gif` — multi-frame GIF, uses its own per-frame durations (min 20 ms)
- `png` — single static image
- `seq` — directory of numbered frames played at `fps`
- `emoji` — rendered as a text glyph, no assets needed

Paths are relative to the pack directory. The Studio's pack chooser scans
`pack_dir` and thumbnails every type.

### Bundled packs

| pack | kind | source |
|---|---|---|
| `starlight` | 39 png/gif emotions | OpenMoji (CC BY-SA), Noto (OFL), Wikimedia Commons |
| `anime` | gif | bundled demo sprite |
| `sigil3d` / `moon3d` | 24f / 36f seq | procedural turntables (`scripts/render3d*.py`) |
| `orb3d` / `star3d` | 60f / 48f seq | procedural sphere + sparkle (`scripts/render3d_pro.py`) |
| `crystal3d` / `crown3d` | 36f / 24f seq | procedural gem/crown (`scripts/render3d_gem.py`) |
| `fluent3d` | 15 png | Microsoft Fluent 3D emoji (MIT) |
| `particlefx` | 12 png | Kenney Particle Pack (CC0) |
| `animated` | 18 gif (24–37f) | Fluent Emoji animated APNG→GIF (MIT) |
| `gloss3d` | 7 png | 3dicons glossy 3D set (CC0) |
| `spells` | 5 seq (orbsoul/firebrand/fireball/voidorb/ghostsmoke) | spell_animations sheets, gutter-sliced (CC BY 4.0) |
| `planet3d` / `rune3d` | 60f / 48f seq | procedural planet + rune turntables (`scripts/render3d_planet_rune.py`) |
| `imported/*` | seq | your own GIFs / frame folders via the studio Import button |

## How it works

`cursor_magic.py` is a **GTK3 layer-shell overlay**: `exclusive_zone = 0`,
`keyboard_mode = none`, no input region — clicks and keys pass straight
through to whatever is under it. Each tick it queries the Hyprland socket
(`cursorpos`, non-blocking) for the pointer, feeds it through
`SpeedEstimator` → `WiggleDetector` (heat) → `AuraMachine` (critically-damped
spring, k/ζ per profile) and paints with Cairo. Click FX come from
`clicks.py`, a **zero-dependency read-only evdev watcher** (no uinput, never
grabs the device, survives unplug/replug). Config changes are detected by
**mtime polling** — write `config.json` and the daemon reloads live.

## Reduced motion

`motion.profile = "reduced"` pins scale to 1.0 and switches the aura to an
alpha-only fade — stars and trail suppressed — for anyone who needs motion
restrained. No OS-level motion setting is read; this is explicit in config.

## Credits & sources

- Shake-to-find behavior researched from **KWin `shakecursor`** (3× magnitude,
  2 s hold, InOutCubic deflate), **macOS** accessibility cursor (~3×), and
  **PowerToys** "Find my mouse" (500 ms sonar rings) — see
  `research/find-my-cursor.md`.
- `starlight` pack: **OpenMoji** (CC BY-SA 4.0), **Noto** (SIL OFL 1.1),
  images via **Wikimedia Commons**.
- 3D packs rendered offline by `scripts/render3d.py` / `render3d_moon.py` /
  `render3d_pro.py` / `render3d_gem.py` (numpy/Pillow turntable projectors).
- `fluent3d`: **Microsoft Fluent UI Emoji** 3D set (MIT). `particlefx`:
  **Kenney Particle Pack** (CC0).
- Core math verified by `test_magic_core.py`: `/usr/bin/python3
  test_magic_core.py` → ALL PASS.
