# Shell Hotfix Hard ON/OFF Slice (Step Cap 6, 5 Runs, 2026-03-09)

## Protocol

- Task: `shell_git_transfer_hotfix_hard`
- Backend: `openai`
- Executor/Judge model: `gpt-5-nano`
- Deterministic flags: `--benchmark-deterministic`, `--structured-lessons-required`
- Docs: `--doc-mode none --doc-retrieval off --executor-docs off --judge-docs off`
- Self-edit: `--no-self-edit-mode`
- ON lane: `ab_shell_hotfix_on_20260309` (`posttask_learn=True`)
- OFF lane: `ab_shell_hotfix_off_20260309` (`--no-posttask-learn`)

## Per-Arm Summary

- ON (sessions `609100-609104`)
  - pass rate: `3/5` (`60%`)
  - mean score: `0.856`
  - mean errors: `3.8`
  - mean lesson activations: `0.8`
  - mean retrieval help ratio: `0.333`
- OFF (sessions `609200-609204`)
  - pass rate: `2/5` (`40%`)
  - mean score: `0.878`
  - mean errors: `3.8`
  - mean lesson activations: `0.0`
  - mean retrieval help ratio: `0.0`

## Readout

- Pass/fail reliability favors ON (`+20pp` pass rate).
- Mean score is slightly higher in OFF, so this slice still has variance.
- Mechanism signal is present in ON only (`activations > 0`, `help_ratio > 0`).

## Telegram-Path Smoke (same phrasing)

- Dispatcher path: `integrations/openclaw_agi_dispatch.py` with
  `CORTEX_RUNTIME_LANE=telegram_smoke_20260309`.
- Input phrasing:
  - `Create and verify a git hotfix workflow: generate hotfix.txt and transfer_summary.txt, apply hotfix patch cleanly, and prove final repo status is clean. Use only 6 steps.`
- Outcome:
  - auto routed to task mode (`reason=auto_task_intent`)
  - canonical task mapped: `shell_git_transfer_hotfix_hard`
  - adaptive attempts: `2` attempts
  - final result: `eval_passed=true`, `eval_score=1.0`
  - final session: `tracks/cli_sqlite/runtime/telegram_smoke_20260309/sessions/session-1001`

