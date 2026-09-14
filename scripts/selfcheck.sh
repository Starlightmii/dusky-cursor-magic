#!/bin/bash
cd ~/Projects/dusky-cursor-magic
mkdir -p "$HOME/.cache/cursor-magic"
for p in $(pgrep -f "^[^ ]*python3? [^ ]*cursor_magic\.py"); do kill "$p" 2>/dev/null; done
sleep 0.4
setsid /usr/bin/python3 cursor_magic.py --demo girl >$HOME/.cache/cursor-magic/magic.log 2>&1 & echo $! > $HOME/.cache/cursor-magic/magic.pid
/usr/bin/python3 - <<'PY'
import json, subprocess, time
t0 = time.time(); prev = None
while time.time() - t0 < 4.0:
    d = json.loads(subprocess.run(['hyprctl','layers','-j'],capture_output=True,text=True).stdout)
    on = any(l['namespace']=='dusky-cursor-magic' for lv in d['eDP-1']['levels'].values() for l in lv)
    if on != prev:
        print(f"{time.time()-t0:5.2f}s surface={'ON' if on else 'OFF'}")
        prev = on
    time.sleep(0.04)
PY
for p in $(pgrep -f "^[^ ]*python3? [^ ]*cursor_magic\.py"); do kill "$p" 2>/dev/null; done
sleep 0.4
setsid /usr/bin/python3 cursor_magic.py >$HOME/.cache/cursor-magic/magic.log 2>&1 & echo $! > $HOME/.cache/cursor-magic/magic.pid
sleep 1.0; echo "restored live: $(cat $HOME/.cache/cursor-magic/magic.pid) alive=$(kill -0 $(cat $HOME/.cache/cursor-magic/magic.pid) 2>/dev/null && echo yes)"
