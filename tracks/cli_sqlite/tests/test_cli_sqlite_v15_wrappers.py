from __future__ import annotations

from argparse import Namespace

from tracks.cli_sqlite_v15.profile import V15_LOCKED
from tracks.cli_sqlite_v15.run_cli_agent_v15 import _build_command


def test_v15_profile_locks_openai_nano_policy() -> None:
    assert V15_LOCKED.llm_backend == "openai"
    assert V15_LOCKED.model_executor == "gpt-5-nano"
    assert V15_LOCKED.model_judge == "gpt-5-nano"
    assert V15_LOCKED.learning_mode == "strict"
    assert V15_LOCKED.benchmark_deterministic is True
    assert V15_LOCKED.structured_lessons_required is True
    assert V15_LOCKED.self_edit_mode is False


def test_v15_run_wrapper_ignores_transport_overrides() -> None:
    args = Namespace(
        task_id="shell_git_transfer_hotfix",
        task="",
        domain="shell",
        session=42,
        run_id="run_42",
        max_steps=6,
        no_posttask_learn=False,
        no_require_skill_read=False,
        executor_prompt_mode="",
        verbose=False,
        model_executor="claude-opus-4-6",
        llm_backend="anthropic",
    )
    cmd = _build_command(args)
    text = " ".join(cmd)
    assert "--llm-backend openai" in text
    assert "--model-executor gpt-5-nano" in text
    assert "--model-judge gpt-5-nano" in text
    assert "--no-self-edit-mode" in text
    assert "--benchmark-deterministic" in text
    assert "--structured-lessons-required" in text
    assert "--no-benchmark-promoted-only" in text
    assert "anthropic" not in text
    assert "claude-opus-4-6" not in text


def test_v15_run_wrapper_accepts_experimental_prompt_and_skill_gate_overrides() -> None:
    args = Namespace(
        task_id="shell_git_transfer_hotfix",
        task="",
        domain="shell",
        session=43,
        run_id="run_43",
        max_steps=6,
        no_posttask_learn=False,
        no_require_skill_read=True,
        executor_prompt_mode="minimal",
        verbose=False,
        model_executor="",
        llm_backend="",
    )
    cmd = _build_command(args)
    text = " ".join(cmd)
    assert "--executor-prompt-mode minimal" in text
    assert "--no-require-skill-read" in text
