#!/bin/bash
cd ~/Projects/dusky-cursor-magic
mkdir -p "$HOME/.cache/cursor-magic"
# kill ONLY daemon procs whose argv starts with the interpreter + our script
# (never matches a shell that merely mentions cursor_magic.py in its command —
#  the pkill -f self-match trap, this time via pgrep -f on the wrapper's argv)
for p in $(pgrep -f "python3? .*/cursor_magic\.py$"); do kill "$p" 2>/dev/null; done
sleep 0.4
setsid /usr/bin/python3 cursor_magic.py >$HOME/.cache/cursor-magic/magic.log 2>&1 & echo $! > $HOME/.cache/cursor-magic/magic.pid
sleep 1.2
echo "daemon: $(cat $HOME/.cache/cursor-magic/magic.pid) alive=$(kill -0 $(cat $HOME/.cache/cursor-magic/magic.pid) 2>/dev/null && echo yes)"
head -5 $HOME/.cache/cursor-magic/magic.log
