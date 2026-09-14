#!/bin/bash
cd ~/Projects/dusky-cursor-magic
hyprctl layers -j | /usr/bin/python3 -c "import json,sys;d=json.load(sys.stdin);print([l['namespace'] for m in d.values() for lv in m['levels'].values() for l in lv])"
echo "soul pid=$(cat ~/.cache/cursor-magic/soul.pid) alive=$(kill -0 $(cat ~/.cache/cursor-magic/soul.pid) 2>/dev/null && echo yes)"
