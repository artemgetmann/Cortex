#!/usr/bin/env python3
"""
Interactive click diagnostic v4.

This version starts with an easy browser-panel target, then tests multiple
left-click delivery paths. No Channel Rack coordinate guessing required.

Usage:
    cd /path/to/Cortex && uv run python scripts/click_test.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import Quartz
from AppKit import NSWorkspace
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_FL_BUNDLE_ID = "com.image-line.flstudio"
_OUTDIR = Path("sessions/click-test")


def find_fl_pid() -> int | None:
    ws = NSWorkspace.sharedWorkspace()
    for app in ws.runningApplications():
        if (app.bundleIdentifier() or "") == _FL_BUNDLE_ID:
            return app.processIdentifier()
    return None


def activate_fl_studio() -> None:
    ws = NSWorkspace.sharedWorkspace()
    for app in ws.runningApplications():
        if (app.bundleIdentifier() or "") == _FL_BUNDLE_ID:
            app.activateWithOptions_(3)
            return


def find_fl_window() -> tuple[int, tuple[int, int, int, int]] | None:
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
    best = None
    for w in window_list:
        try:
            owner = w.get("kCGWindowOwnerName")
            layer = int(w.get("kCGWindowLayer", 0))
            if owner not in ("FL Studio", "OsxFL"):
                continue
            if layer != 0:
                continue
            bounds = w.get("kCGWindowBounds") or {}
            x = int(bounds.get("X", 0))
            y = int(bounds.get("Y", 0))
            ww = int(bounds.get("Width", 0))
            wh = int(bounds.get("Height", 0))
            wid = int(w.get("kCGWindowNumber"))
            if ww <= 0 or wh <= 0:
                continue
            area = ww * wh
            if best is None or area > best[2]:
                best = (wid, (x, y, ww, wh), area)
        except Exception:
            continue
    if best is None:
        return None
    return best[0], best[1]


def capture_fl_window_png(wid: int, bounds: tuple[int, int, int, int], out_path: Path) -> bool:
    x, y, ww, wh = bounds
    rect = Quartz.CGRectMake(x, y, ww, wh)
    cgimg = Quartz.CGWindowListCreateImage(
        rect,
        Quartz.kCGWindowListOptionIncludingWindow,
        wid,
        Quartz.kCGWindowImageBoundsIgnoreFraming,
    )
    if cgimg is None:
        return False

    width = Quartz.CGImageGetWidth(cgimg)
    height = Quartz.CGImageGetHeight(cgimg)
    bpr = Quartz.CGImageGetBytesPerRow(cgimg)
    provider = Quartz.CGImageGetDataProvider(cgimg)
    data = Quartz.CGDataProviderCopyData(provider)
    buf = bytes(data)
    img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", bpr, 1).copy()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return True


def post_key_to_pid(pid: int, keycode: int) -> None:
    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventPostToPid(pid, down)
    time.sleep(0.02)
    Quartz.CGEventPostToPid(pid, up)


def click_hid_tap(sx: int, sy: int) -> None:
    pt = Quartz.CGPointMake(sx, sy)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def click_hid_source(sx: int, sy: int) -> None:
    source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    pt = Quartz.CGPointMake(sx, sy)
    down = Quartz.CGEventCreateMouseEvent(source, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(source, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def click_to_pid(pid: int, sx: int, sy: int) -> None:
    pt = Quartz.CGPointMake(sx, sy)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPostToPid(pid, down)
    time.sleep(0.05)
    Quartz.CGEventPostToPid(pid, up)


def right_click_hid_tap(sx: int, sy: int) -> None:
    pt = Quartz.CGPointMake(sx, sy)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseDown, pt, Quartz.kCGMouseButtonRight)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseUp, pt, Quartz.kCGMouseButtonRight)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def main() -> int:
    pid = find_fl_pid()
    if pid is None:
        print("ERROR: FL Studio not running")
        return 1
    print(f"FL Studio PID: {pid}")

    found = find_fl_window()
    if found is None:
        print("ERROR: FL Studio window not found")
        return 1
    wid, (ox, oy, ww, wh) = found
    print(f"Window: x={ox} y={oy} w={ww} h={wh}")

    def api_to_screen(ax: int, ay: int) -> tuple[int, int]:
        sx = ww / 1024.0
        sy = wh / 768.0
        mx = max(0, min(ww - 1, int(round(ax * sx))))
        my = max(0, min(wh - 1, int(round(ay * sy))))
        return ox + mx, oy + my

    def warp(ax: int, ay: int) -> tuple[int, int]:
        sx, sy = api_to_screen(ax, ay)
        Quartz.CGWarpMouseCursorPosition(Quartz.CGPointMake(sx, sy))
        return sx, sy

    # =====================================================================
    # PHASE 0: Key event test
    # =====================================================================
    print("\n=== PHASE 0: Key event test ===")
    activate_fl_studio()
    time.sleep(1.0)
    print("Sending F6 (Channel Rack)...")
    post_key_to_pid(pid, 97)  # F6
    time.sleep(0.5)
    print("Sending Space (play)...")
    post_key_to_pid(pid, 49)  # Space
    result = input("Did FL Studio start playing? (y/n): ").strip().lower()
    post_key_to_pid(pid, 49)  # Stop playback

    if result != "y":
        print("\nKey events aren't reaching FL Studio from this process.")
        return 1

    # =====================================================================
    # PHASE 1: Browser panel target selection
    # =====================================================================
    print("\n=== PHASE 1: Pick an easy browser-panel click target ===")
    print("I will move the cursor over likely clickable browser rows.")
    print("Reply y when the cursor is on a browser item you can click.")

    activate_fl_studio()
    time.sleep(0.5)

    # Left browser tree rows around your screenshot area.
    candidates = [(95, 165), (95, 195), (95, 225), (95, 255), (95, 285), (95, 315)]
    target_api: tuple[int, int] | None = None
    for ax, ay in candidates:
        sx, sy = warp(ax, ay)
        time.sleep(0.25)
        ans = input(f"  API({ax},{ay}) -> Screen({sx},{sy}) on clickable browser row? (y/n): ").strip().lower()
        if ans == "y":
            target_api = (ax, ay)
            break

    if target_api is None:
        raw = input("Enter manual API target as 'x y' (example: 95 195): ").strip().split()
        if len(raw) != 2:
            print("Invalid target input.")
            return 1
        try:
            target_api = (int(raw[0]), int(raw[1]))
        except ValueError:
            print("Invalid target input.")
            return 1

    tx, ty = target_api
    sx, sy = api_to_screen(tx, ty)
    print(f"Using target API({tx},{ty}) -> Screen({sx},{sy})")

    capture_fl_window_png(wid, (ox, oy, ww, wh), _OUTDIR / "browser_before.png")

    # =====================================================================
    # PHASE 2: Left-click delivery methods on browser target
    # =====================================================================
    print("\n=== PHASE 2: Left-click methods ===")
    print("Expected reaction: browser row selection/folder open/sample preview.")
    warp(tx, ty)
    input("Cursor positioned on target. Press Enter to run Method A...")

    click_hid_tap(sx, sy)
    capture_fl_window_png(wid, (ox, oy, ww, wh), _OUTDIR / "browser_after_a_hid_tap.png")
    a = input("Method A (CGEventPost HID tap) reacted? (y/n): ").strip().lower() == "y"
    if a:
        print("\n✅ Left-click works (Method A).")
        return 0

    warp(tx, ty)
    click_hid_source(sx, sy)
    capture_fl_window_png(wid, (ox, oy, ww, wh), _OUTDIR / "browser_after_b_hid_source.png")
    b = input("Method B (HID event source) reacted? (y/n): ").strip().lower() == "y"
    if b:
        print("\n✅ Left-click works (Method B).")
        return 0

    pid = find_fl_pid() or pid
    warp(tx, ty)
    click_to_pid(pid, sx, sy)
    capture_fl_window_png(wid, (ox, oy, ww, wh), _OUTDIR / "browser_after_c_pid.png")
    c = input("Method C (CGEventPostToPid mouse) reacted? (y/n): ").strip().lower() == "y"
    if c:
        print("\n✅ Left-click works (Method C).")
        return 0

    # Right click on the same target is a very visible fallback.
    warp(tx, ty)
    right_click_hid_tap(sx, sy)
    capture_fl_window_png(wid, (ox, oy, ww, wh), _OUTDIR / "browser_after_d_right_click.png")
    d = input("Method D right-click context menu appeared? (y/n): ").strip().lower() == "y"

    if d:
        print("\nRight-click works at this target, but left-click did not.")
        print("That suggests a left-button delivery path issue, not coordinate mapping.")
    else:
        print("\nNeither left nor right click reacted at this target.")
        print("Re-check permissions and confirm target is truly interactive.")

    print(f"Debug screenshots saved in: {_OUTDIR}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
