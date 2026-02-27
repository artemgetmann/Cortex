from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = ROOT / "integrations" / "openclaw_agi_dispatch.py"


def _run_dispatch(*, text: str, chat_id: str = "tg-1", dry_run: bool = True) -> dict:
    cmd = ["python3", str(DISPATCHER), "--text", text, "--chat-id", chat_id]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def test_dispatch_chat_mode_default() -> None:
    payload = _run_dispatch(text="hey what is up")
    assert payload["mode"] == "chat"
    assert payload["reply"].startswith("Chat mode.")


def test_dispatch_known_task_from_run_command() -> None:
    payload = _run_dispatch(text="/run shell_git_transfer_hotfix")
    plan = payload["plan"]
    result = payload["result"]
    assert payload["mode"] == "run"
    assert plan["attempts"] == 1
    assert plan["task_id"] == "shell_git_transfer_hotfix"
    assert plan["domain"] == "shell"
    assert result["dry_run"] is True
    assert result["ok"] is True


def test_dispatch_dynamic_task_id_is_stable_per_chat_scope() -> None:
    text = "/run domain=shell build me a deterministic cli summary flow"
    first = _run_dispatch(text=text, chat_id="tg-123")
    second = _run_dispatch(text=text, chat_id="tg-123")
    third = _run_dispatch(text=text, chat_id="tg-456")
    assert first["plan"]["task_id"].startswith("openclaw_dynamic_")
    assert first["plan"]["task_id"] == second["plan"]["task_id"]
    assert first["plan"]["task_id"] != third["plan"]["task_id"]


def test_dispatch_status_mode() -> None:
    payload = _run_dispatch(text="/learn-status")
    assert payload["mode"] == "status"
    assert "lessons_total" in payload
    assert "error_count" in payload["latest_session"]


def test_dispatch_learn_off_adds_no_posttask_flag() -> None:
    payload = _run_dispatch(text="/run domain=shell learn=off shell_git_transfer_hotfix")
    cmd = payload["result"]["command"]
    assert "--no-posttask-learn" in cmd


@pytest.mark.parametrize(
    "phrase",
    [
        "use only 5 steps",
        "in 5 steps",
        "steps 5",
    ],
)
def test_dispatch_natural_steps_phrase_sets_max_steps(phrase: str) -> None:
    payload = _run_dispatch(text=f"/run domain=shell {phrase} shell_git_transfer_hotfix")
    assert payload["plan"]["max_steps"] == 5


def test_dispatch_natural_control_phrase_not_used_as_task_text_for_known_task() -> None:
    payload = _run_dispatch(text="/run domain=sqlite task_id=incremental_reconcile use only 5 steps")
    plan = payload["plan"]
    assert plan["task_id"] == "incremental_reconcile"
    # Control phrase should not become task body. Known task should run by ID.
    assert plan["task_text"] is None


@pytest.mark.parametrize(
    "phrase",
    [
        "learn off",
        "learning off",
        "without learning",
        "do not learn",
        "don't learn",
        "no learning",
    ],
)
def test_dispatch_natural_learning_off_phrase_adds_no_posttask_flag(phrase: str) -> None:
    payload = _run_dispatch(text=f"/run domain=shell {phrase} shell_git_transfer_hotfix")
    cmd = payload["result"]["command"]
    assert "--no-posttask-learn" in cmd


def test_dispatch_learnrun_attempts_three_emits_attempt_results() -> None:
    payload = _run_dispatch(text="/learnrun domain=shell attempts=3 shell_git_transfer_hotfix")
    result = payload["result"]
    assert payload["mode"] == "run"
    assert payload["plan"]["attempts"] == 3
    assert result["attempts_requested"] == 3
    assert len(result["attempt_results"]) == 3
    assert len({item["run_id"] for item in result["attempt_results"]}) == 3
    assert len({item["session_id"] for item in result["attempt_results"]}) == 3
    assert result["run_id"] == result["attempt_results"][-1]["run_id"]


def test_dispatch_run_prefix_defaults_to_single_attempt() -> None:
    payload = _run_dispatch(text="/run domain=shell shell_git_transfer_hotfix")
    assert payload["plan"]["attempts"] == 1
    assert "attempts_requested" not in payload["result"]
    assert "attempt_results" not in payload["result"]


def test_dispatch_known_task_without_explicit_text_omits_task_override_flag() -> None:
    payload = _run_dispatch(text="/run domain=sqlite task_id=incremental_reconcile")
    cmd = payload["result"]["command"]
    assert "--task-id" in cmd
    assert "incremental_reconcile" in cmd
    assert "--task" not in cmd


def test_dispatch_plain_natural_task_routes_to_dynamic_run_plan() -> None:
    payload = _run_dispatch(
        text="Import a CSV of sales events into SQLite. Deduplicate by event_id and return category totals."
    )
    assert payload["mode"] == "run"
    assert payload["plan"]["reason"] == "auto_task_intent"
    assert payload["plan"]["attempts"] == 3
    assert payload["plan"]["task_id"].startswith("openclaw_dynamic_")
    assert payload["plan"]["domain"] == "sqlite"


def test_dispatch_plain_non_task_text_stays_chat_mode() -> None:
    payload = _run_dispatch(text="hey what is up")
    assert payload["mode"] == "chat"
