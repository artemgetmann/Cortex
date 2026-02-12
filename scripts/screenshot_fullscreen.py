#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import Quartz  # type: ignore
from PIL import Image


def _cgimage_to_pil(cgimg) -> Image.Image:
    width = Quartz.CGImageGetWidth(cgimg)
    height = Quartz.CGImageGetHeight(cgimg)
    bpr = Quartz.CGImageGetBytesPerRow(cgimg)
    provider = Quartz.CGImageGetDataProvider(cgimg)
    data = Quartz.CGDataProviderCopyData(provider)
    buf = bytes(data)
    return Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", bpr, 1).copy()


def _find_fl_window_bounds() -> tuple[int, int, int, int] | None:
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
    best: tuple[int, int, int, int] | None = None
    best_area = -1
    for w in window_list:
        try:
            owner = w.get("kCGWindowOwnerName")
            layer = int(w.get("kCGWindowLayer", 0))
            if owner not in ("FL Studio", "OsxFL") or layer != 0:
                continue
            bounds = w.get("kCGWindowBounds") or {}
            x = int(bounds.get("X", 0))
            y = int(bounds.get("Y", 0))
            ww = int(bounds.get("Width", 0))
            wh = int(bounds.get("Height", 0))
            if ww <= 0 or wh <= 0:
                continue
            area = ww * wh
            if area > best_area:
                best = (x, y, ww, wh)
                best_area = area
        except Exception:
            continue
    return best


def _list_online_displays() -> list[int]:
    try:
        err, displays, count = Quartz.CGGetOnlineDisplayList(32, None, None)
        if err != Quartz.kCGErrorSuccess or count <= 0:
            return []
        return [int(d) for d in displays[:count]]
    except Exception:
        return []


def _display_bounds(display_id: int) -> tuple[int, int, int, int] | None:
    try:
        rect = Quartz.CGDisplayBounds(display_id)
        x = int(rect.origin.x)
        y = int(rect.origin.y)
        w = int(rect.size.width)
        h = int(rect.size.height)
        if w <= 0 or h <= 0:
            return None
        return x, y, w, h
    except Exception:
        return None


def _display_for_window(bounds: tuple[int, int, int, int]) -> int:
    wx, wy, ww, wh = bounds
    displays = _list_online_displays()
    if not displays:
        return int(Quartz.CGMainDisplayID())

    best_display: int | None = None
    best_area = -1
    for did in displays:
        db = _display_bounds(did)
        if db is None:
            continue
        dx, dy, dw, dh = db
        ix0 = max(wx, dx)
        iy0 = max(wy, dy)
        ix1 = min(wx + ww, dx + dw)
        iy1 = min(wy + wh, dy + dh)
        iw = ix1 - ix0
        ih = iy1 - iy0
        if iw <= 0 or ih <= 0:
            continue
        area = iw * ih
        if area > best_area:
            best_area = area
            best_display = did

    if best_display is not None:
        return best_display
    return int(Quartz.CGMainDisplayID())


def _desktop_union_bounds(displays: list[int]) -> tuple[int, int, int, int] | None:
    rects: list[tuple[int, int, int, int]] = []
    for did in displays:
        db = _display_bounds(did)
        if db is not None:
            rects.append(db)
    if not rects:
        return None
    min_x = min(r[0] for r in rects)
    min_y = min(r[1] for r in rects)
    max_x = max(r[0] + r[2] for r in rects)
    max_y = max(r[1] + r[3] for r in rects)
    return min_x, min_y, max_x - min_x, max_y - min_y


def _capture_composited_all() -> Image.Image | None:
    cgimg = Quartz.CGWindowListCreateImage(
        Quartz.CGRectInfinite,
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault,
    )
    if cgimg is None:
        return None
    return _cgimage_to_pil(cgimg)


def capture_fullscreen() -> Image.Image:
    # Capture composited desktop first (robust for FL popup/menu visibility),
    # then crop to one target display.
    full = _capture_composited_all()
    if full is None:
        cgimg = Quartz.CGDisplayCreateImage(Quartz.CGMainDisplayID())
        if cgimg is not None:
            return _cgimage_to_pil(cgimg)
        raise RuntimeError(
            "Display capture failed. Grant Screen Recording permission to your terminal/IDE, "
            "then restart it."
        )

    displays = _list_online_displays()
    union_bounds = _desktop_union_bounds(displays)
    if union_bounds is None:
        return full

    bounds = _find_fl_window_bounds()
    display_id = _display_for_window(bounds) if bounds is not None else int(Quartz.CGMainDisplayID())
    target = _display_bounds(display_id)
    if target is None:
        return full

    ux, uy, uw, uh = union_bounds
    dx, dy, dw, dh = target
    # CoreGraphics display/window bounds are in points; captured bitmap is pixels.
    # Convert point-space desktop coords to pixel-space crop coords.
    if uw <= 0 or uh <= 0:
        return full
    sx = full.width / float(uw)
    sy = full.height / float(uh)
    x0 = int(round((dx - ux) * sx))
    y0 = int(round((dy - uy) * sy))
    x1 = int(round((dx + dw - ux) * sx))
    y1 = int(round((dy + dh - uy) * sy))
    x0 = max(0, min(full.width - 1, x0))
    y0 = max(0, min(full.height - 1, y0))
    x1 = max(0, min(full.width, x1))
    y1 = max(0, min(full.height, y1))
    if x1 > x0 and y1 > y0:
        return full.crop((x0, y0, x1, y1))
    return full


def main() -> int:
    out_dir = Path("sessions/fullscreen-test")
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"fullscreen-{ts}.png"

    img = capture_fullscreen()
    img.save(out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
