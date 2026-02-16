from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from tracks.cli_sqlite import agent_cli
from tracks.cli_sqlite.domain_adapter import DomainWorkspace
from tracks.cli_sqlite.domains import artic_adapter
from tracks.cli_sqlite.domains.artic_adapter import ArticAdapter
from tracks.cli_sqlite.scripts import memory_timeline_demo
from tracks.cli_sqlite.scripts import run_cli_agent as run_cli_agent_script


class _FakeHeaders:
    def get_content_charset(self) -> str:
        return "utf-8"


class _FakeResponse:
    def __init__(self, *, status: int, payload: dict[str, Any]) -> None:
        self._status = status
        self._raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.headers = _FakeHeaders()

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._raw


def _workspace(tmp_path: Path) -> DomainWorkspace:
    task_dir = tmp_path / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_dir.joinpath("task.md").write_text("artic test", encoding="utf-8")
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    return DomainWorkspace(
        task_id="artic_test",
        task_dir=task_dir,
        work_dir=work_dir,
        fixture_paths={"task.md": task_dir / "task.md"},
    )


def test_artic_execute_success_returns_compact_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = ArticAdapter()
    workspace = _workspace(tmp_path)

    def _fake_urlopen(request, timeout: float):
        assert request.get_method() == "GET"
        assert "https://api.artic.edu/api/v1/artworks/search" in request.full_url
        assert "q=cats" in request.full_url
        assert "limit=2" in request.full_url
        assert timeout == 15.0
        return _FakeResponse(
            status=200,
            payload={"data": [{"id": 7, "title": "Cat and Bird"}], "pagination": {"total": 1}},
        )

    monkeypatch.setattr(artic_adapter, "urlopen", _fake_urlopen)

    result = adapter.execute(
        "run_artic",
        {"method": "GET", "path": "/artworks/search", "query": {"q": "cats", "limit": 2}},
        workspace,
    )

    assert result.error is None
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["status"] == 200
    assert payload["request"]["method"] == "GET"
    assert payload["request"]["path"] == "/artworks/search"
    assert payload["result"]["data"][0]["id"] == 7


def test_artic_execute_rejects_non_get_method(tmp_path: Path) -> None:
    adapter = ArticAdapter()
    workspace = _workspace(tmp_path)
    result = adapter.execute("run_artic", {"method": "POST", "path": "/artworks/search", "query": {}}, workspace)
    assert result.error is not None
    assert "only supports GET" in result.error


def test_artic_execute_surfaces_http_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = ArticAdapter()
    workspace = _workspace(tmp_path)

    def _raise_http_error(request, timeout: float):
        del request, timeout
        raise HTTPError(
            url="https://api.artic.edu/api/v1/artworks/0",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b'{"detail":"missing"}'),
        )

    monkeypatch.setattr(artic_adapter, "urlopen", _raise_http_error)
    result = adapter.execute("run_artic", {"method": "GET", "path": "/artworks/0", "query": {}}, workspace)
    assert result.error is not None
    assert "HTTP 404" in result.error
    assert "/artworks/0" in result.error


def test_artic_execute_surfaces_network_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = ArticAdapter()
    workspace = _workspace(tmp_path)

    def _raise_url_error(request, timeout: float):
        del request, timeout
        raise URLError("temporary dns failure")

    monkeypatch.setattr(artic_adapter, "urlopen", _raise_url_error)
    result = adapter.execute("run_artic", {"method": "GET", "path": "/artworks/search", "query": {}}, workspace)
    assert result.error is not None
    assert "network error" in result.error
    assert "/artworks/search" in result.error


def test_artic_execute_clips_large_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = ArticAdapter()
    workspace = _workspace(tmp_path)
    huge_data = [{"id": i, "title": f"title-{i}", "artist_title": "x" * 80} for i in range(500)]

    def _fake_urlopen(request, timeout: float):
        del request, timeout
        return _FakeResponse(status=200, payload={"data": huge_data, "pagination": {"total": len(huge_data)}})

    monkeypatch.setattr(artic_adapter, "urlopen", _fake_urlopen)
    result = adapter.execute("run_artic", {"method": "GET", "path": "/artworks/search", "query": {"q": "x"}}, workspace)
    assert result.error is None
    payload = json.loads(result.output)
    assert payload["truncated"] is True
    assert "result_excerpt" in payload


def test_artic_prepare_workspace_includes_task_markdown(tmp_path: Path) -> None:
    adapter = ArticAdapter()
    task_dir = tmp_path / "tasks" / "artic_search_basic"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_dir.joinpath("task.md").write_text("demo", encoding="utf-8")
    task_dir.joinpath("CONTRACT.json").write_text("{}", encoding="utf-8")
    workspace = adapter.prepare_workspace(task_dir, tmp_path / "work")
    assert "task.md" in workspace.fixture_paths
    assert "CONTRACT.json" not in workspace.fixture_paths


def test_agent_cli_resolves_artic_adapter() -> None:
    resolved = agent_cli._resolve_adapter("artic")
    assert resolved.name == "artic"
    assert resolved.executor_tool_name == "run_artic"


def test_run_cli_agent_script_accepts_artic_domain(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
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
            "artic_search_basic",
            "--session",
            "31001",
            "--domain",
            "artic",
        ],
    )
    rc = run_cli_agent_script.main()
    assert rc == 0
    assert captured["domain"] == "artic"
    capsys.readouterr()


def test_memory_timeline_treats_artic_as_executor_tool() -> None:
    assert memory_timeline_demo._is_executor_tool("run_artic") is True

