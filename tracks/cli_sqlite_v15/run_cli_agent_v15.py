#!/usr/bin/env python3
"""V1.5 locked single-run wrapper for Telegram/OpenClaw dispatch.

This wrapper keeps Telegram task-mode execution on one deterministic policy:
- backend: openai
- executor/judge: gpt-5-nano
- critic path: disabled (simplified architecture uses executor for lesson extraction)
- self-edit: disabled
- deterministic benchmark settings: enabled
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tracks.cli_sqlite_v15.profile import BASE_RUNNER, V15_LOCKED


def _build_command(args: argparse.Namespace) -> list[str]:
    cmd: list[str] = [
        "python3",
        str(BASE_RUNNER),
        "--task-id",
        args.task_id,
        "--domain",
        args.domain,
        "--session",
        str(args.session),
        "--max-steps",
        str(args.max_steps),
        "--posttask-mode",
        V15_LOCKED.posttask_mode,
        "--learning-mode",
        V15_LOCKED.learning_mode,
        # Simplified architecture bypasses separate critic-model generation and
        # keeps the proof path to one model behavior surface.
        "--architecture-mode",
        "simplified",
        "--llm-backend",
        V15_LOCKED.llm_backend,
        "--model-executor",
        V15_LOCKED.model_executor,
        "--model-judge",
        V15_LOCKED.model_judge,
        "--contract-gap-retry",
        "--contract-gap-retry-steps",
        str(V15_LOCKED.contract_gap_retry_steps),
        "--contract-gap-deterministic-recipes",
        "--structured-lessons-required",
        "--benchmark-deterministic",
        "--no-benchmark-promoted-only",
        "--doc-retrieval",
        V15_LOCKED.doc_retrieval,
        "--doc-mode",
        V15_LOCKED.doc_mode,
        "--judge-diagnostic",
        "--watchdog-allow-posttask-in-safe-mode",
        "--no-self-edit-mode",
        "--no-auto-escalate-critic",
    ]
    if args.task:
        cmd.extend(["--task", args.task])
    if args.run_id:
        cmd.extend(["--run-id", args.run_id])
    if args.no_posttask_learn:
        cmd.append("--no-posttask-learn")
    if args.verbose:
        cmd.append("--verbose")
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one CLI task using v1.5 locked runtime policy.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task", default="")
    parser.add_argument("--domain", default="shell", choices=["sqlite", "gridtool", "fluxtool", "artic", "shell"])
    parser.add_argument("--session", required=True, type=int)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--no-posttask-learn", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    # Dispatcher currently passes these flags. Keep parser compatibility so we
    # can hard-lock behavior without breaking call sites.
    parser.add_argument("--model-executor", default="")
    parser.add_argument("--llm-backend", default="")
    args = parser.parse_args()

    if not BASE_RUNNER.exists():
        print(f"error: base runner missing: {BASE_RUNNER}", file=sys.stderr)
        return 1

    cmd = _build_command(args)
    proc = subprocess.run(cmd, cwd=str(ROOT_DIR))
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
