# Cursor Soul

One file. One window. The cursor **is** the soul: a living shader aura that
follows your pointer on Hyprland — no system arrow, no sprites, no GIFs, no
control panel.

- Glowing orb that **squashes along your motion** and round-rests at idle
- **Comet trail** lagging softly behind while you sweep
- Aura **swells with speed**, breathes at rest, settles slow (macOS easing)
- Every click fires a **ripple ring + energy flash** from the pointer
- **Auto Dusky theme colours** — reads `~/.cache/wal/colors.json` at 1 Hz,
  so the soul re-tints itself the moment you change your Dusky theme
  (answers dusklinux/dusky#343 for the cursor: themeable, zero config)
- Fully **click-through** (input-shape recipe), single-instance flock,
  restores the system arrow on exit
- **Music-synced** — taps the PipeWire speakers monitor, reads bass/mid/treble
  + beat: the aura swells on the bass, brightens on hats, flares on kicks
  while you're parked, and sprinkles stars on the downbeat mid-sweep
- **Alive** — damped-spring homing lean (it swings after fast flicks like a
  pet), idle twitch sparkles every few seconds so it never looks dead
- GPU field on the Intel iGPU (`soul_gl.py`, GLES3 surfaceless): stars,
  shockwaves, orb, aura in one fragment pass — ~3% CPU, auto CPU fallback
- ~3% CPU idle / 60fps active

## Install

    ./install.sh          # copies config + systemd --user unit, starts it

Survives reboot / relogin via `cursor-soul.service` (graphical-session).
Tune in `~/.config/dusky/cursor-magic/config.json` → `soul` (`on`,
`hide_arrow`, `radius`, `strength`, `grow`, `glow`).

## Gates

    /usr/bin/python3 shader_soul.py --test   # physics self-check
    /usr/bin/python3 test_orb_squash.py      # squash-along-motion
    /usr/bin/python3 test_click_parse.py     # evdev click parsing
    /usr/bin/python3 test_aura_screen.py     # real screen pixels: speed grows aura
    /usr/bin/python3 test_stars.py           # galaxy burst/nova gates
    /usr/bin/python3 test_shockwave.py       # Sedov vs linear ring
    /usr/bin/python3 test_gl_parity.py       # GPU field == CPU field
    /usr/bin/python3 test_music.py           # beat grid + bands, synthetic track
    bash scripts/selfcheck.sh                # layer alive + click-through
