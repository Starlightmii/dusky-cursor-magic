#!/usr/bin/env bash
# Install Cursor Soul as a systemd --user service (survives reboot/relogin).
set -e
cd "$(dirname "$0")/.."
cp scripts/systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
# hand ownership from any manual spawns to systemd
systemctl --user stop cursor-soul.service 2>/dev/null || true
for p in $(pgrep -f 'python3? (-u )?[^ ]*shader_soul[.]py'); do
  [ "$p" != "$$" ] && kill -TERM "$p" 2>/dev/null || true
done
sleep 1.5
systemctl --user enable --now cursor-soul.service
sleep 2
systemctl --user is-active cursor-soul
echo "souls=$(pgrep -cf 'python3? -u [^ ]*shader_soul[.]py')"
