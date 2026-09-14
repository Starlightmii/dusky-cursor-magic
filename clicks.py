#!/usr/bin/env python3
"""Zero-dep evdev click detector. Watches /dev/input/event* for BTN_LEFT/RIGHT/MIDDLE.

Capability filter uses /proc/bus/input/devices (name + mouse handler) instead of an
EVIOCGBIT ioctl scan -- stdlib-only. ponytail: cheap heuristic; switch to fcntl.ioctl
EVIOCGBIT if a click-capable non-mouse device ever matters.
"""
import os, re, select, struct, sys, threading, time

# struct input_event = 24 bytes on 64-bit (time_t=8); 16 on 32-bit (time_t=4).
EVPACK = "=QQHHiI" if sys.maxsize > 2**32 else "=IIHHiI"
EVENT = struct.calcsize(EVPACK)
BTN = {0x110: "left", 0x111: "right", 0x112: "middle"}
DBL_GAP = 0.35


def parse(buf):
    """bytes -> [(t, type, code, value), ...] for whole 24-byte events."""
    out = []
    for i in range(len(buf) // EVENT):
        s, us, t, code, value, _ = struct.unpack_from(EVPACK, buf, i * EVENT)
        out.append((s + us / 1e9, t, code, value))
    return out


def click_capable_devices():
    """/dev/input/eventN paths for mouse/touchpad-like devices, {path: name}."""
    dev = {}
    for blk in open("/proc/bus/input/devices").read().split("\n\n"):
        name = re.search(r'N:\s*Name="([^"]*)"', blk)
        hnd = re.search(r"H:\s*Handlers=([^\n]*)", blk)
        if not (name and hnd):
            continue
        handlers = hnd.group(1).split()
        if not any(h.startswith("event") for h in handlers):
            continue
        low = name.group(1).lower()
        if "mouse" in handlers or "mouse" in low or "touchpad" in low:
            for h in handlers:
                if h.startswith("event"):
                    p = "/dev/input/" + h
                    if os.path.exists(p):
                        dev[p] = name.group(1)
    return dev


class ClickWatcher(threading.Thread):
    """Daemon thread: select() over all click-capable fds, emits press/release/dbl."""

    def __init__(self):
        super().__init__(daemon=True)
        self._cb = None
        self._lock = threading.Lock()
        self._pending = []
        self._open = {}  # fd -> path
        self._buf = b""
        self._last_left = 0.0
        self._down = set()
        self._stop = threading.Event()

    def start(self, on_event=None):  # type: ignore[override]
        self._cb = on_event
        super().start()

    def stop(self):
        self._stop.set()

    def pop_pending(self):
        with self._lock:
            out, self._pending = self._pending, []
        return out

    def _emit(self, kind, button, t):
        evt = {"kind": kind, "button": button, "t": t}
        if self._cb:
            self._cb(evt)
        else:
            with self._lock:
                self._pending.append(evt)

    def _rescan(self):
        for path in click_capable_devices():
            if path in self._open.values():
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                self._open[fd] = path
            except OSError:
                pass  # vanished or busy; retried next scan

    def _drop(self, fd):
        self._open.pop(fd, None)
        try:
            os.close(fd)
        except OSError:
            pass

    def run(self):
        next_scan = 0.0
        while not self._stop.is_set():
            if time.time() >= next_scan:
                self._rescan()
                next_scan = time.time() + 2.0
            if not self._open:
                time.sleep(0.2)
                continue
            try:
                rdy, _, _ = select.select(self._open, [], [], 0.5)
            except (OSError, ValueError):  # all fds died mid-select
                for fd in list(self._open):
                    self._drop(fd)
                continue
            for fd in rdy:
                try:
                    chunk = os.read(fd, 4096)
                except BlockingIOError:
                    continue
                except OSError:  # device vanished
                    self._drop(fd)
                    continue
                if not chunk:  # EOF
                    self._drop(fd)
                    continue
                self._buf += chunk
                head = (len(self._buf) // EVENT) * EVENT
                events, self._buf = parse(self._buf[:head]), self._buf[head:]
                for t, typ, code, value in events:
                    if typ == 1 and code in BTN:
                        self._handle(t, BTN[code], value)

    def _handle(self, t, button, value):
        if value not in (0, 1):  # autorepeat=2: treat as nothing new
            return
        if value == 1:
            dbl = (button == "left" and button not in self._down
                   and 0 < t - self._last_left <= DBL_GAP)
            self._down.add(button)
            if button == "left":
                self._last_left = t
            self._emit("press", button, t)
            if dbl:
                self._emit("dbl", button, t)
        else:
            self._down.discard(button)
            self._emit("release", button, t)


def _selftest():
    # (a) synthetic stream: press, release, press(<0.35s), release
    def ev(t, code, value):
        return struct.pack(EVPACK, int(t), int(t % 1 * 1e6), 1, code, value, 0)
    w = ClickWatcher()
    got = []
    w._cb = got.append
    t0 = time.time()
    stream = ev(t0, 0x110, 1) + ev(t0 + 0.05, 0x110, 0) + ev(t0 + 0.1, 0x110, 1) + ev(t0 + 0.3, 0x110, 0)
    for t, typ, code, value in parse(stream):
        w._handle(t, BTN[code], value)
    kinds = [g["kind"] for g in got]
    assert kinds == ["press", "release", "press", "dbl", "release"], kinds
    # (b) real devices
    devs = click_capable_devices()
    assert devs, "no click-capable device found"
    print("click-capable devices:")
    for p, n in sorted(devs.items()):
        print(f"  {p}: {n}")
    print("selftest OK")


if __name__ == "__main__":
    _selftest()
