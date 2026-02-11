#!/usr/bin/env python3
"""Run a single focus+key test method. Usage: python diag_focus_single.py H"""
import subprocess
import sys
import time

import Quartz  # type: ignore
from AppKit import NSWorkspace  # type: ignore
from ApplicationServices import (  # type: ignore
    AXUIElementCreateApplication,
    AXUIElementPerformAction,
    AXUIElementCopyAttributeValue,
    AXUIElementPostKeyboardEvent,
)

SPACE = 49


def get_frontmost() -> str:
    ws = NSWorkspace.sharedWorkspace()
    f = ws.frontmostApplication()
    return f"{f.localizedName()} (pid={f.processIdentifier()})"


def find_fl():
    """Return (pid, bounds, owner) for FL Studio."""
    ws = NSWorkspace.sharedWorkspace()
    fl_pid = None
    for app in ws.runningApplications():
        name = app.localizedName() or ""
        if "FL Studio" in name:
            fl_pid = app.processIdentifier()
            break
    if fl_pid is None:
        return None, None, None

    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    wl = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    for w in wl:
        owner = w.get("kCGWindowOwnerName", "")
        if "FL Studio" not in owner:
            continue
        if int(w.get("kCGWindowLayer", 0)) != 0:
            continue
        b = w.get("kCGWindowBounds", {})
        x, y = int(b.get("X", 0)), int(b.get("Y", 0))
        ww, wh = int(b.get("Width", 0)), int(b.get("Height", 0))
        if ww > 0 and wh > 0:
            return fl_pid, (x, y, ww, wh), owner
    return fl_pid, None, None


def warp(x, y):
    Quartz.CGWarpMouseCursorPosition(Quartz.CGPointMake(x, y))


def cg_click(x, y, tap=Quartz.kCGHIDEventTap):
    pt = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(tap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(tap, up)


def cg_key(keycode, tap=Quartz.kCGHIDEventTap):
    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventPost(tap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(tap, up)


def countdown(n=5):
    for i in range(n, 0, -1):
        print(f"  {i}...")
        time.sleep(1)


# ── Methods ──────────────────────────────────────────────────────────────────

def method_h(pid, bounds):
    """AXUIElementPostKeyboardEvent — keys direct to PID, NO FOCUS NEEDED."""
    print(f"Method H: AXUIElementPostKeyboardEvent to PID {pid}")
    print("  (Sends Space DIRECTLY to FL Studio — no focus change!)")
    ax_app = AXUIElementCreateApplication(pid)
    countdown()
    print("  >> Sending Space NOW...")
    AXUIElementPostKeyboardEvent(ax_app, 0, SPACE, True)
    time.sleep(0.02)
    AXUIElementPostKeyboardEvent(ax_app, 0, SPACE, False)
    print("  SENT. Watch FL Studio transport bar!")
    time.sleep(4)
    print(f"  Frontmost: {get_frontmost()}")


def method_i(pid, bounds):
    """Dock bounce trick — activate Dock, then FL Studio, then CGEvent key."""
    print(f"Method I: Dock bounce activate + CGEvent Space")
    ws = NSWorkspace.sharedWorkspace()
    dock = fl_app = None
    for app in ws.runningApplications():
        bid = app.bundleIdentifier() or ""
        if bid == "com.apple.dock":
            dock = app
        if app.processIdentifier() == pid:
            fl_app = app

    if dock:
        print("  Activating Dock first...")
        dock.activateWithOptions_(3)
        time.sleep(0.3)
        print(f"  Frontmost after Dock: {get_frontmost()}")

    if fl_app:
        print("  Now activating FL Studio...")
        ok = fl_app.activateWithOptions_(3)
        print(f"  activateWithOptions: {ok}")
        time.sleep(0.5)
        print(f"  Frontmost after FL: {get_frontmost()}")

    countdown()
    print("  >> Sending Space NOW...")
    cg_key(SPACE)
    print("  SENT. Watch FL Studio!")
    time.sleep(4)
    print(f"  Frontmost: {get_frontmost()}")


def method_j(pid, bounds):
    """CGEventPostToPid — post keyboard event directly to FL Studio PID."""
    print(f"Method J: CGEventPostToPid({pid}) Space")
    countdown()
    print("  >> Sending Space via CGEventPostToPid NOW...")
    down = Quartz.CGEventCreateKeyboardEvent(None, SPACE, True)
    up = Quartz.CGEventCreateKeyboardEvent(None, SPACE, False)
    try:
        Quartz.CGEventPostToPid(pid, down)
        time.sleep(0.05)
        Quartz.CGEventPostToPid(pid, up)
        print("  SENT.")
    except Exception as e:
        print(f"  ERROR: {e}")
    time.sleep(4)
    print(f"  Frontmost: {get_frontmost()}")


def method_a(pid, bounds):
    """open -a 'FL Studio' + CGEvent key."""
    print("Method A: open -a 'FL Studio' + CGEvent Space")
    r = subprocess.run(["open", "-a", "FL Studio"], capture_output=True, text=True)
    print(f"  open -a rc={r.returncode} err={r.stderr.strip()}")
    time.sleep(1.0)
    print(f"  Frontmost: {get_frontmost()}")
    countdown()
    print("  >> Sending Space NOW...")
    cg_key(SPACE)
    print("  SENT.")
    time.sleep(4)
    print(f"  Frontmost: {get_frontmost()}")


def method_d(pid, bounds):
    """CGWarp + click (HID + Session) + key."""
    if bounds is None:
        print("ERROR: No FL Studio bounds"); return
    x, y, ww, wh = bounds
    cx, cy = x + ww // 2, y + 50
    print(f"Method D: CGWarp + click at ({cx},{cy}) + Space")

    print("  D1: HID tap click...")
    warp(cx, cy)
    time.sleep(0.1)
    cg_click(cx, cy, Quartz.kCGHIDEventTap)
    time.sleep(0.5)
    print(f"  Frontmost after HID click: {get_frontmost()}")

    print("  D2: Session tap click...")
    warp(cx, cy)
    time.sleep(0.1)
    cg_click(cx, cy, Quartz.kCGSessionEventTap)
    time.sleep(0.5)
    print(f"  Frontmost after Session click: {get_frontmost()}")

    countdown()
    print("  >> Sending Space NOW...")
    cg_key(SPACE)
    print("  SENT.")
    time.sleep(4)
    print(f"  Frontmost: {get_frontmost()}")


METHODS = {
    "H": method_h,
    "I": method_i,
    "J": method_j,
    "A": method_a,
    "D": method_d,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1].upper() not in METHODS:
        print(f"Usage: python {sys.argv[0]} <{'|'.join(METHODS)}>" )
        print("  H = AXUIElementPostKeyboardEvent (HIGHEST CONFIDENCE)")
        print("  I = Dock bounce activate trick")
        print("  J = CGEventPostToPid")
        print("  A = open -a + CGEvent key")
        print("  D = CGWarp + click + key")
        return 1

    method = sys.argv[1].upper()

    pid, bounds, owner = find_fl()
    if pid is None:
        print("ERROR: FL Studio not found!")
        return 1
    print(f"FL Studio: pid={pid}, owner='{owner}', bounds={bounds}")
    print(f"Frontmost: {get_frontmost()}\n")

    METHODS[method](pid, bounds)

    print("\nDid FL Studio respond? Tell me!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
