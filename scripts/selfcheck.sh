#!/bin/bash
# Cursor Soul self-check: the layer must appear and click through.
cd ~/Projects/dusky-cursor-magic
mkdir -p "$HOME/.cache/cursor-magic"
if systemctl --user is-active --quiet cursor-soul; then
  systemctl --user restart cursor-soul
else
  for p in $(pgrep -f "^[^ ]*python3? -u? [^ ]*shader_soul\.py"); do kill "$p" 2>/dev/null; done
  sleep 0.4
  setsid /usr/bin/python3 -u shader_soul.py >$HOME/.cache/cursor-magic/soul.log 2>&1 &
fi
/usr/bin/python3 - <<'PY'
import json, subprocess, time
t0 = time.time(); prev = None
while time.time() - t0 < 5.0:
    d = json.loads(subprocess.run(['hyprctl','layers','-j'],capture_output=True,text=True).stdout)
    on = any(l['namespace']=='gtk-layer-shell' for m in d.values() for lv in m['levels'].values() for l in lv)
    if on != prev:
        print(f"{time.time()-t0:5.2f}s soul-surface={'ON' if on else 'OFF'}")
        prev = on
    time.sleep(0.05)
PY
sleep 0.3; echo "live: $(cat $HOME/.cache/cursor-magic/soul.pid) alive=$(kill -0 $(cat $HOME/.cache/cursor-magic/soul.pid) 2>/dev/null && echo yes)"