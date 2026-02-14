"""Domain adapter protocol for pluggable CLI tool domains."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolResult:
    """Unified tool result used across all domains."""
    output: str = ""
    error: str | None = None

    def is_error(self) -> bool:
        return bool(self.error)


@dataclass(frozen=True)
class DomainWorkspace:
    """Domain-agnostic workspace for a single task run."""
    task_id: str
    task_dir: Path
    work_dir: Path
    fixture_paths: dict[str, Path]


@runtime_checkable
class DomainAdapter(Protocol):
    """Protocol that every domain adapter must satisfy."""

    @property
    def name(self) -> str:
        """Domain name, e.g. 'sqlite', 'gridtool'."""
        ...

    @property
    def executor_tool_name(self) -> str:
        """Canonical tool name for the executor, e.g. 'run_sqlite', 'run_gridtool'."""
        ...

    def tool_defs(self, fixture_refs: list[str], *, opaque: bool) -> list[dict[str, Any]]:
        """Return API tool definitions list (includes domain executor + read_skill + show_fixture)."""
        ...

    def execute(self, tool_name: str, tool_input: dict[str, Any], workspace: DomainWorkspace) -> ToolResult:
        """Execute a domain-specific tool call. Only handles the executor tool, not read_skill/show_fixture."""
        ...

    def prepare_workspace(self, task_dir: Path, work_dir: Path) -> DomainWorkspace:
        """Set up task workspace (create DB, copy fixtures, etc)."""
        ...

    def capture_final_state(self, workspace: DomainWorkspace) -> str:
        """Capture final state for LLM judge (DB dump, file output, etc)."""
        ...

    def system_prompt_fragment(self) -> str:
        """Domain-specific instructions for the system prompt."""
        ...

    def quality_keywords(self) -> re.Pattern[str]:
        """Domain-specific keywords for lesson quality scoring."""
        ...

    def build_alias_map(self, *, opaque: bool) -> dict[str, str]:
        """Return {api_name: canonical_name} for all tools including domain-specific ones."""
        ...
