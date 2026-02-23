from __future__ import annotations

import json
import subprocess
from pathlib import Path


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


def test_dispatch_learn_off_adds_no_posttask_flag() -> None:
    payload = _run_dispatch(text="/run domain=shell learn=off shell_git_transfer_hotfix")
    cmd = payload["result"]["command"]
    assert "--no-posttask-learn" in cmd
