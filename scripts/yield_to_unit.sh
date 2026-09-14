#!/bin/bash
# kill every soul EXCEPT the systemd unit's MainPID, then make sure the unit owns it
unit=$(systemctl --user show cursor-soul -p MainPID --value)
for p in $(pgrep -f 'python3? -u /home/starlight/Projects/dusky-cursor-magic/shader_soul\.py'); do
  [ "$p" != "$unit" ] && kill -TERM "$p" 2>/dev/null
done
sleep 3
systemctl --user restart cursor-soul
sleep 2
echo "unit=$(systemctl --user show cursor-soul -p MainPID --value) active=$(systemctl --user is-active cursor-soul) souls=$(pgrep -cf 'python3? -u [^ ]*shader_soul[.]py') pidfile=$(cat ~/.cache/cursor-magic/soul.pid)"
