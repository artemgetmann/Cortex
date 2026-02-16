from __future__ import annotations
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class CortexConfig:
    anthropic_api_key: str

    # "Decider" is used for early gate tests / cheaper loops; "heavy" for dense FL tasks.
    model_decider: str
    model_heavy: str
    # Critic is used by posttask reflection/patch proposal. Default to heavy model for quality.
    model_critic: str
    # Dedicated visual judge for FL end-of-run screenshot adjudication.
    model_visual_judge: str

    # What the model sees as the "screen" coordinate space.
    display_width_px: int
    display_height_px: int

    # Prompt caching beta.
    enable_prompt_caching: bool

    # Computer Use tool + beta flags vary by model family.
    # Haiku/Sonnet often support computer_20250124; Opus supports computer_20251124 (zoom).
    computer_tool_type_decider: str
    computer_tool_type_heavy: str
    computer_use_beta_decider: str
    computer_use_beta_heavy: str
    prompt_caching_beta: str
    token_efficient_tools_beta: str


def _getenv_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return int(raw)


def load_config() -> CortexConfig:
    # Local .env is gitignored; allow it to exist without leaking into git.
    load_dotenv(override=False)

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing (set it in .env).")

    display_width_px = _getenv_int("CORTEX_DISPLAY_WIDTH_PX", 1024)
    display_height_px = _getenv_int("CORTEX_DISPLAY_HEIGHT_PX", 768)

    model_decider = os.getenv("CORTEX_MODEL_DECIDER", "claude-haiku-4-5").strip()
    model_heavy = os.getenv("CORTEX_MODEL_HEAVY", "claude-opus-4-6").strip()
    model_critic = os.getenv("CORTEX_MODEL_CRITIC", model_heavy).strip()
    model_visual_judge = os.getenv("CORTEX_MODEL_VISUAL_JUDGE", model_heavy).strip()

    enable_prompt_caching = os.getenv("CORTEX_ENABLE_PROMPT_CACHING", "1").strip() not in (
        "",
        "0",
        "false",
        "False",
    )

    return CortexConfig(
        anthropic_api_key=api_key,
        model_decider=model_decider,
        model_heavy=model_heavy,
        model_critic=model_critic,
        model_visual_judge=model_visual_judge,
        display_width_px=display_width_px,
        display_height_px=display_height_px,
        enable_prompt_caching=enable_prompt_caching,
        computer_tool_type_decider=os.getenv("CORTEX_COMPUTER_TOOL_DECIDER", "computer_20250124").strip(),
        computer_tool_type_heavy=os.getenv("CORTEX_COMPUTER_TOOL_HEAVY", "computer_20251124").strip(),
        computer_use_beta_decider=os.getenv("CORTEX_COMPUTER_BETA_DECIDER", "computer-use-2025-01-24").strip(),
        computer_use_beta_heavy=os.getenv("CORTEX_COMPUTER_BETA_HEAVY", "computer-use-2025-11-24").strip(),
        prompt_caching_beta="prompt-caching-2024-07-31",
        token_efficient_tools_beta=os.getenv("CORTEX_TOKEN_EFFICIENT_TOOLS_BETA", "token-efficient-tools-2025-02-19").strip(),
    )
