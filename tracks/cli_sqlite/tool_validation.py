"""Tool-agnostic input validation helpers for CLI agent tools."""
from __future__ import annotations

from typing import Any


def build_tool_schema_map(tool_defs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Build a {tool_name: input_schema} map from the API tool list.

    We only preserve schemas that are explicit dicts. This keeps validation
    shallow and portable across tool adapters without imposing strict typing.
    """
    schema_map: dict[str, dict[str, Any]] = {}
    for tool in tool_defs:
        name = str(tool.get("name", "")).strip()
        schema = tool.get("input_schema")
        if name and isinstance(schema, dict):
            schema_map[name] = schema
    return schema_map


def validate_tool_input(
    *,
    tool_name: str,
    tool_input: Any,
    schema: dict[str, Any] | None,
) -> str | None:
    """
    Perform a structural validation pass against a tool's input schema.

    This intentionally avoids semantic parsing (no bash/sql validation). The goal
    is to prevent obviously malformed calls (empty strings, missing keys, wrong
    primitive types) across all tools in a domain-agnostic way.
    """
    if not schema:
        return None

    if schema.get("type") == "object" and not isinstance(tool_input, dict):
        return f"{tool_name} expects object input, got {type(tool_input).__name__}"

    if not isinstance(tool_input, dict):
        return f"{tool_name} expects dict input, got {type(tool_input).__name__}"

    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = schema.get("required") if isinstance(schema.get("required"), list) else []

    missing = [key for key in required if key not in tool_input]
    if missing:
        return f"{tool_name} missing required keys: {sorted(missing)}"

    if schema.get("additionalProperties") is False:
        unknown = [key for key in tool_input if key not in properties]
        if unknown:
            return f"{tool_name} input had unknown keys: {sorted(unknown)}"

    for key, spec in properties.items():
        if key not in tool_input:
            continue
        expected = spec.get("type") if isinstance(spec, dict) else None
        value = tool_input.get(key)
        if expected == "string":
            if not isinstance(value, str) or not value.strip():
                return f"{tool_name} requires non-empty string {key}, got {value!r}"
        elif expected == "object":
            if not isinstance(value, dict):
                return f"{tool_name} requires object {key}, got {value!r}"
        elif expected == "array":
            if not isinstance(value, list):
                return f"{tool_name} requires array {key}, got {value!r}"

    return None
