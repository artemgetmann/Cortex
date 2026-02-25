# SICA Worktree Plan (Cortex)

Date: 2026-02-25
Worktree: `/Users/user/Programming_Projects/Cortex/.worktree/sica-cortex`
Branch: `lane/sica-cortex-20260225`

## Goal

Use the best parts of SICA that fit Cortex right now:

1. Let the system improve root causes, not only write more lessons.
2. Track which variant actually performs best.
3. Keep strict safety checks so we do not break reliability.

## What We Will Build in This Worktree

## Phase 1: Baseline Snapshot (Read Before Edit)

What:

1. Capture current behavior on a small fixed benchmark set.
2. Save baseline metrics for pass rate, run time, and cost.

Why:

We need a hard before/after comparison so we know if changes help.

Done when:

1. Baseline report is saved under `tracks/cli_sqlite/reports/`.
2. We can point to one file that says "current best known behavior."

## Phase 2: Safe Self-Edit Gate (Small Scope)

What:

1. Add a guarded mode where the agent can propose tiny code fixes for a limited target set (start with CLI orchestration files only).
2. Require automatic checks before accepting any patch.
3. Reject and roll back any patch that fails checks.

Why:

This is the fastest way to copy SICA's main advantage without copying its whole system.

Done when:

1. A proposed patch is only accepted if tests/checks pass.
2. Failed patches are clearly logged as rejected.

## Phase 3: Variant Scoreboard (Simple, Honest Ranking)

What:

1. Add a small scoreboard that ranks runs by quality, speed, and cost.
2. Keep the current best variant as default for the next run.

Why:

Without ranking, we are guessing. With ranking, we pick winners based on results.

Done when:

1. Scoreboard output is written each run.
2. "Best variant" selection is deterministic and visible in logs.

## Phase 4: Loop Safety Watchdog

What:

1. Add a watchdog that detects repeat-failure loops.
2. Stop or downgrade risky behavior when the same bad pattern repeats.

Why:

Self-improvement without loop protection burns time and budget.

Done when:

1. Repeated-failure loops are flagged in logs.
2. The run exits safely or falls back to safe mode.

## Phase 5: Validate and Keep-or-Kill

What:

1. Run the same benchmark set from Phase 1.
2. Compare before vs after.
3. Keep only pieces that improve outcomes with no reliability regression.

Why:

Only measured improvements should survive.

Done when:

1. We have a short comparison report.
2. Any neutral or harmful change is removed or disabled.

## Guardrails

1. No broad self-editing scope on day one. Start narrow.
2. No bypass of existing deterministic checks.
3. No default-on for new behavior without benchmark evidence.

## File Targets (Initial)

1. `tracks/cli_sqlite/agent_cli.py`
2. `tracks/cli_sqlite/scripts/run_cli_agent.py`
3. `tracks/cli_sqlite/run_observability.py`
4. `tracks/cli_sqlite/scripts/run_learning_curve.py`
5. New small module(s) for:
   - patch safety gate,
   - variant scoring,
   - loop watchdog.

## Verification Commands

```bash
python3 -m pytest tracks/cli_sqlite/tests -q
python3 tracks/cli_sqlite/scripts/run_cli_agent.py --help
python3 tracks/cli_sqlite/scripts/run_learning_curve.py --help
```

## Definition of Done

1. Baseline and after reports are both saved.
2. Safe self-edit path is test-gated and logged.
3. Variant scoreboard is active and reproducible.
4. Loop watchdog prevents repeated bad cycles.
5. No regression on existing core tests.

## Merge Note

After this plan is completed and validation passes, we should merge this worktree branch back into `main`.
