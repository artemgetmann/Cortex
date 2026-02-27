#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracks.cli_sqlite import run_service


ROOT_DIR = Path(__file__).resolve().parents[1]
TRACK_DIR = ROOT_DIR / "tracks" / "cli_sqlite"
TASKS_ROOT = TRACK_DIR / "tasks"
SESSIONS_ROOT = TRACK_DIR / "sessions"
LESSONS_V2_PATH = TRACK_DIR / "learning" / "lessons_v2.jsonl"
DISPATCH_PROFILE = str(os.environ.get("CORTEX_DISPATCH_PROFILE", "legacy")).strip().lower()
USE_V15_PROFILE = DISPATCH_PROFILE in {"v15", "proof", "cli_sqlite_v15"}
RUNNER_LEGACY = TRACK_DIR / "scripts" / "run_cli_agent.py"
RUNNER_V15 = ROOT_DIR / "tracks" / "cli_sqlite_v15" / "run_cli_agent_v15.py"
RUNNER = RUNNER_V15 if USE_V15_PROFILE else RUNNER_LEGACY
DEFAULT_EXECUTOR_MODEL = "gpt-5-nano" if USE_V15_PROFILE else "claude-haiku-4-5"
DEFAULT_LLM_BACKEND = "openai" if USE_V15_PROFILE else "anthropic"

KNOWN_TASK_DOMAIN: dict[str, str] = {
    "aggregate_report": "gridtool",
    "aggregate_report_holdout": "gridtool",
    "basic_transform": "gridtool",
    "multi_step_pipeline": "gridtool",
    "multi_agg_pipeline": "gridtool",
    "regional_performance": "gridtool",
    "import_aggregate": "sqlite",
    "incremental_reconcile": "sqlite",
    "idempotent_rerun": "sqlite",
    "partial_failure_recovery": "sqlite",
    "shell_git_train_release_flow": "shell",
    "shell_git_transfer_hotfix": "shell",
    "shell_excel_build_report": "shell",
    "shell_excel_multi_summary": "shell",
    "artic_search_basic": "artic",
    "artic_pagination_extract": "artic",
    "artic_followup_fetch": "artic",
}

RUN_PREFIXES = ("/run", "run ")
STATUS_PREFIXES = ("/learn-status", "/learnstatus", "/learn_status", "/run-status", "/status", "learn status")
CANCEL_PREFIXES = ("/cancel", "/cancel-run", "cancel run")
FOLLOWUP_PREFIXES = ("/followup", "followup ")
CHAT_PREFIXES = ("/chat",)


@dataclass(frozen=True)
class DispatchPlan:
    mode: str
    chat_scope: str = "global"
    domain: str | None = None
    task_id: str | None = None
    task_text: str | None = None
    followup_text: str | None = None
    run_id: str | None = None
    max_steps: int = 6
    model_executor: str = DEFAULT_EXECUTOR_MODEL
    llm_backend: str = DEFAULT_LLM_BACKEND
    posttask_learn: bool = True
    progress: bool = False
    progress_limit: int = 8
    reason: str = ""


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _strip_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix.lower()):
            return text[len(prefix):].strip()
    return text.strip()


def _parse_keyvals(payload: str) -> tuple[dict[str, str], str]:
    """
    Parse compact key-value controls from the front of the run payload.

    Example:
      "domain=shell steps=8 model=claude-haiku-4-5 build a git hotfix flow"
    -> {"domain":"shell","steps":"8","model":"claude-haiku-4-5"}, "build a git hotfix flow"
    """
    controls: dict[str, str] = {}
    tokens = payload.split()
    tail_start = 0
    for idx, token in enumerate(tokens):
        if "=" not in token:
            tail_start = idx
            break
        key, value = token.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            tail_start = idx
            break
        controls[key] = value
        tail_start = idx + 1
    tail = " ".join(tokens[tail_start:]).strip()
    return controls, tail


def _looks_like_run_id(value: str) -> bool:
    token = str(value or "").strip()
    return token.startswith("run_") or token.startswith("run-")


def _parse_bool(value: str, *, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "on", "yes", "y"}:
        return True
    if text in {"0", "false", "off", "no", "n"}:
        return False
    return default


def _parse_progress_limit(value: str, *, default: int = 8) -> int:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        return max(1, min(20, int(raw)))
    except ValueError:
        return default


def _coerce_lifecycle_event(row: dict[str, Any]) -> dict[str, Any] | None:
    event = str(row.get("event", "")).strip().lower()
    if not event:
        return None
    ts_raw = row.get("ts")
    try:
        ts = float(ts_raw)
    except (TypeError, ValueError):
        ts = 0.0

    step_raw = row.get("step")
    try:
        step = int(step_raw) if step_raw is not None else None
    except (TypeError, ValueError):
        step = None

    session_raw = row.get("session_id")
    try:
        session_id = int(session_raw) if session_raw is not None else None
    except (TypeError, ValueError):
        session_id = None

    trigger_text = str(row.get("trigger", "")).strip()
    task_text = str(row.get("task_id", "")).strip()
    domain_text = str(row.get("domain", "")).strip()
    text_value = row.get("text")
    source_value = row.get("source")
    return {
        "ts": ts,
        "event": event,
        "step": step,
        "trigger": trigger_text or None,
        "session_id": session_id,
        "task_id": task_text or None,
        "domain": domain_text or None,
        "text": str(text_value).strip() if text_value is not None else None,
        "source": str(source_value).strip() if source_value is not None else None,
    }


def _latest_lifecycle_events(*, run_id: str, limit: int) -> list[dict[str, Any]]:
    path = run_service.resolve_lifecycle_path()
    rows = run_service.list_events(run_id, max_events=max(1, limit), lifecycle_path=path)
    matched: list[dict[str, Any]] = []
    for row in rows:
        normalized = _coerce_lifecycle_event(row)
        if normalized is not None:
            matched.append(normalized)
    return matched


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))


def _infer_domain(task_text: str, fallback: str = "shell") -> str:
    lowered = task_text.lower()
    if any(key in lowered for key in ("sqlite", "sql ", "query", "table", "database")):
        return "sqlite"
    if any(key in lowered for key in ("gridtool", "tally", "rank ", "fixture.csv")):
        return "gridtool"
    if any(key in lowered for key in ("artic", "search api", "pagination")):
        return "artic"
    if any(key in lowered for key in ("shell", "bash", "git", "python", "xlsx", "excel", "csv")):
        return "shell"
    return fallback


def _known_task_ids() -> set[str]:
    rows: set[str] = set(KNOWN_TASK_DOMAIN.keys())
    if not TASKS_ROOT.exists():
        return rows
    for item in TASKS_ROOT.iterdir():
        if not item.is_dir():
            continue
        if (item / "task.md").exists():
            rows.add(item.name)
    return rows


def _extract_known_task_id(text: str, known_ids: set[str]) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9_\\-]+", text)
    for token in tokens:
        if token in known_ids:
            return token
    return None


def _dynamic_task_id(*, domain: str, chat_scope: str, task_text: str) -> str:
    normalized = _normalize_ws(task_text).lower()
    digest = hashlib.sha1(f"{chat_scope}|{domain}|{normalized}".encode("utf-8")).hexdigest()[:10]
    scope_slug = re.sub(r"[^a-z0-9]+", "-", chat_scope.lower()).strip("-")[:18] or "global"
    return f"openclaw_dynamic_{scope_slug}_{domain}_{digest}"


def _ensure_dynamic_task_dir(*, task_id: str, domain: str, task_text: str, chat_scope: str) -> Path:
    task_dir = TASKS_ROOT / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = task_dir / "task.md"
    metadata_path = task_dir / "OPENCLAW_TASK.json"
    if not task_md.exists():
        # The task prompt is intentionally explicit so the executor has a clear
        # objective without relying on benchmark-specific fixtures/contracts.
        body = (
            f"{domain} task: {task_id}\n\n"
            "Goal:\n"
            f"{task_text.strip()}\n\n"
            "Constraints:\n"
            "- Use available domain tools only.\n"
            "- Verify your outcome with explicit evidence before stopping.\n"
            "- If blocked, produce the smallest deterministic recovery step.\n"
        )
        task_md.write_text(body, encoding="utf-8")
    metadata = {
        "task_id": task_id,
        "domain": domain,
        "chat_scope": chat_scope,
        "created_at_epoch_s": int(time.time()),
        "source": "openclaw_dispatch",
        "task_text": _normalize_ws(task_text),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return task_dir


def _build_plan(text: str, *, chat_scope: str, default_domain: str) -> DispatchPlan:
    normalized = _normalize_ws(text)
    lowered = normalized.lower()

    if any(lowered.startswith(prefix) for prefix in STATUS_PREFIXES):
        payload = _strip_prefix(normalized, STATUS_PREFIXES)
        controls, payload_tail = _parse_keyvals(payload)
        run_id = controls.get("run_id", "").strip()
        tail_tokens = payload_tail.split() if payload_tail else []
        if not run_id and tail_tokens and _looks_like_run_id(tail_tokens[0]):
            run_id = tail_tokens[0].strip()
            tail_tokens = tail_tokens[1:]

        progress = _parse_bool(controls.get("progress", ""), default=False)
        progress_limit = _parse_progress_limit(controls.get("limit", controls.get("events", "")), default=8)
        for token in tail_tokens:
            lowered_token = token.strip().lower()
            if lowered_token in {"progress", "--progress"}:
                progress = True
                continue
            if lowered_token.startswith("progress="):
                progress = _parse_bool(lowered_token.split("=", 1)[1], default=progress)
                continue
            if lowered_token.startswith("limit="):
                progress_limit = _parse_progress_limit(lowered_token.split("=", 1)[1], default=progress_limit)
                continue
            if lowered_token.startswith("events="):
                progress_limit = _parse_progress_limit(lowered_token.split("=", 1)[1], default=progress_limit)

        return DispatchPlan(
            mode="status",
            chat_scope=chat_scope,
            run_id=run_id or None,
            progress=progress,
            progress_limit=progress_limit,
            reason="status_prefix",
        )

    if any(lowered.startswith(prefix) for prefix in CANCEL_PREFIXES):
        payload = _strip_prefix(normalized, CANCEL_PREFIXES)
        controls, payload_tail = _parse_keyvals(payload)
        run_id = controls.get("run_id", "").strip()
        if not run_id and payload_tail:
            token = payload_tail.split(" ", 1)[0].strip()
            run_id = token if _looks_like_run_id(token) else ""
        return DispatchPlan(mode="cancel", chat_scope=chat_scope, run_id=run_id or None, reason="cancel_prefix")

    if any(lowered.startswith(prefix) for prefix in FOLLOWUP_PREFIXES):
        payload = _strip_prefix(normalized, FOLLOWUP_PREFIXES)
        controls, payload_tail = _parse_keyvals(payload)
        run_id = controls.get("run_id", "").strip()
        followup_text = controls.get("text", "").strip()

        tail = payload_tail
        if tail and not run_id:
            token, *rest = tail.split(" ", 1)
            if _looks_like_run_id(token):
                run_id = token.strip()
                tail = rest[0].strip() if rest else ""
        if not followup_text:
            followup_text = tail.strip()

        return DispatchPlan(
            mode="followup",
            chat_scope=chat_scope,
            run_id=run_id or None,
            followup_text=followup_text or None,
            reason="followup_prefix",
        )

    if any(lowered.startswith(prefix) for prefix in CHAT_PREFIXES):
        return DispatchPlan(mode="chat", chat_scope=chat_scope, reason="chat_prefix")

    if not any(lowered.startswith(prefix) for prefix in RUN_PREFIXES):
        return DispatchPlan(mode="chat", chat_scope=chat_scope, reason="no_run_prefix")

    payload = _strip_prefix(normalized, RUN_PREFIXES)
    controls, payload_tail = _parse_keyvals(payload)
    known_ids = _known_task_ids()
    explicit_task_id = controls.get("task_id", "").strip()
    if explicit_task_id and explicit_task_id in known_ids:
        task_id = explicit_task_id
        domain = controls.get("domain", KNOWN_TASK_DOMAIN.get(task_id, default_domain)).strip() or default_domain
        task_text = controls.get("task", "").strip() or payload_tail
    else:
        detected_task_id = _extract_known_task_id(payload_tail, known_ids)
        if detected_task_id:
            task_id = detected_task_id
            domain = controls.get("domain", KNOWN_TASK_DOMAIN.get(task_id, default_domain)).strip() or default_domain
            task_text = controls.get("task", "").strip() or payload_tail
        else:
            free_text = controls.get("task", "").strip() or payload_tail
            if not free_text:
                free_text = "Run a meaningful CLI task and provide verification evidence."
            domain = controls.get("domain", "").strip() or _infer_domain(free_text, fallback=default_domain)
            task_id = _dynamic_task_id(domain=domain, chat_scope=chat_scope, task_text=free_text)
            task_text = free_text

    max_steps_raw = controls.get("steps", "").strip()
    try:
        max_steps = max(2, min(20, int(max_steps_raw))) if max_steps_raw else 6
    except ValueError:
        max_steps = 6

    # v1.5 profile is intentionally locked to a single model/backend so
    # real-world Telegram data stays consistent with benchmark policy.
    if USE_V15_PROFILE:
        model_executor = DEFAULT_EXECUTOR_MODEL
        llm_backend = DEFAULT_LLM_BACKEND
    else:
        model_executor = controls.get("model", "").strip() or DEFAULT_EXECUTOR_MODEL
        llm_backend = controls.get("backend", "").strip() or DEFAULT_LLM_BACKEND
    run_id = controls.get("run_id", "").strip() or None
    learn_value = controls.get("learn", controls.get("persist", "")).strip().lower()
    posttask_learn = not (learn_value in {"off", "false", "0", "no"})
    return DispatchPlan(
        mode="run",
        chat_scope=chat_scope,
        domain=domain,
        task_id=task_id,
        task_text=task_text,
        run_id=run_id,
        max_steps=max_steps,
        model_executor=model_executor,
        llm_backend=llm_backend,
        posttask_learn=posttask_learn,
        reason="run_prefix",
    )


def _run_task(plan: DispatchPlan, *, dry_run: bool = False) -> dict[str, Any]:
    assert plan.mode == "run"
    assert plan.domain is not None
    assert plan.task_id is not None
    assert plan.task_text is not None
    if not RUNNER.exists():
        return {
            "ok": False,
            "error": f"runner not found: {RUNNER}",
            "dispatch_profile": DISPATCH_PROFILE,
        }

    if plan.task_id.startswith("openclaw_dynamic_") and not dry_run:
        _ensure_dynamic_task_dir(
            task_id=plan.task_id,
            domain=plan.domain,
            task_text=plan.task_text,
            chat_scope=plan.chat_scope,
        )

    # Reserve IDs before execution so transport layers can immediately track
    # this run with deterministic identifiers.
    run_id = plan.run_id or run_service.generate_run_id()
    session_id = run_service.allocate_session_id()
    cmd = [
        "python3",
        str(RUNNER),
        "--task-id",
        plan.task_id,
        "--task",
        plan.task_text,
        "--domain",
        plan.domain,
        "--session",
        str(session_id),
        "--max-steps",
        str(plan.max_steps),
        "--llm-backend",
        plan.llm_backend,
        "--model-executor",
        plan.model_executor,
        "--run-id",
        run_id,
    ]
    # Legacy runner expects these explicit control flags. v1.5 runner is
    # already hard-locked internally and keeps argv minimal on purpose.
    if not USE_V15_PROFILE:
        cmd.extend(
            [
                "--posttask-mode",
                "direct",
                "--contract-gap-retry",
                "--contract-gap-retry-steps",
                "1",
                "--structured-lessons-required",
            ]
        )
    if not plan.posttask_learn:
        # Allow safe live testing without mutating shared lesson stores.
        cmd.append("--no-posttask-learn")

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "command": cmd,
            "task_id": plan.task_id,
            "domain": plan.domain,
            "session_id": session_id,
            "run_id": run_id,
            "dispatch_profile": DISPATCH_PROFILE,
            "runner": str(RUNNER),
        }

    proc = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True)
    session_dir = SESSIONS_ROOT / f"session-{session_id:03d}"
    metrics_path = session_dir / "metrics.json"
    metrics: dict[str, Any] = {}
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            metrics = {}

    ok = proc.returncode == 0
    run_row = run_service.get_run(run_id)
    return {
        "ok": ok,
        "dispatch_profile": DISPATCH_PROFILE,
        "runner": str(RUNNER),
        "run_id": run_id,
        "task_id": plan.task_id,
        "domain": plan.domain,
        "session_id": session_id,
        "session_dir": str(session_dir),
        "returncode": proc.returncode,
        "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-16:]),
        "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-16:]),
        "metrics": metrics,
        "run_status": run_row.status if run_row else None,
        "run": run_row.to_dict() if run_row else None,
        "run_followup_count": len(run_row.followups or []) if run_row else 0,
    }


def _status_payload(
    *,
    chat_scope: str,
    run_id: str | None = None,
    include_progress: bool = False,
    progress_limit: int = 8,
) -> dict[str, Any]:
    lesson_count = 0
    scoped_count = 0
    if LESSONS_V2_PATH.exists():
        for line in LESSONS_V2_PATH.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            lesson_count += 1
            task_id = str(row.get("task_id", ""))
            if chat_scope in task_id:
                scoped_count += 1

    recent_metrics: dict[str, Any] = {}
    session_dirs = sorted(
        [p for p in SESSIONS_ROOT.glob("session-*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for session_dir in session_dirs:
        metrics_path = session_dir / "metrics.json"
        if not metrics_path.exists():
            continue
        try:
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        recent_metrics = payload
        break

    active_runs = [row.to_dict() for row in run_service.list_active()]
    run_row = run_service.get_run(run_id) if run_id else None
    lifecycle_events: list[dict[str, Any]] = []
    if include_progress and run_id:
        lifecycle_events = _latest_lifecycle_events(run_id=run_id, limit=progress_limit)

    return {
        "ok": True,
        "mode": "status",
        "dispatch_profile": DISPATCH_PROFILE,
        "runner": str(RUNNER),
        "chat_scope": chat_scope,
        "run_id": run_id,
        "run": run_row.to_dict() if run_row else None,
        "active_runs": active_runs,
        "progress_mode": bool(include_progress),
        "progress_limit": int(progress_limit),
        "lifecycle_events": lifecycle_events,
        "lessons_total": lesson_count,
        "lessons_scoped": scoped_count,
        "latest_session": {
            "task_id": recent_metrics.get("task_id"),
            "domain": recent_metrics.get("domain"),
            "eval_passed": recent_metrics.get("eval_passed"),
            "eval_score": recent_metrics.get("eval_score"),
            "lesson_activations": recent_metrics.get("lesson_activations"),
            "v2_retrieval_help_ratio": recent_metrics.get("v2_retrieval_help_ratio"),
        },
    }


def _chat_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "chat",
        "reply": (
            "Chat mode. No learning run executed.\n"
            "Use /run <task> to trigger Cortex learning loop.\n"
            "Use /learn-status for learning metrics, /run-status run_id=<id> progress=on for progress,\n"
            "and /followup run_id=<id> <text> to append steering."
        ),
    }


def _cancel_payload(*, run_id: str | None) -> tuple[dict[str, Any], int]:
    rid = str(run_id or "").strip()
    if not rid:
        return {
            "ok": False,
            "mode": "cancel",
            "error": "Missing run_id. Usage: /cancel run_id=<run_id>",
        }, 1
    row = run_service.cancel_run(rid, reason="transport_requested")
    if row is None:
        return {"ok": False, "mode": "cancel", "run_id": rid, "error": "run_id not found"}, 1
    return {"ok": True, "mode": "cancel", "run_id": rid, "run": row.to_dict()}, 0


def _followup_payload(
    *,
    run_id: str | None,
    followup_text: str | None,
    chat_scope: str,
) -> tuple[dict[str, Any], int]:
    rid = str(run_id or "").strip()
    text = str(followup_text or "").strip()
    if not rid:
        return {
            "ok": False,
            "mode": "followup",
            "error": "Missing run_id. Usage: /followup run_id=<run_id> <text>",
        }, 1
    if not text:
        return {
            "ok": False,
            "mode": "followup",
            "run_id": rid,
            "error": "Missing follow-up text. Usage: /followup run_id=<run_id> <text>",
        }, 1

    append_fn = getattr(run_service, "append_followup", None)
    if not callable(append_fn):
        return {
            "ok": False,
            "mode": "followup",
            "run_id": rid,
            "error": "run_service.append_followup is unavailable in this build.",
        }, 1

    # Follow-up is stored as run-linked steering input with source metadata so
    # future analysis can attribute behavior changes to transport-level guidance.
    try:
        raw_result = append_fn(
            rid,
            text,
            source=f"transport:{chat_scope}",
            ts=time.time(),
        )
    except Exception as exc:
        return {
            "ok": False,
            "mode": "followup",
            "run_id": rid,
            "error": f"append_followup failed: {exc}",
        }, 1

    if raw_result is None:
        return {
            "ok": False,
            "mode": "followup",
            "run_id": rid,
            "error": "run_id not found",
        }, 1

    if hasattr(raw_result, "to_dict"):
        result_payload = raw_result.to_dict()  # RunRecord
        accepted = True
    elif isinstance(raw_result, dict):
        result_payload = dict(raw_result)
        accepted = bool(result_payload.get("accepted", True))
    else:
        accepted = bool(raw_result)
        result_payload = {"accepted": accepted}

    payload = {
        "ok": accepted,
        "mode": "followup",
        "run_id": rid,
        "accepted": accepted,
        "result": result_payload,
    }
    if not accepted:
        payload["error"] = "Follow-up was rejected."
    return payload, (0 if accepted else 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Dispatch Telegram/OpenClaw text into Cortex learning runs.")
    ap.add_argument("--text", required=True, help="Raw inbound user message text.")
    ap.add_argument("--chat-id", default="global", help="Chat/user scope for dynamic task ids.")
    ap.add_argument("--default-domain", default="shell", choices=["sqlite", "gridtool", "fluxtool", "artic", "shell"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    chat_scope = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(args.chat_id).strip()) or "global"
    plan = _build_plan(str(args.text), chat_scope=chat_scope, default_domain=args.default_domain)

    if plan.mode == "chat":
        _print_json(_chat_payload())
        return 0
    if plan.mode == "status":
        _print_json(
            _status_payload(
                chat_scope=chat_scope,
                run_id=plan.run_id,
                include_progress=plan.progress,
                progress_limit=plan.progress_limit,
            )
        )
        return 0
    if plan.mode == "cancel":
        payload, rc = _cancel_payload(run_id=plan.run_id)
        _print_json(payload)
        return rc
    if plan.mode == "followup":
        payload, rc = _followup_payload(
            run_id=plan.run_id,
            followup_text=plan.followup_text,
            chat_scope=chat_scope,
        )
        _print_json(payload)
        return rc

    result = _run_task(plan, dry_run=bool(args.dry_run))
    _print_json({"mode": "run", "plan": plan.__dict__, "result": result})
    return 0 if bool(result.get("ok", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
