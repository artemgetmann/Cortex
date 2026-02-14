"""Tool alias system for opaque-tool experiments.

When opaque=True, the agent sees generic tool names (dispatch, probe, catalog)
instead of descriptive ones (run_sqlite, read_skill, show_fixture).  This forces
the agent to actually read skill docs to understand what each tool does.

Event logging always uses canonical names so the evaluator works unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolAlias:
    opaque_name: str
    canonical_name: str
    opaque_description: str
    canonical_description: str


STANDARD_ALIASES: dict[str, ToolAlias] = {
    "run_sqlite": ToolAlias(
        opaque_name="dispatch",
        canonical_name="run_sqlite",
        opaque_description="Execute a command against the workspace. Consult skill docs for parameter semantics.",
        canonical_description="Execute SQL against task-local sqlite database. No shell escapes. Dot-commands are restricted.",
    ),
    "read_skill": ToolAlias(
        opaque_name="probe",
        canonical_name="read_skill",
        opaque_description="Look up a reference document by ref key.",
        canonical_description="Read full contents of a skill document by stable skill_ref.",
    ),
    "show_fixture": ToolAlias(
        opaque_name="catalog",
        canonical_name="show_fixture",
        opaque_description="Retrieve a named data artifact.",
        canonical_description="Read task fixture/bootstrap file by stable path_ref.",
    ),
}


def build_alias_map(opaque: bool) -> dict[str, str]:
    """Return {api_name: canonical_name} mapping.

    When opaque=True, api_name is the opaque name (dispatch, probe, catalog).
    When opaque=False, api_name == canonical_name.
    """
    result: dict[str, str] = {}
    for canonical, alias in STANDARD_ALIASES.items():
        api_name = alias.opaque_name if opaque else canonical
        result[api_name] = canonical
    return result


def get_tool_api_name(canonical: str, opaque: bool) -> str:
    """Return the tool name that the API will see."""
    alias = STANDARD_ALIASES.get(canonical)
    if alias is None:
        return canonical
    return alias.opaque_name if opaque else canonical


def get_tool_description(canonical: str, opaque: bool) -> str:
    """Return the tool description for the given mode."""
    alias = STANDARD_ALIASES.get(canonical)
    if alias is None:
        return ""
    return alias.opaque_description if opaque else alias.canonical_description
