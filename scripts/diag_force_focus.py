#!/usr/bin/env python3
"""Aggressive focus + key delivery test.

Tries multiple activation methods and verifies focus before sending keys.
"""
import subprocess
import time

import pyautogui
import Quartz  # type: ignore
from AppKit import NSWorkspace, NSRunningApplication  # type: ignore


def get_fl_pid() -> int | None:
    """Find FL Studio PID from running apps."""
    workspace = NSWorkspace.sharedWorkspace()
    for app in workspace.runningApplications():
        name = app.localizedName()
        bid = app.bundleIdentifier() or ""
        if "FL Studio" in (name or "") or "fl-studio" in bid.lower() or "flstudio" in bid.lower():
            print(f"  Found app: name={name}, bid={bid}, pid={app.processIdentifier()}")
            return app.processIdentifier()
    return None


def get_frontmost_app() -> str:
    """Return the name of the current frontmost app."""
    workspace = NSWorkspace.sharedWorkspace()
    front = workspace.frontmostApplication()
    return f"{front.localizedName()} (pid={front.processIdentifier()})"


def activate_by_pid(pid: int) -> bool:
    """Force-activate an app by PID using NSRunningApplication."""
    workspace = NSWorkspace.sharedWorkspace()
    for app in workspace.runningApplications():
        if app.processIdentifier() == pid:
            result = app.activateWithOptions_(3)  # NSApplicationActivateAllWindows | NSApplicationActivateIgnoringOtherApps
            return result
    return False


def find_fl_bounds():
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
    for w in window_list:
        owner = w.get("kCGWindowOwnerName", "")
        if "FL Studio" not in owner and "OsxFL" not in owner:
            continue
        layer = int(w.get("kCGWindowLayer", 0))
        if layer != 0:
            continue
        b = w.get("kCGWindowBounds", {})
        x = int(b.get("X", 0))
        y = int(b.get("Y", 0))
        ww = int(b.get("Width", 0))
        wh = int(b.get("Height", 0))
        pid = int(w.get("kCGWindowOwnerPID", 0))
        if ww > 0 and wh > 0:
            return (x, y, ww, wh), owner, pid
    return None, None, None


def main():
    print("═══ Force-Focus + Key Delivery Test ═══\n")

    # Step 1: Find FL Studio
    bounds, owner, win_pid = find_fl_bounds()
    if bounds is None:
        print("ERROR: FL Studio window not found!")
        return 1
    print(f"Quartz window: owner={owner}, pid={win_pid}, bounds={bounds}")

    fl_pid = get_fl_pid()
    if fl_pid is None:
        print("ERROR: FL Studio not in running apps!")
        return 1
    print(f"NSWorkspace PID: {fl_pid}")

    print(f"\nCurrent frontmost: {get_frontmost_app()}")

    # Step 2: Force-activate FL Studio
    print(f"\nActivating FL Studio (pid={fl_pid}) via NSRunningApplication...")
    ok = activate_by_pid(fl_pid)
    print(f"  activateWithOptions result: {ok}")
    time.sleep(0.5)
    print(f"  Frontmost after activate: {get_frontmost_app()}")

    # Step 3: Click inside FL Studio window
    x, y, ww, wh = bounds
    cx = x + ww // 2
    cy = y + 20  # Near title bar, safe area
    print(f"\nClicking FL Studio at ({cx}, {cy})...")
    pyautogui.click(cx, cy)
    time.sleep(0.3)
    print(f"  Frontmost after click: {get_frontmost_app()}")

    # Step 4: Verify mouse position
    mx, my = pyautogui.position()
    print(f"  Mouse position: ({mx}, {my})")
    print(f"  Inside FL bounds? x:{x}..{x+ww} y:{y}..{y+wh} => {x <= mx <= x+ww and y <= my <= y+wh}")

    # Step 5: Send Space via pyautogui
    print(f"\nSending Space via pyautogui...")
    pyautogui.press("space")
    print("  Sent! Watch FL Studio for 3 seconds...")
    time.sleep(3.0)

    # Step 6: Try CGEvent targeted to FL Studio's PID
    print("\nSending Space via CGEvent (targeted to FL PID)...")
    ev_down = Quartz.CGEventCreateKeyboardEvent(None, 49, True)
    ev_up = Quartz.CGEventCreateKeyboardEvent(None, 49, False)
    # Target the event to FL Studio's PID
    Quartz.CGEventSetIntegerValueField(ev_down, Quartz.kCGEventTargetUnixProcessID, fl_pid)
    Quartz.CGEventSetIntegerValueField(ev_up, Quartz.kCGEventTargetUnixProcessID, fl_pid)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_up)
    print("  Sent! Watch FL Studio for 3 seconds...")
    time.sleep(3.0)

    # Step 7: Try osascript with correct app name
    print(f"\nTrying osascript with app name '{owner}'...")
    r = subprocess.run(
        ["osascript", "-e", f'tell application "{owner}" to activate'],
        capture_output=True, text=True,
    )
    print(f"  activate result: rc={r.returncode}, err={r.stderr.strip()}")
    time.sleep(0.3)

    # Try System Events keystroke
    r = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to key code 49'],
        capture_output=True, text=True,
    )
    print(f"  System Events key code 49: rc={r.returncode}, err={r.stderr.strip()}")
    time.sleep(3.0)

    print("\n═══ Done. Which method (if any) started playback? ═══")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
