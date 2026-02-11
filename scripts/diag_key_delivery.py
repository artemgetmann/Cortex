#!/usr/bin/env python3
"""Diagnostic: test which key delivery method actually reaches FL Studio.

Tests 3 methods of sending Space to FL Studio, with human confirmation between each.
No agent loop, no API calls. Pure local test.

Run: .venv/bin/python scripts/diag_key_delivery.py
"""
from __future__ import annotations

import subprocess
import time

import pyautogui
import Quartz  # type: ignore


def activate_fl() -> None:
    subprocess.run(["osascript", "-e", 'tell application "FL Studio 2024" to activate'],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.3)


def method_a_pyautogui() -> None:
    """Current approach — pyautogui.press() via CGEvent to kCGSessionEventTap."""
    pyautogui.press("space")


def method_b_applescript() -> None:
    """AppleScript System Events — key code 49 = Space."""
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to key code 49'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"    osascript error: {result.stderr.strip()}")


def method_c_cgevent() -> None:
    """Raw CGEvent posted to kCGHIDEventTap (hardware-level simulation)."""
    # key code 49 = Space
    event_down = Quartz.CGEventCreateKeyboardEvent(None, 49, True)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_down)
    time.sleep(0.05)
    event_up = Quartz.CGEventCreateKeyboardEvent(None, 49, False)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_up)


def main() -> int:
    print("═══ FL Studio Key Delivery Diagnostic ═══\n")
    print("Make sure FL Studio is open and frontmost with a project loaded.")
    print("Watch the transport bar after each method — does playback start/stop?\n")
    input("Press Enter when ready...")

    results: dict[str, bool] = {}

    methods = [
        ("A", "pyautogui.press('space')", method_a_pyautogui),
        ("B", "AppleScript System Events key code 49", method_b_applescript),
        ("C", "CGEvent to kCGHIDEventTap (keycode 49)", method_c_cgevent),
    ]

    for label, desc, fn in methods:
        print(f"\n── Method {label}: {desc} ──")
        activate_fl()
        print(f"  Sending Space via Method {label} in 1s...")
        time.sleep(1.0)
        fn()
        time.sleep(0.3)
        answer = input(f"  Did FL Studio respond? (y/n): ").strip().lower()
        results[label] = answer == "y"
        # If playback started, send Space again to stop it before next test
        if answer == "y":
            print("  Sending Space again to stop playback...")
            activate_fl()
            time.sleep(0.3)
            fn()
            time.sleep(0.5)

    print("\n═══ Results ═══")
    for label, desc, _ in methods:
        status = "WORKS" if results[label] else "FAILED"
        print(f"  Method {label} ({desc}): {status}")

    winners = [l for l, ok in results.items() if ok]
    if winners:
        print(f"\n  Winner(s): {', '.join(winners)}")
        print("  Update computer_use.py to use the winning method.")
    else:
        print("\n  No method worked. Check:")
        print("  - Is FL Studio actually the frontmost app?")
        print("  - Does FL Studio respond to physical Space key?")
        print("  - Try granting Accessibility to Python binary directly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
