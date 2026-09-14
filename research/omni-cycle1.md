# @omni-router cycle-1 research (Cursor Soul)

## Assets (all license-checked)
- N64 Medallions — CC0, animated elemental icon seqs (fire/water/earth/air/light/darkness), per-frame PNGs.
- Gem Jewel Diamond Glass — CC-BY 3.0 (Osmic), raytraced-look gems.
- CC0 Gem Icons (AntumDeluge), Gothicvania Magic Pack 9 (ansimuz) — CC0 VFX sheets.
- Animated Blue Ring Explosion — CC0, ~20-frame transparent ring = literal click-ripple asset. Ring Explosion — CC0. Kenney particle packs — CC0.

## Compositing verdict
- GTK4 GskGLShader deprecated since 4.16 → dead end (matches my failed GLArea-on-Mesa test).
- wlr-layer-shell + raw EGL = the way if GPU shader needed (Duckonaut/glshell skeleton).
- Our current path (numpy field → cairo blit into layer OVERLAY) stays valid: proven visible, ~70% core at 256px/60fps.

## Motion baselines
- PowerToys find-my-mouse: 100px spotlight, 1000ms shake window.
- hypr-dynamic-cursors: 100ms tilt window, stick/drag/pendulum models.
- Material: micro 50-100ms (ripples), decelerate on entry.
- macOS butter ≈ critically-damped follow (ζ≈1, settle 120-180ms), speed→size smoothstep, click ripple 50-100ms rise / 200-300ms total, trail 3-5 ghosts exp-decay.
- Already shipped that shape: ambient_gain γ=0.3 (token-router cycle-4) + soul field grow/spring/ripple (12fc78a).

## Real-3D pipeline (verified on this box)
- pyrender 0.1.45 + trimesh 5.1.0 + PyOpenGL EGL (PYOPENGL_PLATFORM=egl) renders transparent turntables: DamagedHelmet CC-BY 16 frames @17ms/frame. Wheels cached in /tmp/wheels; scripts /tmp/{turntable,gem,helmet}_test.py.
- Upgrade path for scripts/render3d_model.py when we want real PBR lighting instead of painter sort.
