#!/usr/bin/env bash
# restart soul: systemd owns it when the unit is active; else exact-pid kill+spawn
if systemctl --user is-active --quiet cursor-soul; then
  systemctl --user restart cursor-soul
else
  for p in $(pgrep -f 'python3? -u [^ ]*shader_soul[.]py'); do kill -TERM "$p" 2>/dev/null; done
  sleep 1.5
  cd ~/Projects/dusky-cursor-magic
  setsid /usr/bin/python3 -u shader_soul.py </dev/null >/tmp/soul.log 2>&1 &
fi
sleep 2
echo "souls now: $(pgrep -cf 'python3? -u [^ ]*shader_soul[.]py')"
echo "pidfile: $(cat ~/.cache/cursor-magic/soul.pid)"
