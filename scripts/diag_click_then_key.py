#!/usr/bin/env python3
"""Test: click inside FL Studio window first, then send Space."""
import subprocess
import time

import pyautogui
import Quartz  # type: ignore


def find_fl_bounds():
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
    for w in window_list:
        owner = w.get("kCGWindowOwnerName", "")
        if owner not in ("FL Studio", "OsxFL", "FL Studio 2024"):
            continue
        layer = int(w.get("kCGWindowLayer", 0))
        if layer != 0:
            continue
        b = w.get("kCGWindowBounds", {})
        x = int(b.get("X", 0))
        y = int(b.get("Y", 0))
        ww = int(b.get("Width", 0))
        wh = int(b.get("Height", 0))
        if ww > 0 and wh > 0:
            return (x, y, ww, wh), owner
    return None, None


def main():
    print("═══ Click-to-Focus + Key Test ═══\n")

    bounds, owner = find_fl_bounds()
    if bounds is None:
        print("ERROR: FL Studio window not found via Quartz!")
        return 1

    x, y, ww, wh = bounds
    print(f"Found FL Studio: owner={owner}, bounds=({x},{y},{ww},{wh})")

    # Click center of FL Studio window to force keyboard focus to that display
    cx = x + ww // 2
    cy = y + wh // 2
    print(f"\nStep 1: Clicking center of FL window at ({cx}, {cy}) to grab focus...")
    pyautogui.click(cx, cy)
    time.sleep(0.5)

    # Method A: pyautogui after click
    print("Step 2: pyautogui.press('space') — sending NOW")
    pyautogui.press("space")
    print("  Sent! Watch FL Studio for 4 seconds...")
    time.sleep(4.0)

    # Stop playback for next test
    print("  Sending Space again to reset...")
    pyautogui.click(cx, cy)
    time.sleep(0.3)
    pyautogui.press("space")
    time.sleep(2.0)

    # Click again for Method C
    print("\nStep 3: Click FL window again...")
    pyautogui.click(cx, cy)
    time.sleep(0.5)

    # Method C: CGEvent after click
    print("Step 4: CGEvent kCGHIDEventTap — sending NOW")
    ev_down = Quartz.CGEventCreateKeyboardEvent(None, 49, True)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_down)
    time.sleep(0.05)
    ev_up = Quartz.CGEventCreateKeyboardEvent(None, 49, False)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_up)
    print("  Sent! Watch FL Studio for 4 seconds...")
    time.sleep(4.0)

    print("\n═══ Done ═══")
    print("Which method worked?")
    print("  A = pyautogui (after click)")
    print("  C = CGEvent (after click)")
    print("  Neither")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
