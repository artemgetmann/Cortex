from __future__ import annotations

from types import SimpleNamespace

from tracks.cli_sqlite.lesson_structured_validation import (
    _allowed_action_tools_for_adapter,
    _extract_action_template_from_legacy_lesson,
    _validate_structured_model_lesson,
)


class _FakeAdapter:
    executor_tool_name = "run_bash"

    def build_alias_map(self, *, opaque: bool = False) -> dict[str, str]:
        if opaque:
            return {"tool_exec": "run_bash"}
        return {"run_bash": "run_bash"}


def test_allowed_action_tools_for_adapter_includes_executor_and_helpers() -> None:
    tools = _allowed_action_tools_for_adapter(adapter=_FakeAdapter(), opaque_tools=False)
    assert "run_bash" in tools
    assert "read_skill" in tools
    assert "show_fixture" in tools


def test_extract_action_template_from_legacy_lesson_for_bash() -> None:
    lesson_text = "CORRECT: git init source_repo WHY: create repo first."
    action = _extract_action_template_from_legacy_lesson(
        lesson_text=lesson_text,
        executor_tool_name="run_bash",
    )
    assert action.startswith("run_bash(")
    assert "git init source_repo" in action


def test_validate_structured_model_lesson_accepts_bound_gap_and_action() -> None:
    lesson = SimpleNamespace(
        trigger_gap_signature="missing_required_file|required_file|target_repo/transfer_summary.txt",
        reason_code="missing_required_file",
        gap_type="required_file",
        action_template='run_bash(command="cat > target_repo/transfer_summary.txt")',
        expected_evidence="target_repo/transfer_summary.txt should exist with summary lines",
    )
    unresolved = [
        {
            "gap_signature": "missing_required_file|required_file|target_repo/transfer_summary.txt",
            "reason_code": "missing_required_file",
            "gap_type": "required_file",
            "detail": "target_repo/transfer_summary.txt",
        }
    ]
    ok, reason, payload = _validate_structured_model_lesson(
        lesson=lesson,
        unresolved_gap_rows=unresolved,
        allowed_action_tools={"run_bash"},
    )
    assert ok is True
    assert reason == ""
    assert payload["reason_code"] == "missing_required_file"

