# Cursor Soul — a living star for Hyprland (Dusky)

One tiny daemon (`shader_soul.py`): the pointer is a star with a life cycle.

## The cycle
- **rest = nothing**: at rest you see only the Dusky default cursor — no
  ambient glow, ever
- **stay long → black hole → supernova**: park 9–15 s and a void *gathers*
  (opaque event-horizon disk at the pointer, particles spiral inward), then
  it implodes and detonates: BIG blast (24-ring + hero stars, radius swell,
  ~1.5 s white-hot bloom), Sedov–Taylor shockwave + echo ring at +0.25 s.
  Every long stay repeats gather → blast
- **moving → soft tail**: fly gently and a small capped star tail trails the
  pointer (stars peak at 0.75 alpha — reads soft, never hides the surface)
- **flying FAST → galaxy blast**: sustained high speed (EMA > 0.85)
  detonates the biggest blast — triple supernova + shockwaves at 3x reach,
  mirrored on a fullscreen layer so the wave crosses the *whole space*, no
  hidden box
- **clicks / music**: no light (music only modulates the nova via `--music`)

## Install / run
```sh
./scripts/install_services.sh      # systemd user unit + enable
./scripts/restart_soul.sh          # restart (systemd owns the flock)
./scripts/selfcheck.sh             # gates + live health
```
Off: `systemctl --user disable --now cursor-soul.service` (Dusky default
cursor returns; the daemon restores the arrow on exit either way).

## Flags
`--radius 34 --glow 0.50 --fps 60 --renderer gpu|cpu --music on|off
--homing on|off --surface on|off` (live config:
`~/.config/dusky/cursor-magic/config.json` → `{"soul": {"hide_arrow": true,
"radius": 34, ...}}`, polled at 1 Hz; theme auto-follows pywal
`~/.cache/wal/colors.json`).

## How it works
GTK layer-shell overlay (overlay ns, click-through) follows
`hyprctl cursorpos` at --fps; aura = numpy premultiplied field (GPU GLES3
surfaceless shader via `soul_gl.py`, auto CPU fallback); ripples expand by
Sedov–Taylor; the window itself only carries the soul — blast waves that
outrun it paint on the fullscreen `bwin` layer while alive.

## Gates (run them all)
`shader_soul.py --test` · `test_soul_cycle9.py` (phase machine, void disk,
BIG ripple reach, tail caps) · `test_idle_nova.py` · `test_stars.py` ·
`test_shockwave.py` · `test_sedov_decay.py` · `test_music.py` ·
`test_orb_squash.py` · `test_click_parse.py` · `test_gl_parity.py` (GPU≈CPU)
· `test_aura_screen.py` (real-screen lifecycle: rest black, soft tail,
fast→blast, park→nova).

## Tuning the cycle
`soul_phase()` in `shader_soul.py`: gather lead 5 s, nova window 9–15 s,
blast threshold speed 0.85, cooldown 2 s, `BIG_K = 3.0` (blast reach),
tail cap 0.75. Star travel: `_add(..., r0=)` — implode stars are born on a
far ring and negative speed walks them home.
