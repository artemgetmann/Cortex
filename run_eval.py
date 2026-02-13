from __future__ import annotations

from dataclasses import dataclass
from typing import Any


INSPECTION_ACTIONS = {"zoom", "mouse_move"}
DECISIVE_ACTIONS = {"left_click", "key"}


@dataclass(frozen=True)
class DrumRunEvaluation:
    applicable: bool
    passed: bool
    score: float
    reasons: list[str]
    clicks: list[dict[str, int]]
    zoom_count: int
    decisive_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "passed": self.passed,
            "score": self.score,
            "reasons": self.reasons,
            "clicks": self.clicks,
            "zoom_count": self.zoom_count,
            "decisive_count": self.decisive_count,
        }


def _looks_like_drum_task(task: str) -> bool:
    t = task.lower()
    hints = [
        "fl studio",
        "drum",
        "kick",
        "4-on-the-floor",
        "channel rack",
    ]
    return sum(1 for h in hints if h in t) >= 2


def evaluate_drum_run(task: str, events: list[dict[str, Any]]) -> DrumRunEvaluation:
    if not _looks_like_drum_task(task):
        return DrumRunEvaluation(
            applicable=False,
            passed=False,
            score=0.0,
            reasons=[],
            clicks=[],
            zoom_count=0,
            decisive_count=0,
        )

    clicks: list[dict[str, int]] = []
    zoom_count = 0
    decisive_count = 0

    for ev in events:
        if ev.get("tool") != "computer":
            continue
        tool_input = ev.get("tool_input")
        if not isinstance(tool_input, dict):
            continue
        action = tool_input.get("action")
        if action in INSPECTION_ACTIONS:
            zoom_count += 1
        if action in DECISIVE_ACTIONS:
            decisive_count += 1

        if action != "left_click":
            continue
        coord = tool_input.get("coordinate")
        if not (isinstance(coord, list) and len(coord) == 2):
            continue
        x_raw, y_raw = coord[0], coord[1]
        if not isinstance(x_raw, (int, float)) or not isinstance(y_raw, (int, float)):
            continue
        x = int(x_raw)
        y = int(y_raw)
        # Channel Rack top row where kick pattern clicks happen in our runs.
        if 130 <= y <= 170:
            clicks.append({"step": int(ev.get("step", 0) or 0), "x": x, "y": y})

    first4 = clicks[:4]
    reasons: list[str] = []
    xs = [c["x"] for c in first4]

    if len(first4) < 4:
        reasons.append("insufficient_step_clicks")
    else:
        # Selector strip is to the left of the step band.
        if any(x < 420 for x in xs):
            reasons.append("selector_zone_misclick")
        if xs != sorted(xs):
            reasons.append("non_monotonic_step_order")

        diffs = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        # For 1/5/9/13 pattern spacing should be roughly even for last three clicks.
        if len(diffs) == 3:
            if not (40 <= diffs[0] <= 90 and 55 <= diffs[1] <= 90 and 55 <= diffs[2] <= 90):
                reasons.append("step_spacing_out_of_range")

    if decisive_count > 0 and (zoom_count / float(decisive_count)) > 1.0:
        reasons.append("inspection_loop")

    unique_reasons = sorted(set(reasons))
    passed = len(unique_reasons) == 0
    score = max(0.0, 1.0 - (0.25 * len(unique_reasons)))
    if passed:
        score = 1.0

    return DrumRunEvaluation(
        applicable=True,
        passed=passed,
        score=round(score, 3),
        reasons=unique_reasons,
        clicks=first4,
        zoom_count=zoom_count,
        decisive_count=decisive_count,
    )

