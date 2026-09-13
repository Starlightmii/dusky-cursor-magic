#!/usr/bin/env bash
# Install dusky-cursor-magic: daemon + packs + autostart hook.
set -eu
SRC="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$SRC/cursor_magic.py"
mkdir -p ~/.config/dusky/cursor-magic
cp -r "$SRC/packs" ~/.config/dusky/cursor-magic/
[ -f ~/.config/dusky/cursor-magic/config.json ] || cp "$SRC/config.default.json" ~/.config/dusky/cursor-magic/config.json
if [ -f ~/.config/hypr/source/autostart.lua ] && ! grep -q cursor-magic ~/.config/hypr/source/autostart.lua; then
  cp ~/.config/hypr/source/autostart.lua ~/.config/hypr/source/autostart.lua.bak
  sed -i '0,/^end)$/s|^end)$|    hl.exec_cmd("'"$HOME"'/Projects/dusky-cursor-magic/cursor_magic.py")\n\nend)|' ~/.config/hypr/source/autostart.lua
fi
"$SRC/cursor_magic.py" & echo $! > /tmp/magic.pid   # start now; autostarts after next login
