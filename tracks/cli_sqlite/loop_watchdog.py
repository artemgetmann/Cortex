from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WATCHDOG_STATE_FILENAME = "loop_watchdog_state.json"
DEFAULT_REJECTION_STREAK_THRESHOLD = 2


@dataclass(frozen=True)
class LoopWatchdogState:
    version: int = 1
    safe_mode_active: bool = False
    safe_mode_failure_streak: int = 0
    rejection_streak: int = 0
    last_run_id: str = ""
    last_failure_signals: tuple[str, ...] = ()
    last_stop_flag: bool = False
    updated_at_ts: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": int(self.version),
            "safe_mode_active": bool(self.safe_mode_active),
            "safe_mode_failure_streak": int(self.safe_mode_failure_streak),
            "rejection_streak": int(self.rejection_streak),
            "last_run_id": str(self.last_run_id),
            "last_failure_signals": list(self.last_failure_signals),
            "last_stop_flag": bool(self.last_stop_flag),
            "updated_at_ts": float(self.updated_at_ts),
        }


@dataclass(frozen=True)
class LoopWatchdogSnapshot:
    repeated_hard_failure_signatures: int = 0
    contract_gap_unresolved_count: int = 0
    rejection_streak: int = 0


@dataclass(frozen=True)
class LoopWatchdogDecision:
    safe_mode_active: bool
    safe_mode_triggered: bool
    stop_flag: bool
    failure_signals: tuple[str, ...]
    disable_self_edit: bool
    disable_posttask_patching: bool
    safe_mode_failure_streak: int


def state_path_for_learning_root(*, learning_root: Path) -> Path:
    return learning_root / WATCHDOG_STATE_FILENAME


def load_watchdog_state(*, state_path: Path) -> LoopWatchdogState:
    default = LoopWatchdogState()
    if not state_path.exists():
        return default
    try:
        parsed = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return default
    if not isinstance(parsed, dict):
        return default
    return _state_from_dict(parsed)


def persist_watchdog_state(*, state_path: Path, state: LoopWatchdogState) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def evaluate_watchdog_policy(
    *,
    state: LoopWatchdogState,
    snapshot: LoopWatchdogSnapshot,
    rejection_streak_threshold: int = DEFAULT_REJECTION_STREAK_THRESHOLD,
) -> LoopWatchdogDecision:
    threshold = max(1, int(rejection_streak_threshold))
    failure_signals: list[str] = []
    if int(snapshot.repeated_hard_failure_signatures) > 0:
        failure_signals.append("repeated_hard_failure_signatures")
    if int(snapshot.contract_gap_unresolved_count) > 0:
        failure_signals.append("contract_gap_unresolved")
    if int(snapshot.rejection_streak) >= threshold:
        failure_signals.append("posttask_rejection_streak")

    had_safe_mode = bool(state.safe_mode_active)
    failure_detected = bool(failure_signals)
    safe_mode_active = had_safe_mode
    safe_mode_triggered = False

    if failure_detected and not had_safe_mode:
        safe_mode_active = True
        safe_mode_triggered = True
    elif had_safe_mode and not failure_detected:
        safe_mode_active = False

    safe_mode_failure_streak = 0
    stop_flag = False
    if safe_mode_active and failure_detected:
        if had_safe_mode:
            safe_mode_failure_streak = int(state.safe_mode_failure_streak) + 1
            stop_flag = True
        else:
            safe_mode_failure_streak = 1

    return LoopWatchdogDecision(
        safe_mode_active=bool(safe_mode_active),
        safe_mode_triggered=bool(safe_mode_triggered),
        stop_flag=bool(stop_flag),
        failure_signals=tuple(failure_signals),
        disable_self_edit=bool(safe_mode_active),
        disable_posttask_patching=bool(safe_mode_active),
        safe_mode_failure_streak=max(0, int(safe_mode_failure_streak)),
    )


def next_watchdog_state(
    *,
    state: LoopWatchdogState,
    decision: LoopWatchdogDecision,
    run_id: str,
    posttask_rejection_total: int,
    rejection_streak_threshold: int = DEFAULT_REJECTION_STREAK_THRESHOLD,
) -> LoopWatchdogState:
    threshold = max(1, int(rejection_streak_threshold))
    rejections = max(0, int(posttask_rejection_total))
    rejection_streak = int(state.rejection_streak) + 1 if rejections > 0 else 0

    safe_mode_active = bool(decision.safe_mode_active)
    safe_mode_failure_streak = max(0, int(decision.safe_mode_failure_streak))
    if not safe_mode_active and rejection_streak >= threshold:
        safe_mode_active = True
        safe_mode_failure_streak = 0
    if not safe_mode_active:
        safe_mode_failure_streak = 0

    return LoopWatchdogState(
        version=1,
        safe_mode_active=bool(safe_mode_active),
        safe_mode_failure_streak=max(0, int(safe_mode_failure_streak)),
        rejection_streak=max(0, int(rejection_streak)),
        last_run_id=str(run_id),
        last_failure_signals=tuple(decision.failure_signals),
        last_stop_flag=bool(decision.stop_flag),
        updated_at_ts=float(time.time()),
    )


def _state_from_dict(raw: dict[str, Any]) -> LoopWatchdogState:
    signals = raw.get("last_failure_signals", [])
    if not isinstance(signals, list):
        signals = []
    return LoopWatchdogState(
        version=max(1, int(raw.get("version", 1) or 1)),
        safe_mode_active=bool(raw.get("safe_mode_active", False)),
        safe_mode_failure_streak=max(0, int(raw.get("safe_mode_failure_streak", 0) or 0)),
        rejection_streak=max(0, int(raw.get("rejection_streak", 0) or 0)),
        last_run_id=str(raw.get("last_run_id", "")),
        last_failure_signals=tuple(str(signal).strip() for signal in signals if str(signal).strip()),
        last_stop_flag=bool(raw.get("last_stop_flag", False)),
        updated_at_ts=float(raw.get("updated_at_ts", 0.0) or 0.0),
    )
