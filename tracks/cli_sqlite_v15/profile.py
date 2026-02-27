"""Shared v1.5 locked runtime policy.

The goal is to keep all wrappers aligned to one immutable policy surface
while we iterate on the v1.5 track.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class V15Policy:
    llm_backend: str = "openai"
    model_executor: str = "gpt-5-nano"
    model_judge: str = "gpt-5-nano"
    model_critic: str = "gpt-5-nano"
    learning_mode: str = "strict"
    self_edit_mode: bool = False
    benchmark_deterministic: bool = True
    benchmark_promoted_only: bool = False
    structured_lessons_required: bool = True
    contract_gap_retry: bool = True
    contract_gap_retry_steps: int = 1
    contract_gap_deterministic_recipes: bool = True
    doc_retrieval: str = "auto"
    doc_mode: str = "lossy"
    judge_diagnostic: bool = True
    posttask_mode: str = "direct"
    watchdog_allow_posttask_in_safe_mode: bool = True


V15_LOCKED = V15Policy()
ROOT_DIR = Path(__file__).resolve().parents[2]
BASE_RUNNER = ROOT_DIR / "tracks" / "cli_sqlite" / "scripts" / "run_cli_agent.py"

