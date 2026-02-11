#!/usr/bin/env python3
"""Focus + key delivery v2 — correct app name + multiple strategies.

Tests:
  A) open -a "FL Studio" + CGEvent key
  B) NSRunningApplication.activateWithOptions + CGEvent key
  C) AXUIElement raise + CGEvent key
  D) CGWarp + CGEvent click + CGEvent key (current best)
  E) osascript activate + System Events key code
"""
import subprocess
import time

import Quartz  # type: ignore
from AppKit import NSWorkspace, NSRunningApplication  # type: ignore
from ApplicationServices import (  # type: ignore
    AXUIElementCreateApplication,
    AXUIElementPerformAction,
    AXUIElementCopyAttributeValue,
    AXUIElementPostKeyboardEvent,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_frontmost() -> str:
    ws = NSWorkspace.sharedWorkspace()
    f = ws.frontmostApplication()
    return f"{f.localizedName()} (pid={f.processIdentifier()})"


def find_fl_pid() -> int | None:
    ws = NSWorkspace.sharedWorkspace()
    for app in ws.runningApplications():
        name = app.localizedName() or ""
        bid = app.bundleIdentifier() or ""
        if "FL Studio" in name or "flstudio" in bid.lower():
            return app.processIdentifier()
    return None


def find_fl_bounds():
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
            return (x, y, ww, wh), owner, int(w.get("kCGWindowOwnerPID", 0))
    return None, None, None


def warp(x, y):
    Quartz.CGWarpMouseCursorPosition(Quartz.CGPointMake(x, y))


def cg_click(x, y):
    pt = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def cg_click_session(x, y):
    """Click using kCGSessionEventTap instead of kCGHIDEventTap."""
    pt = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGSessionEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGSessionEventTap, up)


def cg_key(keycode, tap=Quartz.kCGHIDEventTap):
    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventPost(tap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(tap, up)


def cg_key_to_pid(keycode, pid):
    """Post key event targeted to a specific PID."""
    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    # Try kCGEventTargetUnixProcessID
    try:
        Quartz.CGEventSetIntegerValueField(down, Quartz.kCGEventTargetUnixProcessID, pid)
        Quartz.CGEventSetIntegerValueField(up, Quartz.kCGEventTargetUnixProcessID, pid)
    except Exception as e:
        print(f"    (CGEventSetIntegerValueField failed: {e})")
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def countdown(msg, n=3):
    print(msg)
    for i in range(n, 0, -1):
        print(f"  {i}...")
        time.sleep(1)


SPACE = 49


# ── Tests ────────────────────────────────────────────────────────────────────

def test_a_open_activate(fl_pid, bounds):
    """Method A: 'open -a' with correct name + CGEvent key."""
    print("\n╔══ Method A: open -a 'FL Studio' + CGEvent Space ══╗")
    r = subprocess.run(["open", "-a", "FL Studio"], capture_output=True, text=True)
    print(f"  open -a result: rc={r.returncode} err={r.stderr.strip()}")
    time.sleep(1.0)
    print(f"  Frontmost: {get_frontmost()}")
    countdown("  Sending Space in", 2)
    cg_key(SPACE)
    print("  Space sent! Watch FL Studio transport.")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


def test_b_nsapp_activate(fl_pid, bounds):
    """Method B: NSRunningApplication.activateWithOptions + CGEvent key."""
    print("\n╔══ Method B: NSRunningApplication activate + CGEvent Space ══╗")
    ws = NSWorkspace.sharedWorkspace()
    for app in ws.runningApplications():
        if app.processIdentifier() == fl_pid:
            # activateAllWindows + ignoreOtherApps
            ok = app.activateWithOptions_(3)
            print(f"  activateWithOptions: {ok}")
            break
    time.sleep(1.0)
    print(f"  Frontmost: {get_frontmost()}")
    countdown("  Sending Space in", 2)
    cg_key(SPACE)
    print("  Space sent!")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


def test_c_axui_raise(fl_pid, bounds):
    """Method C: AXUIElement raise window + CGEvent key."""
    print("\n╔══ Method C: AXUIElement raise + CGEvent Space ══╗")
    ax_app = AXUIElementCreateApplication(fl_pid)
    err, windows = AXUIElementCopyAttributeValue(ax_app, "AXWindows", None)
    if err == 0 and windows:
        print(f"  Found {len(windows)} AX windows")
        for w in windows:
            err2 = AXUIElementPerformAction(w, "AXRaise")
            print(f"  AXRaise result: {err2} (0=success)")
            break
    else:
        print(f"  AXUIElementCopyAttributeValue error: {err}")
    time.sleep(1.0)
    print(f"  Frontmost: {get_frontmost()}")
    countdown("  Sending Space in", 2)
    cg_key(SPACE)
    print("  Space sent!")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


def test_d_warp_click_key(fl_pid, bounds):
    """Method D: CGWarp + click (both HID and Session taps) + key."""
    x, y, ww, wh = bounds
    cx, cy = x + ww // 2, y + 50  # top area, safe click target
    print(f"\n╔══ Method D: CGWarp + click at ({cx},{cy}) + Space ══╗")

    # Sub-test D1: HID tap click
    print("  D1: CGWarp + kCGHIDEventTap click...")
    warp(cx, cy)
    time.sleep(0.1)
    cg_click(cx, cy)
    time.sleep(0.5)
    front = get_frontmost()
    print(f"  Frontmost after HID click: {front}")

    # Sub-test D2: Session tap click
    print("  D2: CGWarp + kCGSessionEventTap click...")
    warp(cx, cy)
    time.sleep(0.1)
    cg_click_session(cx, cy)
    time.sleep(0.5)
    front = get_frontmost()
    print(f"  Frontmost after Session click: {front}")

    # Now try key
    countdown("  Sending Space in", 2)
    cg_key(SPACE)
    print("  Space sent!")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


def test_e_osascript(fl_pid, bounds):
    """Method E: osascript activate + System Events key code."""
    print("\n╔══ Method E: osascript activate 'FL Studio' + System Events key ══╗")
    r = subprocess.run(
        ["osascript", "-e", 'tell application "FL Studio" to activate'],
        capture_output=True, text=True,
    )
    print(f"  activate: rc={r.returncode} err={r.stderr.strip()}")
    time.sleep(1.0)
    print(f"  Frontmost: {get_frontmost()}")

    r2 = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to key code 49'],
        capture_output=True, text=True,
    )
    print(f"  key code 49: rc={r2.returncode} err={r2.stderr.strip()}")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


def test_f_key_to_pid(fl_pid, bounds):
    """Method F: CGEvent key targeted to FL Studio PID."""
    print(f"\n╔══ Method F: CGEvent Space targeted to PID {fl_pid} ══╗")

    # First activate via open -a
    subprocess.run(["open", "-a", "FL Studio"], capture_output=True)
    time.sleep(0.5)

    countdown("  Sending PID-targeted Space in", 2)
    cg_key_to_pid(SPACE, fl_pid)
    print("  PID-targeted Space sent!")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


def test_g_associate_warp_click(fl_pid, bounds):
    """Method G: CGAssociateMouseAndMouseCursorPosition + warp + click + key."""
    x, y, ww, wh = bounds
    cx, cy = x + ww // 2, y + 50
    print(f"\n╔══ Method G: Associate + Warp + Click({cx},{cy}) + Space ══╗")

    Quartz.CGAssociateMouseAndMouseCursorPosition(False)
    time.sleep(0.1)
    warp(cx, cy)
    time.sleep(0.1)
    Quartz.CGAssociateMouseAndMouseCursorPosition(True)
    time.sleep(0.1)

    cg_click(cx, cy)
    time.sleep(0.5)
    print(f"  Frontmost after associate+warp+click: {get_frontmost()}")

    countdown("  Sending Space in", 2)
    cg_key(SPACE)
    print("  Space sent!")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


def test_h_axui_post_key(fl_pid, _bounds):
    """Method H: AXUIElementPostKeyboardEvent — keys direct to PID, NO FOCUS NEEDED."""
    print(f"\n╔══ Method H: AXUIElementPostKeyboardEvent to PID {fl_pid} ══╗")
    print("  (This sends keys DIRECTLY to FL Studio — no focus change needed!)")

    ax_app = AXUIElementCreateApplication(fl_pid)
    countdown("  Sending Space via AXUIElement in", 2)
    AXUIElementPostKeyboardEvent(ax_app, 0, SPACE, True)   # key down
    time.sleep(0.02)
    AXUIElementPostKeyboardEvent(ax_app, 0, SPACE, False)  # key up
    print("  AXUIElement Space sent!")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


def test_i_dock_bounce(fl_pid, _bounds):
    """Method I: Dock bounce trick — activate Dock, then FL Studio, then CGEvent key."""
    print(f"\n╔══ Method I: Dock bounce activate + CGEvent Space ══╗")
    print("  (Activates Dock first to force a real focus switch)")

    ws = NSWorkspace.sharedWorkspace()
    # Find Dock
    dock = None
    fl_app = None
    for app in ws.runningApplications():
        bid = app.bundleIdentifier() or ""
        if bid == "com.apple.dock":
            dock = app
        if app.processIdentifier() == fl_pid:
            fl_app = app

    if dock:
        print("  Activating Dock...")
        dock.activateWithOptions_(3)
        time.sleep(0.3)
        print(f"  Frontmost after Dock activate: {get_frontmost()}")

    if fl_app:
        print("  Now activating FL Studio...")
        ok = fl_app.activateWithOptions_(3)
        print(f"  activateWithOptions: {ok}")
        time.sleep(0.5)
        print(f"  Frontmost after FL activate: {get_frontmost()}")

    countdown("  Sending Space in", 2)
    cg_key(SPACE)
    print("  Space sent!")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


def test_j_cgevent_post_to_pid(fl_pid, _bounds):
    """Method J: CGEventPostToPid — post keyboard event directly to FL Studio's PID."""
    print(f"\n╔══ Method J: CGEventPostToPid({fl_pid}) Space ══╗")

    countdown("  Sending Space via CGEventPostToPid in", 2)
    down = Quartz.CGEventCreateKeyboardEvent(None, SPACE, True)
    up = Quartz.CGEventCreateKeyboardEvent(None, SPACE, False)
    try:
        Quartz.CGEventPostToPid(fl_pid, down)
        time.sleep(0.05)
        Quartz.CGEventPostToPid(fl_pid, up)
        print("  CGEventPostToPid Space sent!")
    except Exception as e:
        print(f"  CGEventPostToPid error: {e}")
    time.sleep(3)
    return input("  Did playback START? (y/n): ").strip().lower() == "y"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("═══ Focus + Key Delivery v2 ═══\n")

    fl_pid = find_fl_pid()
    bounds_info, owner, win_pid = find_fl_bounds()
    if fl_pid is None or bounds_info is None:
        print("ERROR: FL Studio not found!")
        return 1

    print(f"FL Studio: pid={fl_pid}, owner='{owner}', bounds={bounds_info}")
    print(f"Current frontmost: {get_frontmost()}")
    print("\nIMPORTANT: Between each test, press Space MANUALLY in FL Studio")
    print("to STOP playback if it started, so next test starts clean.\n")
    input("Ready? Press Enter to begin... ")

    results = {}

    tests = [
        # HIGH CONFIDENCE (from research) — test these first
        ("H: AXUIElement PostKeyboardEvent (no focus!)", test_h_axui_post_key),
        ("I: Dock bounce + CGEvent key", test_i_dock_bounce),
        ("J: CGEventPostToPid", test_j_cgevent_post_to_pid),
        # Other methods
        ("A: open -a + CGEvent key", test_a_open_activate),
        ("B: NSRunningApp + CGEvent key", test_b_nsapp_activate),
        ("C: AXUIElement raise + CGEvent key", test_c_axui_raise),
        ("D: CGWarp + click + key", test_d_warp_click_key),
        ("E: osascript + System Events", test_e_osascript),
        ("F: CGEvent key to PID", test_f_key_to_pid),
        ("G: Associate + Warp + Click + key", test_g_associate_warp_click),
    ]

    for name, fn in tests:
        try:
            ok = fn(fl_pid, bounds_info)
            results[name] = "WORKS" if ok else "FAIL"
        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = f"ERROR: {e}"

        if results[name] == "WORKS":
            print(f"\n  >>> {name}: WORKS! <<<")
            print("  Stop playback manually, then press Enter.")
            input()
        print()

    print("\n═══ RESULTS ═══")
    for name, result in results.items():
        icon = "✓" if result == "WORKS" else "✗"
        print(f"  {icon} {name}: {result}")

    winners = [n for n, r in results.items() if r == "WORKS"]
    if winners:
        print(f"\n  WINNER(S): {', '.join(winners)}")
    else:
        print("\n  NO METHOD WORKED. Need alternative approach.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
