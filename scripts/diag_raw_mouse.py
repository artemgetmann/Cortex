#!/usr/bin/env python3
"""Test raw Quartz mouse movement and keyboard — bypass pyautogui entirely."""
import time

import Quartz  # type: ignore


def move_mouse_quartz(x: float, y: float) -> None:
    """Move mouse using raw CGEvent — bypass pyautogui."""
    point = Quartz.CGPointMake(x, y)
    event = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def click_quartz(x: float, y: float) -> None:
    """Click at (x, y) using raw CGEvent."""
    point = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def press_key_quartz(keycode: int) -> None:
    """Press a key using raw CGEvent."""
    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def get_mouse_pos() -> tuple[float, float]:
    """Get current mouse position via CGEvent."""
    event = Quartz.CGEventCreate(None)
    point = Quartz.CGEventGetLocation(event)
    return point.x, point.y


def main():
    print("═══ Raw Quartz Mouse + Key Test ═══\n")

    mx, my = get_mouse_pos()
    print(f"Current mouse (Quartz): ({mx:.0f}, {my:.0f})")

    # Test 1: Move mouse to center of main display
    print("\nTest 1: Moving mouse to (512, 384) via CGEvent...")
    move_mouse_quartz(512, 384)
    time.sleep(0.3)
    mx, my = get_mouse_pos()
    print(f"  Mouse now at: ({mx:.0f}, {my:.0f})")
    moved = abs(mx - 512) < 5 and abs(my - 384) < 5
    print(f"  Move successful: {moved}")

    if not moved:
        print("\n  CGEvent mouse move also failed!")
        print("  Trying CGWarpMouseCursorPosition...")
        Quartz.CGWarpMouseCursorPosition(Quartz.CGPointMake(512, 384))
        time.sleep(0.3)
        mx, my = get_mouse_pos()
        print(f"  Mouse now at: ({mx:.0f}, {my:.0f})")
        moved = abs(mx - 512) < 5 and abs(my - 384) < 5
        print(f"  Warp successful: {moved}")

    if not moved:
        print("\n  ALL mouse movement methods failed.")
        print("  This is likely a macOS permission issue or Sidecar restriction.")
        return 1

    # Test 2: Click at FL Studio window center
    print("\nTest 2: Clicking at (512, 50) — FL Studio title bar area...")
    click_quartz(512, 50)
    time.sleep(0.5)

    # Test 3: Send Space key
    print("\nTest 3: Sending Space key (keycode 49)...")
    press_key_quartz(49)
    print("  Sent! Watch FL Studio for 4 seconds...")
    time.sleep(4.0)

    # Test 4: Send Space again to stop
    print("\nTest 4: Sending Space again to stop...")
    press_key_quartz(49)
    time.sleep(2.0)

    print("\n═══ Results ═══")
    print("  Did the mouse move to center of main display?")
    print("  Did FL Studio start playback when Space was sent?")
    print("  Did FL Studio stop playback on second Space?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
