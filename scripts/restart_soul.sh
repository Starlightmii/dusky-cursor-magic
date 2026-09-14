#!/bin/bash
# restart soul cleanly: kill ALL souls by exact pid, wait, relaunch one
for p in $(pgrep -f 'python3? -u [^ ]*shader_soul[.]py'); do
  kill -TERM "$p" 2>/dev/null
done
sleep 1.5
for p in $(pgrep -f 'python3? -u [^ ]*shader_soul[.]py'); do
  kill -KILL "$p" 2>/dev/null
done
sleep 0.5
cd ~/Projects/dusky-cursor-magic
setsid /usr/bin/python3 -u shader_soul.py </dev/null >/tmp/soul.log 2>&1 &
sleep 2
echo "souls now: $(pgrep -cf 'python3? -u [^ ]*shader_soul[.]py')"
echo "pidfile: $(cat ~/.cache/cursor-magic/soul.pid)"
pgrep -af 'python3? -u [^ ]*shader_soul[.]py'
