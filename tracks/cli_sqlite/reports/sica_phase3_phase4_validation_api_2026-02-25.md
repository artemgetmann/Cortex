# SICA Phase 3/4 Validation (API)

Date: 2026-02-25
Branch: `lane/sica-cortex-20260225`
Worktree: `/Users/user/Programming_Projects/Cortex/.worktree/sica-cortex`

## Test Baseline

- Command: `python3 -m pytest tracks/cli_sqlite/tests -q`
- Result: `201 passed in 4.08s`

## Phase 3: Variant Scoreboard

Goal checks:
- Scoreboard output written each run.
- Deterministic best-variant default selection is visible in logs.

### Validation run A (selection + carry-forward)

- Command:
  - `python3 tracks/cli_sqlite/scripts/run_learning_curve.py --task-id shell_git_transfer_hotfix_hard --domain shell --sessions 3 --start-session 51001 --max-steps 4 --learning-mode strict --llm-backend anthropic --posttask-mode direct --self-edit-mode --no-posttask-learn`
- Observed runner logs:
  - Run 1: `no prior winner ... using deterministic fallback`
  - Run 2: `default task=shell_git_transfer_hotfix_hard variant=beta`
  - Run 3: `default task=shell_git_transfer_hotfix_hard variant=beta`
  - Each run emitted `[variant-scoreboard] variant=... score=... quality=... speed=... cost=...`

### Validation run B (clean scoreboard + deterministic winner)

- Command:
  - `python3 tracks/cli_sqlite/scripts/run_learning_curve.py --task-id shell_git_transfer_hotfix_hard --domain shell --sessions 2 --start-session 51501 --max-steps 1 --learning-mode strict --llm-backend anthropic --posttask-mode direct --self-edit-mode --no-posttask-learn`
- Observed runner logs:
  - Run 1: fallback selected `alpha`.
  - Run 2: `next default ... variant=alpha`.
- Scoreboard aggregate snapshot (from `variant_scoreboard.jsonl` during validation):
  - `variant_family=shell_git_transfer_hotfix_hard`
  - `best.variant_id=alpha`
  - `best.mean_variant_score=0.377082`
  - Deterministic tie-break is implemented in ranking sort keys.

## Phase 4: Loop Safety Watchdog

Goal checks:
- Repeat-failure loops are flagged.
- Runtime downgrades to safe mode and can raise stop flag on continued failures.

### Validation run (forced repeated failures)

- Command:
  - `python3 tracks/cli_sqlite/scripts/run_learning_curve.py --task-id import_aggregate --domain sqlite --sessions 2 --start-session 51401 --max-steps 0 --learning-mode strict --llm-backend anthropic --posttask-mode direct --self-edit-mode --no-posttask-learn`
- Session metrics evidence:
  - `session-51401/metrics.json`
    - `loop_watchdog_safe_mode_initial=false`
    - `loop_watchdog_safe_mode_triggered=true`
    - `loop_watchdog_safe_mode_active=true`
    - `loop_watchdog_stop_flag=false`
    - `loop_watchdog_failure_signals=["contract_gap_unresolved"]`
    - `self_edit_mode_effective=false`
  - `session-51402/metrics.json`
    - `loop_watchdog_safe_mode_initial=true`
    - `loop_watchdog_safe_mode_triggered=false`
    - `loop_watchdog_safe_mode_active=true`
    - `loop_watchdog_stop_flag=true`
    - `loop_watchdog_failure_signals=["contract_gap_unresolved"]`
    - `self_edit_mode_effective=false`

Interpretation:
- Run 1 enters safe mode (downgrade path).
- Continued failure in safe mode raises stop flag on run 2.

## Conclusion

- Phase 3 implemented and validated:
  - Scoreboard rows are produced per run.
  - Best-variant default selection is deterministic and printed in runner logs.
- Phase 4 implemented and validated:
  - Watchdog detects repeated failure signals.
  - Safe mode disables risky self-edit behavior.
  - Continued failures in safe mode produce a stop flag.
