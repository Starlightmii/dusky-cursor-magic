# Find-my-cursor — verified research (2026-09-14)

Sources: KDE/kwin source (gh api, read directly), PowerToys headers, Apple support docs,
Microsoft Learn, motion canon (Material 1, NN/g, Apple HIG/WWDC23-10158).

## KWin "Shake Cursor" — the only faithful macOS clone with public source
| constant | value |
|---|---|
| trigger | trail length / bounding-diagonal ≥ 4, rolling 1000 ms window, min diagonal 100 px |
| magnification | 3.0× normal cursor; each re-shake adds +1.0× |
| grow / shrink | 200 ms both ways, `QEasingCurve::InOutCubic` |
| hold | deflate starts 2000 ms after last shake |
| render | hides hw cursor, scales the cursor image — pure scale, no alpha ramp, no color |

## macOS (Apple docs + community reverse)
- No published velocity threshold; "quickly move the mouse back and forth".
- Target ≈ **3×** (community measurements; the "~2×/easeOutBack" internet claim is unbacked).
- Holds enlarged ~1–2 s then shrinks; re-shake while enlarged refreshes.
- Proportional growth is disputed — KWin/bigCursor say energy-scaled, fixed-target per shake.

## Windows
- Built-in "Mouse Sonar" = CTRL press → concentric ripple (duration undocumented;
  PowerToys FindMyMouse, its modern reference: 500 ms animation, radius 100 DIP, zoom 9→1×).
- PowerToys shake-activation alt: min path 1000 px / 1000 ms, path:diagonal ≥ 4× (same detector shape as KWin).

## Motion canon applied
- Springs over fixed durations (Apple WWDC23): ours = critically-damped-ish spring (k=180, ζ=0.9)
  tracking heat continuously → "alive", no gate.
- Exits shorter than enters (Material 1/2: 225/195 ms pair) → our melt is faster than our grow.
- 100–400 ms band; >400 ms reads slow. Our enter-to-peak ≈ 250 ms, full melt ≈ 600 ms of hold + decay.
- Reduce-motion: gsettings `org.gnome.desktop.interface enable-animations` == false
  → `reduced` profile: alpha-only, no scale.

## How dusky-cursor-magic maps it
macOS enlarges the *cursor sprite*; we can't resize Hyprland's theme cursor per-frame without
sudo/uinput, so the **aura+stars ARE the enlargement** — an always-listening glow that scales
with shake energy (heat ∝ reversal speed, τ=0.42 s ≈ KWin's 2 s hold), plus the Starlight
signature: 4-point stars burst on every reversal, comet trail, click ripples (PowerToys sonar),
3D sigil turntable (`scripts/render3d.py`), optional anime sprite past arm_heat=0.55.
Controller: `cursor_ctl.py` (Cursor Soul Studio) — same magic_core math, live preview.
