#!/usr/bin/env bash
# Install cursor magic as systemd --user services (survive reboot/relogin).
set -e
cd "$(dirname "$0")/.."
cp scripts/systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
# hand ownership from any manual spawns to systemd
systemctl --user stop cursor-magic.service cursor-soul.service 2>/dev/null || true
for p in $(pgrep -f 'python3? (-u )?[^ ]*/?(shader_soul|cursor_magic)[.]py'); do
  [ "$p" != "$$" ] && kill -TERM "$p" 2>/dev/null || true
done
sleep 1.5
systemctl --user enable --now cursor-magic.service cursor-soul.service
sleep 2
systemctl --user is-active cursor-magic cursor-soul
echo "daemons=$(pgrep -cf 'python3? [^ ]*cursor_magic[.]py') souls=$(pgrep -cf 'python3? -u [^ ]*shader_soul[.]py')"
