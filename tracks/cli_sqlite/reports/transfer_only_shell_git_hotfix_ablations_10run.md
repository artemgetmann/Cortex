# Transfer-Only Ablations: shell_git_transfer_hotfix

## Metric Glossary

- `pass_rate`: fraction of runs that passed deterministic contract checks. High = reliable execution; low = unstable execution.
- `transfer_pass_rate`: pass rate on transfer-phase runs only (same as pass_rate in this transfer-only report). High = better generalization.
- `mean_X`: arithmetic average of X across runs; smooths noise.
- `median_X`: middle value of X across runs; robust to outliers.
- `median_steps_to_success`: median steps among successful runs only. Lower is better.
- `repeated_error_delta`: recurrence_after - recurrence_before. Negative is better.
- `median_repeated_error_delta`: median repeated-error delta across runs. Negative is better.
- `transfer_pass_delta`: last transfer pass - first transfer pass. Positive means trend improved.
- `activation_delta`: last transfer lesson activations - first transfer lesson activations. Positive means memory mechanism engaged more.
- `retrieval_help_ratio_delta`: last transfer retrieval help ratio - first transfer retrieval help ratio. Positive means retrieval helped more.

## How To Read This Report

- Compare pass_rate and runs_6_10_pass_rate across arms to isolate docs/lessons effects.
- If lessons-on materially beats lessons-off late in curve, memory is helping.
- If docs-on materially beats docs-off, docs grounding is helping.

## Arm Summary

| arm_id | docs | lessons | pass_rate | median_steps_to_success | runs_6_10_pass_rate | mean_lesson_activations | mean_retrieval_help_ratio |
|---|---|---|---:|---:|---:|---:|---:|
| docs_on__mode_lossy__lessons_on | on | on | 30.00% | 4.0 | 20.00% | 1.400 | 0.500 |
| docs_on__mode_lossy__lessons_off | on | off | 50.00% | 4.0 | 40.00% | 0.000 | 0.000 |
| docs_off__mode_none__lessons_on | off | on | 50.00% | 4.0 | 100.00% | 0.400 | 0.200 |
| docs_off__mode_none__lessons_off | off | off | 10.00% | 4.0 | 0.00% | 0.000 | 0.000 |

## Artifact Notes

- `contract_gap_postretry.json`: deterministic final gap check after retry; unresolved rows are exact blockers.
- `target_repo/hotfix.txt`: proves patch payload landed in target repo.
- `target_repo/transfer_summary.txt`: proves transfer metadata file was correctly written.

JSON report: `/Users/user/Programming_Projects/Cortex/tracks/cli_sqlite/reports/transfer_only_shell_git_hotfix_ablations_10run.json`
MD report: `/Users/user/Programming_Projects/Cortex/tracks/cli_sqlite/reports/transfer_only_shell_git_hotfix_ablations_10run.md`
