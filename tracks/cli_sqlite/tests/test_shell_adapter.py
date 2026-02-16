from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tracks.cli_sqlite import agent_cli
from tracks.cli_sqlite.domain_adapter import DomainWorkspace
from tracks.cli_sqlite.domains import shell_adapter
from tracks.cli_sqlite.domains.shell_adapter import ShellAdapter
from tracks.cli_sqlite.scripts import memory_timeline_demo
from tracks.cli_sqlite.scripts import run_cli_agent as run_cli_agent_script


def _workspace(tmp_path: Path) -> DomainWorkspace:
    task_dir = tmp_path / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_dir.joinpath("task.md").write_text("shell test", encoding="utf-8")
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    return DomainWorkspace(
        task_id="shell_test",
        task_dir=task_dir,
        work_dir=work_dir,
        fixture_paths={"task.md": task_dir / "task.md"},
    )


def test_shell_execute_success_returns_json_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = ShellAdapter()
    workspace = _workspace(tmp_path)

    def _fake_run(*args, **kwargs):
        del args, kwargs
        return subprocess.CompletedProcess(
            args=["/bin/bash", "-lc", "echo ok"],
            returncode=0,
            stdout="ok\n",
            stderr="",
        )

    monkeypatch.setattr(shell_adapter.subprocess, "run", _fake_run)
    result = adapter.execute("run_bash", {"command": "echo ok"}, workspace)
    assert result.error is None
    payload = json.loads(result.output)
    assert payload["returncode"] == 0
    assert payload["stdout"] == "ok"


def test_shell_execute_failure_surfaces_exit_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = ShellAdapter()
    workspace = _workspace(tmp_path)

    def _fake_run(*args, **kwargs):
        del args, kwargs
        return subprocess.CompletedProcess(
            args=["/bin/bash", "-lc", "python3 -c 'import missing'"],
            returncode=1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'missing'",
        )

    monkeypatch.setattr(shell_adapter.subprocess, "run", _fake_run)
    result = adapter.execute("run_bash", {"command": "python3 -c 'import missing'"}, workspace)
    assert result.error is not None
    assert "exited with code 1" in result.error
    assert "ModuleNotFoundError" in result.error


def test_shell_prepare_workspace_copies_fixture_files(tmp_path: Path) -> None:
    adapter = ShellAdapter()
    task_dir = tmp_path / "tasks" / "shell_excel_build_report"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_dir.joinpath("task.md").write_text("demo", encoding="utf-8")
    task_dir.joinpath("fixture.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    workspace = adapter.prepare_workspace(task_dir, tmp_path / "work")
    assert "task.md" in workspace.fixture_paths
    assert "fixture.csv" in workspace.fixture_paths
    assert (workspace.work_dir / "fixture.csv").exists()


def test_agent_cli_resolves_shell_adapter() -> None:
    resolved = agent_cli._resolve_adapter("shell")
    assert resolved.name == "shell"
    assert resolved.executor_tool_name == "run_bash"


def test_run_cli_agent_script_accepts_shell_domain(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(run_cli_agent_script, "load_config", lambda: object())
    monkeypatch.setattr(
        run_cli_agent_script,
        "run_cli_agent",
        lambda **kwargs: captured.update(kwargs) or SimpleNamespace(metrics={}),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_cli_agent.py",
            "--task-id",
            "shell_excel_build_report",
            "--session",
            "43001",
            "--domain",
            "shell",
        ],
    )
    rc = run_cli_agent_script.main()
    assert rc == 0
    assert captured["domain"] == "shell"
    capsys.readouterr()


def test_memory_timeline_treats_shell_as_executor_tool() -> None:
    assert memory_timeline_demo._is_executor_tool("run_bash") is True
