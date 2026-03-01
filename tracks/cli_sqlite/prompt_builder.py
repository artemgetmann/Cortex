from __future__ import annotations

"""Prompt construction helpers for CLI sqlite runtime.

This module intentionally stays small and deterministic so prompt-shape
experiments can be run without editing the large runtime orchestrator.
"""

EXECUTOR_PROMPT_MODES = ("full", "minimal")
DEFAULT_EXECUTOR_PROMPT_MODE = "full"


def normalize_executor_prompt_mode(mode: str | None) -> str:
    """Normalize prompt mode with a stable fallback.

    We keep a strict allow-list to avoid accidental typo-modes that silently
    change runtime behavior during benchmarks.
    """

    normalized = str(mode or "").strip().lower()
    if normalized in EXECUTOR_PROMPT_MODES:
        return normalized
    return DEFAULT_EXECUTOR_PROMPT_MODE


def build_executor_system_prompt(
    *,
    task_id: str,
    skills_text: str,
    lessons_text: str,
    domain_fragment: str,
    executor_prompt_mode: str = DEFAULT_EXECUTOR_PROMPT_MODE,
) -> str:
    """Build executor system prompt for the selected prompt mode.

    `full` mode keeps domain-specific framing (legacy behavior).
    `minimal` mode strips domain phrasing and keeps generic tool discipline.
    """

    prompt_mode = normalize_executor_prompt_mode(executor_prompt_mode)
    if prompt_mode == "minimal":
        return (
            "You are controlling a deterministic CLI task environment.\n"
            "Use provided tools only. Verify concrete evidence before stopping.\n"
            f"- Active task_id: {task_id}\n\n"
            "Skills metadata:\n"
            f"{skills_text}\n\n"
            "Prior lessons:\n"
            f"{lessons_text}\n"
        )
    return (
        f"{domain_fragment}"
        f"- Active task_id: {task_id}\n\n"
        "Skills metadata:\n"
        f"{skills_text}\n\n"
        "Prior lessons:\n"
        f"{lessons_text}\n"
    )

