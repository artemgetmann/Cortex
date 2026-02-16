from __future__ import annotations

from tracks.cli_sqlite.domains.shell_adapter import ShellAdapter
from tracks.cli_sqlite.tool_validation import build_tool_schema_map, validate_tool_input


def test_tool_validation_rejects_missing_required_keys() -> None:
    adapter = ShellAdapter()
    schema_map = build_tool_schema_map(adapter.tool_defs([], opaque=False))
    schema = schema_map["run_bash"]
    error = validate_tool_input(tool_name="run_bash", tool_input={}, schema=schema)
    assert error is not None
    assert "missing required keys" in error


def test_tool_validation_rejects_empty_string_inputs() -> None:
    adapter = ShellAdapter()
    schema_map = build_tool_schema_map(adapter.tool_defs([], opaque=False))
    schema = schema_map["run_bash"]
    error = validate_tool_input(tool_name="run_bash", tool_input={"command": "   "}, schema=schema)
    assert error is not None
    assert "non-empty string command" in error


def test_tool_validation_rejects_unknown_keys_when_disallowed() -> None:
    adapter = ShellAdapter()
    schema_map = build_tool_schema_map(adapter.tool_defs([], opaque=False))
    schema = schema_map["run_bash"]
    error = validate_tool_input(
        tool_name="run_bash",
        tool_input={"command": "ls", "extra": "nope"},
        schema=schema,
    )
    assert error is not None
    assert "unknown keys" in error


def test_tool_validation_allows_valid_inputs() -> None:
    adapter = ShellAdapter()
    schema_map = build_tool_schema_map(adapter.tool_defs([], opaque=False))
    schema = schema_map["run_bash"]
    error = validate_tool_input(tool_name="run_bash", tool_input={"command": "ls"}, schema=schema)
    assert error is None
