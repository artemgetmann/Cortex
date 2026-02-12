from __future__ import annotations

import base64
import io
import sys
import time
from dataclasses import dataclass
from typing import Any, Literal

import Quartz  # type: ignore
from AppKit import NSWorkspace  # type: ignore
from ApplicationServices import AXIsProcessTrusted  # type: ignore
from PIL import Image, ImageChops


ComputerAction = Literal[
    "screenshot",
    "mouse_move",
    "left_click",
    "right_click",
    "middle_click",
    "double_click",
    "triple_click",
    "left_click_drag",
    "scroll",
    "key",
    "hold_key",
    "type",
    "wait",
    "cursor_position",
    "zoom",
]


# ── macOS virtual keycodes ────────────────────────────────────────────────────

_KEYCODES: dict[str, int] = {
    # Letters
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "o": 31, "u": 32, "i": 34, "p": 35, "l": 37,
    "j": 38, "k": 40, "n": 45, "m": 46,
    # Numbers
    "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22,
    "7": 26, "8": 28, "9": 25, "0": 29,
    # Symbols
    "-": 27, "=": 24, "[": 33, "]": 30, "\\": 42, ";": 41, "'": 39,
    ",": 43, ".": 47, "/": 44, "`": 50,
    # Special keys
    "space": 49, "enter": 36, "return": 36, "tab": 48,
    "escape": 53, "esc": 53, "delete": 51, "backspace": 51,
    "forwarddelete": 117,
    # Arrow keys
    "up": 126, "down": 125, "left": 123, "right": 124,
    # Function keys
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    # Modifiers (when used as the primary key, not as modifier)
    "shift": 56, "ctrl": 59, "control": 59, "alt": 58, "option": 58,
    "command": 55, "cmd": 55,
}

_MODIFIER_FLAGS: dict[str, int] = {
    "shift": Quartz.kCGEventFlagMaskShift,
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "control": Quartz.kCGEventFlagMaskControl,
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "command": Quartz.kCGEventFlagMaskCommand,
    "cmd": Quartz.kCGEventFlagMaskCommand,
}

_FORBIDDEN_COMBOS = frozenset({
    "command+q", "command+tab", "command+option+esc",
    "command+w", "command+m",
})


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    output: str | None = None
    error: str | None = None
    base64_image_png: str | None = None

    def is_error(self) -> bool:
        return bool(self.error)


# ── FL Studio process helpers ─────────────────────────────────────────────────

_FL_BUNDLE_ID = "com.image-line.flstudio"


def _find_fl_pid() -> int | None:
    ws = NSWorkspace.sharedWorkspace()
    for app in ws.runningApplications():
        if (app.bundleIdentifier() or "") == _FL_BUNDLE_ID:
            return app.processIdentifier()
    return None


def _activate_fl_studio() -> None:
    ws = NSWorkspace.sharedWorkspace()
    for app in ws.runningApplications():
        if (app.bundleIdentifier() or "") == _FL_BUNDLE_ID:
            # NSApplicationActivateAllWindows | NSApplicationActivateIgnoringOtherApps
            app.activateWithOptions_(3)
            time.sleep(0.1)
            return


# ── CGEvent input helpers ─────────────────────────────────────────────────────

_INPUT_ACTIONS = frozenset({
    "mouse_move",
    "left_click",
    "right_click",
    "middle_click",
    "double_click",
    "triple_click",
    "left_click_drag",
    "scroll",
    "key",
    "hold_key",
    "type",
})


def _has_post_event_access() -> bool:
    try:
        return bool(Quartz.CGPreflightPostEventAccess())
    except Exception:
        return False


def _has_ax_access() -> bool:
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _build_input_access_error() -> str:
    return (
        "macOS denied synthetic input events. "
        f"CGPreflightPostEventAccess={_has_post_event_access()} "
        f"AXIsProcessTrusted={_has_ax_access()} "
        f"python={sys.executable}. "
        "Grant Accessibility to your terminal/IDE and this Python binary, then restart both."
    )


def _cg_post_key_to_pid(pid: int, keycode: int, down: bool, flags: int = 0) -> None:
    event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
    if flags:
        Quartz.CGEventSetFlags(event, flags | Quartz.CGEventGetFlags(event))
    Quartz.CGEventPostToPid(pid, event)


def _cg_press_key(pid: int, keycode: int, flags: int = 0) -> None:
    _cg_post_key_to_pid(pid, keycode, True, flags)
    time.sleep(0.05)
    _cg_post_key_to_pid(pid, keycode, False, flags)


def _normalize_key_name(k: str) -> str:
    k = k.strip().lower()
    if k == "cmd":
        return "command"
    if k == "ctrl":
        return "control"
    if k == "alt":
        return "option"
    if k == "return":
        return "enter"
    return k


def _press_key_combo(combo: str, pid: int) -> None:
    raw = combo.strip()

    # Repeated keys: "Escape Escape Escape"
    if " " in raw and "+" not in raw:
        for k in raw.split():
            k = _normalize_key_name(k)
            keycode = _KEYCODES.get(k)
            if keycode is not None:
                _cg_press_key(pid, keycode)
        return

    parts = [_normalize_key_name(p) for p in raw.split("+") if p.strip()]
    if not parts:
        return

    normalized = "+".join(parts)
    if normalized in _FORBIDDEN_COMBOS:
        raise ValueError(f"Forbidden key combo for safety: {normalized}")

    # Separate modifiers from main key.
    modifiers: list[str] = []
    main_key: str | None = None
    for p in parts:
        if p in _MODIFIER_FLAGS:
            modifiers.append(p)
        else:
            main_key = p

    if main_key is None:
        # All parts were modifiers — press the last one as the key.
        main_key = parts[-1]
        modifiers = parts[:-1] if len(parts) > 1 else []

    keycode = _KEYCODES.get(main_key)
    if keycode is None:
        raise ValueError(f"Unknown key: {main_key!r}")

    flags = 0
    for m in modifiers:
        flags |= _MODIFIER_FLAGS.get(m, 0)

    _cg_press_key(pid, keycode, flags)


def _cg_move(x: int, y: int) -> None:
    Quartz.CGWarpMouseCursorPosition(Quartz.CGPointMake(x, y))


def _cg_click(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    pt = Quartz.CGPointMake(x, y)
    btn_map = {
        "left": (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft),
        "right": (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp, Quartz.kCGMouseButtonRight),
        "middle": (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp, Quartz.kCGMouseButtonCenter),
    }
    down_type, up_type, btn = btn_map.get(button, btn_map["left"])

    for i in range(clicks):
        down = Quartz.CGEventCreateMouseEvent(None, down_type, pt, btn)
        up = Quartz.CGEventCreateMouseEvent(None, up_type, pt, btn)
        if clicks > 1:
            Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventClickState, i + 1)
            Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventClickState, i + 1)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        time.sleep(0.02)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        if i < clicks - 1:
            time.sleep(0.05)


def _cg_drag(x0: int, y0: int, x1: int, y1: int, duration: float = 0.2) -> None:
    pt0 = Quartz.CGPointMake(x0, y0)
    pt1 = Quartz.CGPointMake(x1, y1)

    Quartz.CGWarpMouseCursorPosition(pt0)
    time.sleep(0.05)

    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt0, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(duration)

    drag = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDragged, pt1, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, drag)
    time.sleep(0.05)

    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt1, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def _cg_scroll(dx: int = 0, dy: int = 0) -> None:
    event = Quartz.CGEventCreateScrollWheelEvent(
        None, Quartz.kCGScrollEventUnitLine, 2, int(dy), int(dx)
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _cg_type_text(pid: int, text: str, interval: float = 0.012) -> None:
    for char in text:
        down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(down, len(char), char)
        Quartz.CGEventKeyboardSetUnicodeString(up, len(char), char)
        Quartz.CGEventPostToPid(pid, down)
        time.sleep(interval)
        Quartz.CGEventPostToPid(pid, up)
        time.sleep(interval)


# ── Image helpers ─────────────────────────────────────────────────────────────

def _image_to_base64_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ── ComputerTool ──────────────────────────────────────────────────────────────

class ComputerTool:
    """
    Local implementation of Anthropic's Computer Use tool.

    Backed by macOS Quartz CGEvent APIs:
    - Keys via CGEventPostToPid (bypasses focus requirements)
    - Mouse via CGWarpMouseCursorPosition + CGEventPost
    - Screenshots via CGWindowListCreateImage

    Coordinates are in API display space (display_width_px x display_height_px)
    and mapped to FL Studio's window bounds.
    """

    name: str = "computer"
    api_type: str

    def __init__(
        self,
        *,
        api_type: str,
        display_width_px: int,
        display_height_px: int,
        enable_zoom: bool = True,
    ):
        self.api_type = str(api_type)
        self.display_width_px = int(display_width_px)
        self.display_height_px = int(display_height_px)
        self.enable_zoom = bool(enable_zoom)

        self._fl_pid: int | None = None
        self._fl_window_id: int | None = None
        self._fl_window_bounds: tuple[int, int, int, int] | None = None  # x, y, w, h

    def to_tool_param(self) -> dict[str, Any]:
        tool: dict[str, Any] = {
            "type": self.api_type,
            "name": self.name,
            "display_width_px": self.display_width_px,
            "display_height_px": self.display_height_px,
        }
        if self.api_type == "computer_20251124" and self.enable_zoom:
            tool["enable_zoom"] = True
        return tool

    # ── FL Studio state ───────────────────────────────────────────────────

    def _get_fl_pid(self) -> int | None:
        if self._fl_pid is not None:
            ws = NSWorkspace.sharedWorkspace()
            for app in ws.runningApplications():
                if app.processIdentifier() == self._fl_pid:
                    return self._fl_pid
            # Cached PID went stale after app restart.
            self._fl_pid = None

        if self._fl_pid is None:
            self._fl_pid = _find_fl_pid()
        return self._fl_pid

    def _require_fl_pid(self) -> int:
        pid = self._get_fl_pid()
        if pid is None:
            raise RuntimeError("FL Studio not running")
        return pid

    def _find_fl_window(self) -> tuple[int, tuple[int, int, int, int]] | None:
        options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []

        best: tuple[int, tuple[int, int, int, int], int] | None = None
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

    def _get_fl_bounds(self) -> tuple[int, int, int, int] | None:
        if self._fl_window_bounds is None or self._fl_window_id is None:
            found = self._find_fl_window()
            if found is None:
                return None
            self._fl_window_id, self._fl_window_bounds = found
        return self._fl_window_bounds

    def _refresh_fl_window(self) -> tuple[int, int, int, int] | None:
        self._fl_window_id = None
        self._fl_window_bounds = None
        return self._get_fl_bounds()

    # ── Screenshot ────────────────────────────────────────────────────────

    def _capture_fl_window(self) -> Image.Image | None:
        found = self._find_fl_window()
        if found is None:
            return None
        wid, (x, y, ww, wh) = found
        self._fl_window_id = wid
        self._fl_window_bounds = (x, y, ww, wh)

        rect = Quartz.CGRectMake(x, y, ww, wh)
        cgimg = Quartz.CGWindowListCreateImage(
            rect,
            Quartz.kCGWindowListOptionIncludingWindow,
            wid,
            Quartz.kCGWindowImageBoundsIgnoreFraming,
        )
        if cgimg is None:
            return None

        width = Quartz.CGImageGetWidth(cgimg)
        height = Quartz.CGImageGetHeight(cgimg)
        bpr = Quartz.CGImageGetBytesPerRow(cgimg)
        provider = Quartz.CGImageGetDataProvider(cgimg)
        data = Quartz.CGDataProviderCopyData(provider)
        buf = bytes(data)

        img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", bpr, 1)
        return img.copy()

    def _screenshot_api_space(self) -> Image.Image:
        window_img = self._capture_fl_window()
        if window_img is None:
            raise RuntimeError(
                "FL Studio window not found. Make sure FL Studio is visible (not minimized)."
            )
        if window_img.size != (self.display_width_px, self.display_height_px):
            window_img = window_img.resize(
                (self.display_width_px, self.display_height_px), Image.Resampling.LANCZOS
            )
        return window_img

    def _wait_for_ui_settle(
        self, timeout_s: float = 5.0, interval_s: float = 0.4, threshold: float = 0.985
    ) -> Image.Image:
        prev = self._screenshot_api_space()
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(interval_s)
            curr = self._screenshot_api_space()
            diff = ImageChops.difference(prev, curr)
            mean_delta = sum(diff.convert("L").getdata()) / (255.0 * diff.size[0] * diff.size[1])
            similarity = 1.0 - mean_delta
            if similarity >= threshold:
                return curr
            prev = curr
        return prev

    # ── Coordinate mapping ────────────────────────────────────────────────

    def _scale_xy_from_api(self, x: int, y: int) -> tuple[int, int]:
        bounds = self._get_fl_bounds()
        if bounds is None:
            main = Quartz.CGMainDisplayID()
            sw = Quartz.CGDisplayPixelsWide(main)
            sh = Quartz.CGDisplayPixelsHigh(main)
            sx = sw / float(self.display_width_px)
            sy = sh / float(self.display_height_px)
            return int(round(x * sx)), int(round(y * sy))
        _, _, ww, wh = bounds
        sx = ww / float(self.display_width_px)
        sy = wh / float(self.display_height_px)
        return int(round(x * sx)), int(round(y * sy))

    def _api_to_screen(self, x: int, y: int) -> tuple[int, int]:
        sx, sy = self._scale_xy_from_api(x, y)
        bounds = self._get_fl_bounds()
        if bounds is not None:
            ox, oy, ww, wh = bounds
            sx = max(0, min(ww - 1, sx))
            sy = max(0, min(wh - 1, sy))
            return ox + sx, oy + sy
        return sx, sy

    # ── Main dispatch ─────────────────────────────────────────────────────

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        action = tool_input.get("action")
        if not isinstance(action, str):
            return ToolResult(error=f"Invalid tool input: missing action: {tool_input!r}")

        try:
            if action in _INPUT_ACTIONS and not _has_post_event_access():
                return ToolResult(error=_build_input_access_error())

            _activate_fl_studio()

            if action == "screenshot":
                img = self._screenshot_api_space()
                return ToolResult(base64_image_png=_image_to_base64_png(img))

            if self._refresh_fl_window() is None:
                return ToolResult(error="FL Studio window not found; refusing to execute action.")

            pid = self._require_fl_pid()

            if action == "cursor_position":
                event = Quartz.CGEventCreate(None)
                point = Quartz.CGEventGetLocation(event)
                return ToolResult(
                    output=f"X={int(point.x)},Y={int(point.y)}",
                    base64_image_png=_image_to_base64_png(self._screenshot_api_space()),
                )

            if action == "wait":
                duration = tool_input.get("duration", 0.5)
                if not isinstance(duration, (int, float)) or duration < 0 or duration > 60:
                    return ToolResult(error=f"Invalid duration: {duration!r}")
                time.sleep(float(duration))
                return ToolResult(base64_image_png=_image_to_base64_png(self._screenshot_api_space()))

            if action == "mouse_move":
                coord = tool_input.get("coordinate")
                if not (isinstance(coord, (list, tuple)) and len(coord) == 2):
                    return ToolResult(error=f"mouse_move requires [x,y], got: {coord!r}")
                ax, ay = self._api_to_screen(int(coord[0]), int(coord[1]))
                _cg_move(ax, ay)
                img = self._wait_for_ui_settle(timeout_s=2.0)
                return ToolResult(base64_image_png=_image_to_base64_png(img))

            if action in ("left_click", "right_click", "middle_click", "double_click", "triple_click"):
                coord = tool_input.get("coordinate")
                if coord is not None:
                    if not (isinstance(coord, (list, tuple)) and len(coord) == 2):
                        return ToolResult(error=f"{action} coordinate must be [x,y], got: {coord!r}")
                    ax, ay = self._api_to_screen(int(coord[0]), int(coord[1]))
                    _cg_move(ax, ay)
                    time.sleep(0.05)
                else:
                    event = Quartz.CGEventCreate(None)
                    point = Quartz.CGEventGetLocation(event)
                    ax, ay = int(point.x), int(point.y)

                button = {"left_click": "left", "right_click": "right", "middle_click": "middle"}.get(action, "left")
                clicks = {"double_click": 2, "triple_click": 3}.get(action, 1)
                _cg_click(ax, ay, button=button, clicks=clicks)
                img = self._wait_for_ui_settle()
                return ToolResult(base64_image_png=_image_to_base64_png(img))

            if action == "left_click_drag":
                start = tool_input.get("start_coordinate")
                end = tool_input.get("coordinate")
                if not (isinstance(start, (list, tuple)) and len(start) == 2 and isinstance(end, (list, tuple)) and len(end) == 2):
                    return ToolResult(error=f"left_click_drag requires start_coordinate and coordinate")
                ax0, ay0 = self._api_to_screen(int(start[0]), int(start[1]))
                ax1, ay1 = self._api_to_screen(int(end[0]), int(end[1]))
                _cg_drag(ax0, ay0, ax1, ay1)
                img = self._wait_for_ui_settle()
                return ToolResult(base64_image_png=_image_to_base64_png(img))

            if action == "scroll":
                direction = tool_input.get("scroll_direction")
                amount = tool_input.get("scroll_amount")
                if direction not in ("up", "down", "left", "right"):
                    return ToolResult(error=f"scroll_direction must be up/down/left/right, got: {direction!r}")
                if not isinstance(amount, int) or amount < 0 or amount > 50:
                    return ToolResult(error=f"scroll_amount must be int 0..50, got: {amount!r}")
                coord = tool_input.get("coordinate")
                if coord is not None:
                    if not (isinstance(coord, (list, tuple)) and len(coord) == 2):
                        return ToolResult(error=f"scroll coordinate must be [x,y], got: {coord!r}")
                    ax, ay = self._api_to_screen(int(coord[0]), int(coord[1]))
                    _cg_move(ax, ay)
                    time.sleep(0.05)

                dx, dy = 0, 0
                if direction == "up":
                    dy = amount
                elif direction == "down":
                    dy = -amount
                elif direction == "left":
                    dx = -amount
                elif direction == "right":
                    dx = amount
                _cg_scroll(dx=dx, dy=dy)
                img = self._wait_for_ui_settle()
                return ToolResult(base64_image_png=_image_to_base64_png(img))

            if action == "key":
                text = tool_input.get("text")
                if not isinstance(text, str) or not text.strip():
                    return ToolResult(error=f"key requires non-empty text, got: {text!r}")
                _press_key_combo(text, pid)
                img = self._wait_for_ui_settle()
                return ToolResult(base64_image_png=_image_to_base64_png(img))

            if action == "hold_key":
                text = tool_input.get("text")
                duration = tool_input.get("duration")
                if not isinstance(text, str) or not text.strip():
                    return ToolResult(error=f"hold_key requires text, got: {text!r}")
                if not isinstance(duration, (int, float)) or duration < 0 or duration > 60:
                    return ToolResult(error=f"hold_key duration must be 0..60, got: {duration!r}")
                key = _normalize_key_name(text)
                keycode = _KEYCODES.get(key)
                if keycode is None:
                    return ToolResult(error=f"Unknown key: {key!r}")
                _cg_post_key_to_pid(pid, keycode, True)
                time.sleep(float(duration))
                _cg_post_key_to_pid(pid, keycode, False)
                img = self._wait_for_ui_settle()
                return ToolResult(base64_image_png=_image_to_base64_png(img))

            if action == "type":
                text = tool_input.get("text")
                if not isinstance(text, str):
                    return ToolResult(error=f"type requires text string, got: {text!r}")
                _cg_type_text(pid, text)
                img = self._wait_for_ui_settle()
                return ToolResult(base64_image_png=_image_to_base64_png(img))

            if action == "zoom":
                region = tool_input.get("region")
                if not (isinstance(region, (list, tuple)) and len(region) == 4 and all(isinstance(c, int) and c >= 0 for c in region)):
                    return ToolResult(error=f"zoom requires region [x0,y0,x1,y1], got: {region!r}")
                img = self._screenshot_api_space()
                x0, y0, x1, y1 = int(region[0]), int(region[1]), int(region[2]), int(region[3])
                x0 = max(0, min(self.display_width_px - 1, x0))
                y0 = max(0, min(self.display_height_px - 1, y0))
                x1 = max(0, min(self.display_width_px, x1))
                y1 = max(0, min(self.display_height_px, y1))
                if x1 <= x0 or y1 <= y0:
                    return ToolResult(error=f"Invalid zoom region: {(x0, y0, x1, y1)}")
                cropped = img.crop((x0, y0, x1, y1))
                return ToolResult(base64_image_png=_image_to_base64_png(cropped))

            return ToolResult(error=f"Unsupported action: {action!r}")

        except Exception as e:
            return ToolResult(error=f"{type(e).__name__}: {e}")
