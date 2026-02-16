from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


INSPECTION_ACTIONS = {"zoom", "mouse_move"}
DECISIVE_ACTIONS = {"left_click", "key"}
DEFAULT_DRUM_CONTRACT_PATH = Path("skills/fl-studio/drum-pattern/CONTRACT.json")


@dataclass(frozen=True)
class DrumRunEvaluation:
    applicable: bool
    passed: bool
    score: float
    reasons: list[str]
    clicks: list[dict[str, int]]
    zoom_count: int
    decisive_count: int
    state_verified: bool
    state_step: int
    state_active_steps: list[int]
    contract_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "passed": self.passed,
            "score": self.score,
            "reasons": self.reasons,
            "clicks": self.clicks,
            "zoom_count": self.zoom_count,
            "decisive_count": self.decisive_count,
            "state_verified": self.state_verified,
            "state_step": self.state_step,
            "state_active_steps": self.state_active_steps,
            "contract_path": self.contract_path,
        }


def _default_drum_contract() -> dict[str, Any]:
    return {
        "id": "fl-studio-drum-pattern-v1",
        "task_match": {
            "all": ["fl studio"],
            "any": ["drum", "kick", "4-on-the-floor", "channel rack"],
        },
        "signals": {
            "click_band": {"y_min": 130, "y_max": 170, "required_clicks": 4},
            "selector_strip": {"x_lt": 420},
            "step_spacing": {
                "diff_min": [40, 55, 55],
                "diff_max": [90, 90, 90],
                "require_monotonic_x": True,
            },
            "inspection_ratio": {"max_zoom_per_decisive": 1.0},
        },
        "required_outcomes": [
            "enough_clicks",
            "monotonic_step_order",
            "spacing_in_range",
        ],
        "forbidden_patterns": [
            "selector_zone_misclick",
            "inspection_loop",
        ],
        "pass_rule": "required_outcomes && no_forbidden",
        "reason_codes": [
            "insufficient_step_clicks",
            "selector_zone_misclick",
            "non_monotonic_step_order",
            "step_spacing_out_of_range",
            "inspection_loop",
        ],
        "reference_images": [],
    }


def load_contract(path: Path = DEFAULT_DRUM_CONTRACT_PATH) -> dict[str, Any]:
    if not path.exists():
        return _default_drum_contract()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return _default_drum_contract()


def _task_matches(task: str, contract: dict[str, Any]) -> bool:
    tm = contract.get("task_match", {})
    if not isinstance(tm, dict):
        return False
    lower = task.lower()
    all_terms = [str(t).lower() for t in tm.get("all", []) if str(t).strip()]
    any_terms = [str(t).lower() for t in tm.get("any", []) if str(t).strip()]
    if all_terms and not all(t in lower for t in all_terms):
        return False
    if any_terms and not any(t in lower for t in any_terms):
        return False
    return True


def evaluate_drum_run(
    task: str,
    events: list[dict[str, Any]],
    *,
    contract_path: Path = DEFAULT_DRUM_CONTRACT_PATH,
) -> DrumRunEvaluation:
    contract = load_contract(contract_path)
    cpath = str(contract_path)
    if not _task_matches(task, contract):
        return DrumRunEvaluation(
            applicable=False,
            passed=False,
            score=0.0,
            reasons=[],
            clicks=[],
            zoom_count=0,
            decisive_count=0,
            state_verified=False,
            state_step=0,
            state_active_steps=[],
            contract_path=cpath,
        )

    def _extract_state_payload(ev: dict[str, Any]) -> dict[str, Any] | None:
        if ev.get("tool") != "extract_fl_state":
            return None
        if not bool(ev.get("ok")):
            return None
        out = ev.get("output")
        if isinstance(out, dict):
            return out
        if isinstance(out, str):
            text = out.strip()
            if not text:
                return None
            try:
                parsed = json.loads(text)
            except Exception:
                return None
            return parsed if isinstance(parsed, dict) else None
        return None

    signals = contract.get("signals", {}) if isinstance(contract.get("signals"), dict) else {}
    click_band = signals.get("click_band", {}) if isinstance(signals.get("click_band"), dict) else {}
    selector_strip = signals.get("selector_strip", {}) if isinstance(signals.get("selector_strip"), dict) else {}
    step_spacing = signals.get("step_spacing", {}) if isinstance(signals.get("step_spacing"), dict) else {}
    inspection = signals.get("inspection_ratio", {}) if isinstance(signals.get("inspection_ratio"), dict) else {}

    y_min = int(click_band.get("y_min", 130))
    y_max = int(click_band.get("y_max", 170))
    required_clicks = int(click_band.get("required_clicks", 4))
    selector_x_lt = int(selector_strip.get("x_lt", 420))
    ratio_max = float(inspection.get("max_zoom_per_decisive", 1.0))
    require_monotonic_x = bool(step_spacing.get("require_monotonic_x", True))

    diff_min_raw = step_spacing.get("diff_min", [40, 55, 55])
    diff_max_raw = step_spacing.get("diff_max", [90, 90, 90])
    diff_min = [int(v) for v in diff_min_raw] if isinstance(diff_min_raw, list) else [40, 55, 55]
    diff_max = [int(v) for v in diff_max_raw] if isinstance(diff_max_raw, list) else [90, 90, 90]
    if len(diff_min) < 3:
        diff_min = (diff_min + [55, 55, 55])[:3]
    if len(diff_max) < 3:
        diff_max = (diff_max + [90, 90, 90])[:3]

    clicks: list[dict[str, int]] = []
    zoom_count = 0
    decisive_count = 0
    latest_state_step = 0
    latest_state_payload: dict[str, Any] | None = None

    for ev in events:
        state_payload = _extract_state_payload(ev)
        if state_payload is not None:
            s = int(ev.get("step", 0) or 0)
            if s >= latest_state_step:
                latest_state_step = s
                latest_state_payload = state_payload
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
        if y_min <= y <= y_max:
            clicks.append({"step": int(ev.get("step", 0) or 0), "x": x, "y": y})

    first = clicks[:required_clicks]
    xs = [c["x"] for c in first]
    reasons: list[str] = []
    outcomes = {
        "enough_clicks": len(first) >= required_clicks,
        "monotonic_step_order": True,
        "spacing_in_range": True,
    }
    state_verified = False
    state_active_steps: list[int] = []

    if latest_state_payload is not None:
        four = latest_state_payload.get("four_on_floor")
        if isinstance(four, dict):
            active_match = bool(four.get("active_match", False))
            active_steps = four.get("active_steps")
            if isinstance(active_steps, list):
                for item in active_steps:
                    if isinstance(item, int) and 1 <= item <= 16:
                        state_active_steps.append(item)
            if not state_active_steps:
                guessed = four.get("detected_steps")
                if isinstance(guessed, list):
                    for item in guessed:
                        if isinstance(item, int) and 1 <= item <= 16:
                            state_active_steps.append(item)
            state_active_steps = sorted(set(state_active_steps))
            if active_match:
                state_verified = True
            elif state_active_steps:
                target = {1, 5, 9, 13}
                state_verified = target.issubset(set(state_active_steps))

    if len(first) < required_clicks:
        reasons.append("insufficient_step_clicks")
        outcomes["monotonic_step_order"] = False
        outcomes["spacing_in_range"] = False
    else:
        if any(x < selector_x_lt for x in xs):
            reasons.append("selector_zone_misclick")
        if require_monotonic_x and xs != sorted(xs):
            reasons.append("non_monotonic_step_order")
            outcomes["monotonic_step_order"] = False

        diffs = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        if len(diffs) == 3:
            bounds_ok = all(diff_min[i] <= diffs[i] <= diff_max[i] for i in range(3))
            if not bounds_ok:
                reasons.append("step_spacing_out_of_range")
                outcomes["spacing_in_range"] = False

    if decisive_count > 0 and (zoom_count / float(decisive_count)) > ratio_max:
        reasons.append("inspection_loop")

    required_outcomes = contract.get("required_outcomes", [])
    if isinstance(required_outcomes, list):
        for name in required_outcomes:
            if isinstance(name, str) and name in outcomes and not outcomes[name]:
                # Reason tags already set above for our current outcome set.
                pass

    forbidden_patterns = contract.get("forbidden_patterns", [])
    forbidden_set = {x for x in forbidden_patterns if isinstance(x, str)}
    unique_reasons = sorted(set(reasons))
    if state_verified and "inspection_loop" in unique_reasons:
        # If the final state proves success, inspection inefficiency should not hard-fail.
        unique_reasons.remove("inspection_loop")
    has_forbidden = any(r in forbidden_set for r in unique_reasons)
    all_outcomes_ok = all(outcomes.values()) or state_verified
    passed = all_outcomes_ok and not has_forbidden and len(unique_reasons) == 0

    score = max(0.0, 1.0 - (0.25 * len(unique_reasons)))
    if passed:
        score = 1.0

    return DrumRunEvaluation(
        applicable=True,
        passed=passed,
        score=round(score, 3),
        reasons=unique_reasons,
        clicks=first,
        zoom_count=zoom_count,
        decisive_count=decisive_count,
        state_verified=state_verified,
        state_step=latest_state_step,
        state_active_steps=state_active_steps,
        contract_path=cpath,
    )
