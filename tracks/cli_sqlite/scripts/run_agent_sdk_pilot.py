#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PilotArgs:
    """CLI input contract for the Agent SDK pilot scaffold."""

    task: str
    session: int
    max_steps: int
    mode: str


def _parse_args() -> PilotArgs:
    ap = argparse.ArgumentParser(
        description=(
            "Scaffold-only Agent SDK pilot entrypoint. "
            "This file is intentionally non-production until memory/judge parity is implemented."
        )
    )
    ap.add_argument(
        "--task",
        required=True,
        help="Task text or task identifier for pilot wiring tests.",
    )
    ap.add_argument(
        "--session",
        required=True,
        type=int,
        help="Session id for pilot artifact naming.",
    )
    ap.add_argument(
        "--max-steps",
        default=12,
        type=int,
        help="Upper bound for planned Agent SDK turn loop.",
    )
    ap.add_argument(
        "--mode",
        default="dry-run",
        choices=("dry-run", "pilot"),
        help="dry-run prints wiring plan only; pilot is reserved for future implementation.",
    )
    ns = ap.parse_args()
    return PilotArgs(
        task=ns.task.strip(),
        session=ns.session,
        max_steps=ns.max_steps,
        mode=ns.mode,
    )


def main() -> int:
    args = _parse_args()

    # IMPORTANT: This command is intentionally a scaffold.
    # No production runtime path is allowed yet.
    if args.mode != "dry-run":
        print(
            "Agent SDK pilot is scaffold-only right now. Use --mode dry-run until TODOs are implemented.",
            file=sys.stderr,
        )
        return 2

    # TODO(agent-sdk): Instantiate Agent SDK client (ClaudeSDKClient path, not query()).
    # TODO(memory-v2): Add pre-run retrieval call to memory.usemindmirror.com.
    # TODO(agent-loop): Implement tool-use turn loop with domain adapter delegation.
    # TODO(memory-v2): Capture error/state/action on executor failures and persist to memory backend.
    # TODO(memory-v2): Inject on-error retrieval hints into the next model turn.
    # TODO(eval): Run deterministic contract eval then judge fallback/primary path.
    # TODO(observability): Write events + metrics artifacts with Memory V2 parity fields.
    scaffold_plan = {
        "status": "scaffold_only",
        "production_ready": False,
        "args": asdict(args),
        "next_step": "Implement TODO blocks in docs/AGENT-SDK-PILOT-PLAN.md order.",
    }
    print(json.dumps(scaffold_plan, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
