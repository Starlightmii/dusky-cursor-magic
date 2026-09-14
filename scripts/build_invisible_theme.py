#!/usr/bin/env python3
"""Build the "Invisible" XCURSOR theme: every Dusky cursor with all pixels
zeroed (sizes/hotspots kept). This Hyprland fork has no cursor:no_cursor, so
a transparent theme is the only way to hide the system arrow and let the
Cursor-Soul layer be the pointer.

    /usr/bin/python3 scripts/build_invisible_theme.py
    hyprctl setcursor Invisible 24     # hide
    hyprctl setcursor Dusky 18         # show again
"""
import os
import shutil
import struct
import sys

SRC = os.environ.get("CURSOR_SRC", "/usr/share/icons/Dusky/cursors")
if not os.path.isdir(SRC):
    SRC = os.path.expanduser("~/.local/share/icons/Dusky/cursors")
DST = os.path.expanduser("~/.local/share/icons/Invisible/cursors")

XCU_IMAGE = 0xFFFD0002
XCU_ANIM = 0xFFFDFFFE


def build(src=SRC, dst=DST):
    os.makedirs(dst, exist_ok=True)
    with open(os.path.join(os.path.dirname(dst), "index.theme"), "w") as f:
        f.write("[Icon Theme]\nName=Invisible\n"
                "Comment=Transparent cursor (Cursor Soul draws the pointer)\n")
    n = 0
    for name in sorted(os.listdir(src)):
        p = os.path.join(src, name)
        if not os.path.isfile(p):
            continue
        b = bytearray(open(p, "rb").read())
        if b[:4] != b"Xcur":                      # not XCU -> copy as-is
            shutil.copyfile(p, os.path.join(dst, name))
            n += 1
            continue
        _, hdr_bytes, _ver, toc = struct.unpack_from("<4I", b, 0)
        for i in range(toc):
            typ, sub, pos = struct.unpack_from("<3I", b, hdr_bytes + i * 12)
            if typ == XCU_IMAGE:                  # subtype IS the pixel size
                b[pos + 36:pos + 36 + sub * sub * 4] = bytes(sub * sub * 4)
            # XCU_ANIM headers kept intact; their frames are separate toc entries
        with open(os.path.join(dst, name), "wb") as f:
            f.write(b)
        n += 1
    return n


if __name__ == "__main__":
    print(f"Invisible theme: {build()} cursors -> {DST}")
    assert build() == len(os.listdir(SRC)), "count mismatch"