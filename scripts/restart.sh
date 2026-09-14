#!/bin/bash
cd ~/Projects/dusky-cursor-magic
mkdir -p "$HOME/.cache/cursor-magic"
for p in $(pgrep -f "[c]ursor_magic.py"); do kill "$p" 2>/dev/null; done
sleep 0.4
setsid /usr/bin/python3 cursor_magic.py >$HOME/.cache/cursor-magic/magic.log 2>&1 & echo $! > $HOME/.cache/cursor-magic/magic.pid
sleep 1.2
echo "daemon: $(cat $HOME/.cache/cursor-magic/magic.pid) alive=$(kill -0 $(cat $HOME/.cache/cursor-magic/magic.pid) 2>/dev/null && echo yes)"
head -5 $HOME/.cache/cursor-magic/magic.log
