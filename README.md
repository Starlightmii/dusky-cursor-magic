# dusky-cursor-magic ✨

Flick your mouse fast → an anime girl bursts over the cursor in a soft glass
glow, wobbles like a spring, then smoothly shrinks away. The real cursor is
never replaced; the overlay is fully click-through (verified by a live
uinput click test on Hyprland 0.56.2).

Works on Dusky Arch / Hyprland (Lua config), no root, no new packages —
GTK3 layer-shell + python-gobject + Pillow, all already on Dusky.

## How

- 60 Hz loop polls the raw Hyprland socket for `cursorpos` (0.02 ms/call).
- Sliding-window speed estimator; a flick ≥ `threshold` px/s triggers a burst.
- easeOutElastic scale curve (overshoot ~1.35, macOS-ify feel), hold, cubic shrink.
- Radial frosted halo + optional compositor `blur` layerrule = "private
  environment" around the cursor; everything else on screen untouched.

## Run / demo

    /usr/bin/python3 cursor_magic.py            # daemon (live flick detection)
    /usr/bin/python3 cursor_magic.py --demo girl  # force one burst
    ./install.sh                                # copy packs, autostart hook

Config: `~/.config/dusky/cursor-magic/config.json` (`threshold`, `hold_s`,
`shrink_s`, `peak_scale`, `glass`, `emotion`, …). Kill with `pkill -f cursor_magic.py`.

## Your own GIFs / emotion packs

Drop any transparent GIF (or PNG) into
`~/.config/dusky/cursor-magic/packs/<name>/` with a `manifest.json`:

    {"emotions": {"girl": {"type": "gif", "path": "girl.gif"}}}

`"emotion": "random"` cycles all loaded emotions; name one to pin it. Emoji
`"type": "emoji", "char": "😡"` also works.

## Tests

    /usr/bin/python3 test_magic_core.py   # core state machine, headless

## Status

Live-verified: flick burst = real girl GIF overlay, alpha passthrough,
smooth shrink-back. Pushed to Starlightmii/dusky-cursor-magic.
