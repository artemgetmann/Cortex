# Benchmark Update (2026-02-25, API reruns)

Goal checked in this batch:
- Lessons ON should beat Lessons OFF clearly.
- Stretch target: ON last-5 runs reach 100%.

## Fresh runs (this session)

| Experiment | ON pass | ON last-5 | OFF pass | OFF last-5 | Notes |
| --- | --- | --- | --- | --- | --- |
| `incremental_reconcile` step=3 | 3/10 (30%) | 2/5 (40%) | 1/10 (10%) | 0/5 (0%) | Strong ON>OFF gap, but ON convergence too low. |
| `shell_git_transfer_hotfix` step=4 docs=off | 4/10 (40%) | 2/5 (40%) | 3/10 (30%) | 2/5 (40%) | Weak separation; noisy slice. |
| `incremental_reconcile` step=4 | 4/10 (40%) | 3/5 (60%) | 2/10 (20%) | 1/5 (20%) | Best ON>OFF tradeoff in fresh reruns, still below 100% last-5. |

Longer accumulation check:
- `incremental_reconcile` step=4 ON for 15 runs: 9/15 total, last-5 = 3/5 (60%).
- Extending runs alone did not reach 100% late-curve stability.

## Mechanism evidence (learning machinery)

When lessons are ON, mechanism metrics are non-zero; when OFF, they are zero:
- ON examples: mean lesson activations in the 1.6-3.6 range, retrieval-help ratio in the 0.8-0.9 range.
- OFF examples: activations 0.0, retrieval-help 0.0.

Interpretation:
- The learning pipeline is active and being used.
- But activation alone is not enough; outcome convergence is still inconsistent.

## Sanitizer patch attempt (tested and reverted)

I tested two code changes intended to reduce noisy/poisoned lessons:
1. sanitize legacy lesson text before storage/retrieval
2. sanitize/filter V2 candidate lessons before persistence

Both were benchmark-tested immediately and then reverted because they did not improve convergence in this batch.

## Practical readout

- We have evidence that lessons can improve outcomes relative to OFF on hard slices.
- We do **not** yet have a robust proof of ON last-5 = 100% under the current setup.
- Next step should be deterministic benchmark mode + promoted-only retrieval lane during benchmark, then rerun one strict ON/OFF slice.

## Raw logs from this batch

- `tracks/cli_sqlite/reports/transfer_only_shell_git_hotfix_10run_steps4_on.log`
- `tracks/cli_sqlite/reports/transfer_only_shell_git_hotfix_10run_steps4_off.log`
- `tracks/cli_sqlite/reports/incremental_reconcile_10run_steps3_on.log`
- `tracks/cli_sqlite/reports/incremental_reconcile_10run_steps3_off.log`
- `tracks/cli_sqlite/reports/shell_git_transfer_hotfix_10run_docs_off_steps4_on.log`
- `tracks/cli_sqlite/reports/shell_git_transfer_hotfix_10run_docs_off_steps4_off.log`
- `tracks/cli_sqlite/reports/incremental_reconcile_10run_steps4_on_retry.log`
- `tracks/cli_sqlite/reports/incremental_reconcile_10run_steps4_off_retry.log`
- `tracks/cli_sqlite/reports/incremental_reconcile_15run_steps4_on_retry.log`
- `tracks/cli_sqlite/reports/incremental_reconcile_10run_steps4_on_sanitized.log`
- `tracks/cli_sqlite/reports/incremental_reconcile_10run_steps4_on_sanitized_v2.log`
