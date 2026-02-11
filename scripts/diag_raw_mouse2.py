#!/usr/bin/env python3
"""Raw Quartz test v2 — with countdown and CGWarp-based click."""
import time

import Quartz  # type: ignore
from AppKit import NSWorkspace  # type: ignore


def warp_to(x: float, y: float) -> None:
    Quartz.CGWarpMouseCursorPosition(Quartz.CGPointMake(x, y))


def click_at(x: float, y: float) -> None:
    """Warp cursor then click at that position."""
    warp_to(x, y)
    time.sleep(0.05)
    point = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def press_key(keycode: int) -> None:
    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def get_mouse_pos() -> tuple[float, float]:
    event = Quartz.CGEventCreate(None)
    point = Quartz.CGEventGetLocation(event)
    return point.x, point.y


def get_frontmost() -> str:
    ws = NSWorkspace.sharedWorkspace()
    f = ws.frontmostApplication()
    return f.localizedName()


def countdown(msg: str, seconds: int = 3) -> None:
    print(msg)
    for i in range(seconds, 0, -1):
        print(f"  {i}...")
        time.sleep(1)


def main():
    print("═══ Raw Quartz Test v2 ═══")
    print("WATCH YOUR MAC SCREEN (where FL Studio is)")
    print()

    countdown("Starting in", 3)

    # Step 1: Warp mouse to FL Studio center
    print("\n>> Moving mouse to FL Studio window center (512, 384)...")
    warp_to(512, 384)
    time.sleep(0.3)
    mx, my = get_mouse_pos()
    print(f"   Mouse at: ({mx:.0f}, {my:.0f})")

    # Step 2: Click FL Studio to focus it
    print("\n>> Clicking FL Studio at (512, 200) to focus...")
    click_at(512, 200)
    time.sleep(0.5)
    front = get_frontmost()
    print(f"   Frontmost app: {front}")

    # Step 3: Send Space to start playback
    countdown("\n>> Sending SPACE to start playback in", 2)
    press_key(49)  # Space = keycode 49
    print("   SPACE SENT! Look at FL Studio transport bar!")
    time.sleep(5.0)

    # Step 4: Send Space to stop playback
    countdown("\n>> Sending SPACE to stop playback in", 2)
    press_key(49)
    print("   SPACE SENT again! Transport should stop.")
    time.sleep(2.0)

    print(f"\n   Frontmost app: {get_frontmost()}")
    print("\n═══ DONE ═══")
    print("Did playback START then STOP?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
