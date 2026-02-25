# Incremental Reconcile Step=4 (Deterministic + Promoted-Only) ON/OFF

Run date: 2026-02-25  
Task: `sqlite/incremental_reconcile`  
Protocol: `max_steps=4`, `docs=on/lossy`, `doc_retrieval=auto`, `judge_diagnostic=on`, `contract_gap_retry=on`, `structured_lessons_required=on`, `llm_backend=anthropic`, `model_executor=claude-haiku-4-5`, `model_judge=claude-haiku-4-5`, `benchmark_deterministic=on`, `benchmark_promoted_only=on`.

Raw logs:
- `tracks/cli_sqlite/reports/incremental_reconcile_step4_on_detpromoted.log`
- `tracks/cli_sqlite/reports/incremental_reconcile_step4_off_detpromoted.log`

## Summary

- lessons_on pass rate: `70% (7/10)`
- lessons_on runs 6-10 pass rate: `100% (5/5)`
- lessons_off pass rate: `0% (0/10)`
- lessons_off runs 6-10 pass rate: `0% (0/5)`
- median steps among successful runs:
  - lessons_on: `4`
  - lessons_off: `n/a` (no successes)

## Per-run results

| run | lessons_on | lessons_off |
|---:|:---:|:---:|
| 1 | FAIL | FAIL |
| 2 | FAIL | FAIL |
| 3 | FAIL | FAIL |
| 4 | PASS | FAIL |
| 5 | PASS | FAIL |
| 6 | PASS | FAIL |
| 7 | PASS | FAIL |
| 8 | PASS | FAIL |
| 9 | PASS | FAIL |
| 10 | PASS | FAIL |

## Failure taxonomy (from `contract_gap_postretry` artifacts)

lessons_on unresolved gaps (failed runs):
- `too_many_errors / error_budget`: `3`
- `required_query_mismatch / required_query`: `2`

lessons_off unresolved gaps:
- `required_query_mismatch / required_query`: `11`
- `too_many_errors / error_budget`: `10`
- `matched_forbidden_pattern / forbidden_sql_pattern`: `2`

## Mechanism note

- `v2_lesson_activations`: `0` in this slice.
- `v2_retrieval_help_ratio`: `0.0` in this slice.

Interpretation: performance lift is strong in pass/fail terms, but V2 activation metrics did not engage under this exact deterministic+promoted-only setup, so this run should be treated as execution-quality evidence rather than mechanism-level memory evidence.

## Go / No-Go

- Execution quality gate (`ON last5 >= 80% and OFF clearly lower`): **GO**
- Strict mechanism gate (`lesson_activations > 0` and `retrieval_help_ratio` lift): **NO-GO** for this slice.

