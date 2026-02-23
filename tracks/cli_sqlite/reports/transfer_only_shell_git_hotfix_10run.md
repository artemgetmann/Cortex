# Transfer-Only Learning Report: shell_git_transfer_hotfix

## Metric Glossary

- `pass_rate`: fraction of runs that passed deterministic contract checks. High = reliable execution; low = unstable execution.
- `transfer_pass_rate`: pass rate on transfer-phase runs only (here identical to pass_rate because this report is transfer-only). High = better generalization; low = weak transfer.
- `mean_X`: arithmetic average of metric X across runs; smooths noise.
- `median_X`: middle value of metric X; robust to outliers.
- `median_steps_to_success`: median steps among successful runs only. Lower is better.
- `repeated_error_delta`: `fingerprint_recurrence_after - fingerprint_recurrence_before`; negative is better.
- `median_repeated_error_delta`: median repeated-error delta across runs; negative is better.
- `transfer_pass_delta`: `last_transfer_pass - first_transfer_pass`; positive means later-run improvement.
- `activation_delta`: `last_transfer_lesson_activations - first_transfer_lesson_activations`; positive means lessons engaged more.
- `retrieval_help_ratio_delta`: `last_transfer_retrieval_help_ratio - first_transfer_retrieval_help_ratio`; positive means retrieval helped more.

## How To Read This Report

- Primary outcome: transfer pass rate and runs 6–10 pass rate.
- Mechanism outcome: lesson activations and retrieval_help_ratio should be non-zero/positive.
- Failure diagnosis: unresolved gaps in `contract_gap_postretry.json` show exact reasons the final retry still failed.

## Summary

- transfer_pass_rate: `90.00%` (9/10)
- median_steps_to_success: `4.0`
- runs_6_10_pass_rate: `100.00%` (5/5)
- recommendation: `run ablations now`

## Per-Run Results

| run | session | passed | score | steps | tool_errors | lesson_activations | retrieval_help_ratio | gap_retry_triggered | unresolved_gaps_final | elapsed_s |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 130200 | PASS | 1.000 | 4 | 0 | 0 | 0.000 | 1 | 0 | 39.12 |
| 2 | 130201 | FAIL | 0.923 | 4 | 0 | 0 | 0.000 | 1 | 1 | 46.80 |
| 3 | 130202 | PASS | 1.000 | 4 | 2 | 4 | 1.000 | 0 | 0 | 34.45 |
| 4 | 130203 | PASS | 1.000 | 3 | 0 | 0 | 0.000 | 0 | 0 | 27.81 |
| 5 | 130204 | PASS | 1.000 | 4 | 1 | 2 | 1.000 | 1 | 0 | 40.40 |
| 6 | 130205 | PASS | 1.000 | 4 | 0 | 0 | 0.000 | 0 | 0 | 29.40 |
| 7 | 130206 | PASS | 1.000 | 3 | 0 | 0 | 0.000 | 0 | 0 | 28.57 |
| 8 | 130207 | PASS | 1.000 | 3 | 0 | 0 | 0.000 | 0 | 0 | 30.75 |
| 9 | 130208 | PASS | 1.000 | 3 | 0 | 0 | 0.000 | 0 | 0 | 29.00 |
| 10 | 130209 | PASS | 1.000 | 4 | 0 | 0 | 0.000 | 0 | 0 | 36.96 |

## Failure Gap Taxonomy (from contract_gap_postretry.json)

### reason_code counts
- `missing_required_event_pattern`: 1

### gap_type counts
- `required_event_pattern`: 1

### top unresolved gap_signatures
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix\.patch`: 1

## Artifact Notes (why these files matter)

- `contract_gap_postretry.json`: deterministic final check after retry; tells us exactly what requirements are still unresolved.
- `target_repo/hotfix.txt`: proves the patch content actually landed in target repo (not just command attempted).
- `target_repo/transfer_summary.txt`: proves expected transfer metadata was written (`TRANSFER_BRANCH`, `TRANSFER_PATCHES`) as contract evidence.

## Interpretation Rule

- Rule low-case: If transfer pass remains around ~50% after 10 runs => likely system issue (not variance).
- Rule high-case: If transfer pass trends toward ~80% by runs 6–10 => learning signal is strong enough to proceed to ablations.
- Observed transfer_pass_rate: 90.00%
- Observed runs_6_10_pass_rate: 100.00%
- Decision: run ablations now

JSON report: `/Users/user/Programming_Projects/Cortex/tracks/cli_sqlite/reports/transfer_only_shell_git_hotfix_10run.json`
MD report: `/Users/user/Programming_Projects/Cortex/tracks/cli_sqlite/reports/transfer_only_shell_git_hotfix_10run.md`
