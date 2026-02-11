#!/usr/bin/env python3
from __future__ import annotations

import time

import pyautogui


def main() -> int:
    print("pyautogui.size() =", pyautogui.size())
    print("Switch to FL Studio NOW (on the 1024x768 virtual display). Screenshot in 3 seconds...")
    time.sleep(3)

    img = pyautogui.screenshot()
    img.save("gate_local.png")
    print("Saved gate_local.png (should show FL Studio)")

    w, h = pyautogui.size()
    pyautogui.click(w // 2, h // 2)
    pyautogui.press("f6")
    print("Clicked center + pressed F6. Did Channel Rack open?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
