# Cursor Soul — an alive cursor aura for Hyprland (Dusky)

One tiny daemon (`shader_soul.py`): a GPU-rendered living aura with galaxy
stars and supernovae that follow your pointer — and never hide what's under it.

## What it does
- **see-through aura**: a clear hole under the whole arrow glyph + a 0.72
  alpha cap on the veil — text and icons under the cursor stay readable
- **alive**: breathes, twitches when alone, leans toward the pointer like a pet
- **surface aware** (`--surface`): 2 Hz grim sample under the pointer — shines
  harder over dark UI, dims over bright paper (firefly instinct)
- **music synced** (`--music`): PipeWire monitor tap → bass swells the radius,
  treble brightens the glow, beats flare the energy and sprinkle stars
- **galaxy tail**: star sparkles shed along the path — spacing tightens with
  speed (30px → 12px), so a fast sweep paints a dense comet
- **speed galaxy**: hard sustained sweeps drag 6-star mini-bursts along the path
- **SUPERNOVA**, two ways:
  - slam on the brakes after a fast sweep → white-hot detonation
  - just park the mouse 9–15 s → a BIG detonation (24-ring blast) with an echo
    shockwave 0.25 s later
  - Sedov–Taylor blast physics: `R ∝ t^0.4` front, `t^-1.2` pressure decay
- **click burst**: layered ring + hero + golden micro-stars, log-spiral arms
- **GPU**: GLES3 surfaceless render of the aura field on the iGPU
  (`--renderer gpu`, auto CPU fallback), ~2× faster than numpy

## Install / run
```sh
./scripts/install_services.sh      # systemd user unit + enable
./scripts/restart_soul.sh          # restart (systemd owns the flock)
./scripts/selfcheck.sh             # gates + live health
```

## Flags
`--radius 34 --glow 0.50 --fps 60 --renderer gpu|cpu --music on|off
--homing on|off --surface on|off` (live config:
`~/.config/dusky/cursor-magic/config.json` → `{"soul": {"hide_arrow": true,
"radius": 34, ...}}`, polled at 1 Hz; theme auto-follows
`~/.cache/wal/colors.json`)

## Tuning constants (`shader_soul.py` top)
`RIPPLE_LIFE 0.85` · `MAX_ALPHA 0.72` (veil cap) · idle-nova window
`random.uniform(9, 15)` · shed spacing `max(12, 30-18*speed)` px

## Gates
```sh
python3 shader_soul.py --test && for t in test_*.py; do python3 $t; done
```
`--test` (see-through hole + speed-grows physics) · `test_idle_nova.py` ·
`test_stars.py` · `test_shockwave.py` · `test_sedov_decay.py` ·
`test_gl_parity.py` (GPU↔CPU lockstep) · `test_aura_screen.py` (real screen) ·
`test_music.py` · `test_orb_squash.py` · `test_click_parse.py`
