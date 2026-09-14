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
- ~22% CPU idle / 60fps active on a laptop iGPU (CPU numpy field, cairo blit)

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
    bash scripts/selfcheck.sh                # layer alive + click-through
