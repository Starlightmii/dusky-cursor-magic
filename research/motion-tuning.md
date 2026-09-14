# Motion tuning — making the cursor feel alive (audit + upgrade spec)

Audit of the live draw path (`cursor_magic.py` tick/draw/_comet/_click_ripples/
_star_burst/_draw_sprite) against the macOS/KWin shake-find references in
`find-my-cursor.md`. Ranked by wonder-per-effort. Status column: what shipped.

## Gaps found

1. **Aura is round, always** — real macOS motion squashes/stretches with
   velocity direction; ours never does. (Status: FIXED)
2. **Click ripple radius is linear in age** (`r = 0.06+0.42*uu`) — no
   ease-out, no overshoot; reads mechanical vs PowerToys sonar's snappy
   expand-then-settle. (Status: FIXED)
3. **Star burst size is constant** regardless of how hot the shake was —
   a gentle flick and a violent shake burst identically. (Status: FIXED)
4. **Comet trail** is line segments tapered by life — good, but joints are
   bare (no sparkle nodes). (Status: documented; candidate)
5. **Sprite has no velocity response** — bob/spin only; no squash while
   darting. (Status: documented; candidate — needs speed feed into
   `_draw_sprite`, slightly more invasive)
6. **Idle shimmer** — cursor is invisible when idle (surface only exists
   while hot — deliberate battery choice). A 0.3-alpha idle breathing
   mode would need the surface always-mapped; documented, not shipped.
7. Spring params (k=180, ζ=0.9 macos profile) already match the kwin
   3x/2s reference — no change needed; verified in PROFILES.

## Shipped upgrades (this pass)

All in `cursor_magic.py`, zero new config keys, all draw-path only:

1. **Velocity squash-stretch** (draw): the aura ellipse is scaled along the
   instantaneous velocity axis by `1 + 0.18*min(1, speed/3000)` and squeezed
   perpendicular (`1/sqrt(s)`), so a fast dart elongates like a comet of
   light. Speed from `(cursor - prev_cursor)/dt` already tracked per tick.
2. **EaseOutBack ripple** (`_click_ripples`): `uu -> 1 + 2.7*(uu-1)^3 +
   1.7*(uu-1)^2` overshoot ~7% past target then settles — the sonar "boing".
3. **Heat-scaled star bursts** (`_star_burst`): star radius multiplier
   `0.6 + 0.8*heat` — gentle flicks sparkle small, violent shakes erupt.

## Candidates not shipped (upgrade path)

- Trail sparkle nodes: dot at every 3rd trail joint, size ~ life.
- Sprite squash: pass speed into `_draw_sprite`, scale along motion axis.
- Idle shimmer: config `idle_shimmer` bool; keep surface mapped at low alpha
  with a 4s breath sine. Cost: surface always mapped (battery).
- Heat-tinted aura hue: lerp glow color toward warm at high heat.

## Applied 2026-09-14 pass (U1–U8, in commit 2718582)

Token-router's numbered spec, applied to `magic_core.py` + `cursor_magic.py`
(U2/U3/U6 partly earlier by coordinator — lanes merged). Measured on
`AuraMachine` @240Hz, default macos profile: **enter t95 = 246 ms,
exit t95 = 233 ms, overshoot = 0.1%** (KWin reference band ~200 ms, was 320 ms).

| ID | Change | Where | Params |
|----|--------|-------|--------|
| U1 | Leaky-peak energy — melts with aura instead of pinning at last shake | `AuraMachine.update/energy` | e-fold τ=0.35 s; zeroed on settle |
| U2 | Energy-scaled star bursts (size + speed) | `StarField.burst(size=)` | `size=0.6+0.8*heat` from wiggle heat |
| U3 | Spring retune + asymmetric melt | `SPRINGS["macos"]`, `update()` | k=260, ζ=0.88; exit k×1.6, ζ+0.12 |
| U4 | Smoothed glow center (35 ms follower) | `cursor_magic` `_sm` | dt-correct lerp, kills raw-pos jitter |
| U5 | Ambient whisper via SpeedEstimator | `aura.update(t, heat, amb)` | config `ambient{min_speed 150, range 900, max_gain 0.35}` |
| U6 | EaseOutBack click ripple | `cursor_magic` ripples | 450 ms, back-ease "boing" |
| U7 | Speed-reactive tapered comet trail | `cursor_magic` trail | 0.35 s window, 350 ms taper, width=f(speed) |
| U8 | Idle shimmer — 3 orbiting stars at rest | `cursor_magic._shimmer` | `idle_shimmer: true`, clock `_last_alive` |

Regression gates: `test_motion.py` (U1 melt <0.35 after 2.7 s calm, U3 k≥220,
U2 burst scaling, reduced-motion pin) + `test_magic_core.py` + lifecycle
`scripts/selfcheck.sh`. Notes: `need` kwarg on WiggleDetector is a deprecated
no-op kept for `**cfg["wiggle"]` compatibility — do not delete.
Idle-shimmer/sprite-squash candidates above are now shipped (U8, aura
squash-stretch in tick); remaining unbuilt: trail sparkle nodes, heat-tinted hue.
