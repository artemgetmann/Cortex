from __future__ import annotations

from tracks.cli_sqlite.prompt_builder import (
    build_executor_system_prompt,
    normalize_executor_prompt_mode,
)


def test_normalize_executor_prompt_mode_falls_back_to_full() -> None:
    assert normalize_executor_prompt_mode(None) == "full"
    assert normalize_executor_prompt_mode("  weird-mode ") == "full"


def test_build_executor_system_prompt_minimal_omits_domain_fragment() -> None:
    prompt = build_executor_system_prompt(
        task_id="incremental_reconcile",
        skills_text="skill_a",
        lessons_text="lesson_a",
        domain_fragment="DOMAIN_FRAGMENT\n",
        executor_prompt_mode="minimal",
    )
    assert "DOMAIN_FRAGMENT" not in prompt
    assert "deterministic CLI task environment" in prompt
    assert "incremental_reconcile" in prompt


def test_build_executor_system_prompt_full_keeps_domain_fragment() -> None:
    prompt = build_executor_system_prompt(
        task_id="incremental_reconcile",
        skills_text="skill_a",
        lessons_text="lesson_a",
        domain_fragment="DOMAIN_FRAGMENT\n",
        executor_prompt_mode="full",
    )
    assert "DOMAIN_FRAGMENT" in prompt
    assert "skill_a" in prompt
    assert "lesson_a" in prompt

