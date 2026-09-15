# Cursor Soul — an event-only light for Hyprland (Dusky)

One tiny daemon (`shader_soul.py`): a cursor companion that lives in the
dark and speaks in starlight — one only. The soul emits **no ambient glow
at all**: at rest, while moving, clicking, with music playing — black. The
one and only light is the **long-stay supernova**: park your pointer for
9–15 s and it detonates.

## What it does
- **event-only light**: zero ambient glow (rest & transit are pitch black) —
  nothing ever hides under the cursor; the field's only light is the nova
- **SUPERNOVA**: park the mouse 9–15 s → BIG detonation (24-ring blast,
  4 hero stars, radius swells ~2.4x, white-hot flash blooms ~1.5 s) plus a
  Sedov–Taylor shockwave and an echo ring at +0.25 s; moving re-arms the
  window, so the next stay fires fresh
- **alive in the dark**: the soul still leans toward the pointer like a pet
  and tracks the layer window with 2-frame latency compensation (motion,
  not light)
- **surface aware** (`--surface`): grim samples what's under the pointer —
  the nova's brightness adapts (shines over dark UI, dims over paper)
- **music aware** (`--music`): PipeWire tap modulates the nova's radius
  and tint — heard only during the detonation, never as idle glow
- **GPU**: GLES3 surfaceless render on the iGPU (`--renderer gpu`, auto
  CPU fallback); 5% steady CPU while dark

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

## Tuning constants (`shader_soul.py`)
`RIPPLE_LIFE 0.85` · `MAX_ALPHA 0.72` (veil cap) · nova window
`random.uniform(9, 15)` · energy decay `0.955/tick` (~1.5 s bloom) ·
nova radius swell `1.0 + 1.5·min(E, 1.5)`

## The dark design (gates keep it dark)
`shader_soul.py --test` enforces: alpha ≤ 6/255 everywhere at rest AND
moving (event-only black) + the nova flash must light >2 % of the field.
`test_aura_screen.py` measures real screen pixels: rest-glow <5 %,
fast-glow <5 %, and a parked pointer must bloom >20 % within 22 s.

## Gates
```sh
python3 shader_soul.py --test && for t in test_*.py; do python3 $t; done
```
`--test` · `test_idle_nova.py` · `test_stars.py` · `test_shockwave.py` ·
`test_sedov_decay.py` · `test_gl_parity.py` (GPU↔CPU lockstep) ·
`test_aura_screen.py` (real screen) · `test_music.py` ·
`test_orb_squash.py` · `test_click_parse.py`
