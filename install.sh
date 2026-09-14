#!/usr/bin/env bash
# Cursor Soul — the ONLY component. One layer-shell aura that IS the cursor.
set -eu
SRC="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$SRC/shader_soul.py"
mkdir -p ~/.config/dusky/cursor-magic
[ -f ~/.config/dusky/cursor-magic/config.json ] || cp "$SRC/config.default.json" ~/.config/dusky/cursor-magic/config.json
"$SRC/scripts/install_services.sh"
