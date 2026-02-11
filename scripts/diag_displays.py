#!/usr/bin/env python3
"""Diagnose display layout and coordinate mapping."""
import pyautogui
import Quartz  # type: ignore


def main():
    print("═══ Display Layout Diagnostic ═══\n")

    # pyautogui view of the world
    pw, ph = pyautogui.size()
    print(f"pyautogui.size() = {pw}x{ph}")
    mx, my = pyautogui.position()
    print(f"pyautogui.position() = ({mx}, {my})")

    # Quartz main display
    main_id = Quartz.CGMainDisplayID()
    main_bounds = Quartz.CGDisplayBounds(main_id)
    print(f"\nCGMainDisplayID = {main_id}")
    print(f"  bounds: origin=({main_bounds.origin.x}, {main_bounds.origin.y}) "
          f"size=({main_bounds.size.width}x{main_bounds.size.height})")
    print(f"  pixels: {Quartz.CGDisplayPixelsWide(main_id)}x{Quartz.CGDisplayPixelsHigh(main_id)}")

    # All active displays
    err, display_ids, count = Quartz.CGGetActiveDisplayList(10, None, None)
    print(f"\nActive displays: {count}")
    for i, did in enumerate(display_ids[:count]):
        b = Quartz.CGDisplayBounds(did)
        pw_d = Quartz.CGDisplayPixelsWide(did)
        ph_d = Quartz.CGDisplayPixelsHigh(did)
        is_main = "MAIN" if did == main_id else ""
        is_builtin = "BUILTIN" if Quartz.CGDisplayIsBuiltin(did) else "EXTERNAL"
        print(f"  [{i}] id={did} {is_main} {is_builtin}")
        print(f"      origin=({b.origin.x}, {b.origin.y}) size={b.size.width}x{b.size.height}")
        print(f"      pixels={pw_d}x{ph_d}")

    # FL Studio window
    print("\nFL Studio window (Quartz):")
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
        print(f"  owner={owner} layer={layer}")
        print(f"  bounds: X={b.get('X')} Y={b.get('Y')} W={b.get('Width')} H={b.get('Height')}")
        print(f"  pid={w.get('kCGWindowOwnerPID')}")

    # Test: where does pyautogui think (0,0) is vs (512,384)?
    print("\nCoordinate test:")
    print("  Moving mouse to pyautogui (0, 0)...")
    pyautogui.moveTo(0, 0)
    qx, qy = pyautogui.position()
    print(f"  pyautogui.position() after moveTo(0,0) = ({qx}, {qy})")

    print("  Moving mouse to pyautogui (512, 384)...")
    pyautogui.moveTo(512, 384)
    qx, qy = pyautogui.position()
    print(f"  pyautogui.position() after moveTo(512,384) = ({qx}, {qy})")

    # Check if pyautogui uses Retina scaling
    print(f"\npyautogui FAILSAFE = {pyautogui.FAILSAFE}")
    print(f"pyautogui PAUSE = {pyautogui.PAUSE}")

    print("\n═══ Key insight: if pyautogui.size() != Quartz main display size,")
    print("    coordinate scaling is needed between the two systems. ═══")


if __name__ == "__main__":
    main()
