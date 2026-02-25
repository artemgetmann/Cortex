# Incremental Reconcile 10-Run (Anchored Candidate Retrieval)

- session_range: `147100-147109`
- pass_rate: `20%` (2/10)
- last_5_pass_rate: `20%` (1/5)
- median_steps_to_success: `4.0`
- mean_lesson_activations: `3.40`
- mean_retrieval_help_ratio: `0.90`

## Per-Run

| run | session | passed | score | steps | lesson_activations | retrieval_help_ratio |
|---:|---:|:---:|---:|---:|---:|---:|
| 1 | 147100 | Y | 1.000 | 4 | 0 | 0.00 |
| 2 | 147101 | N | 0.917 | 4 | 2 | 1.00 |
| 3 | 147102 | N | 0.917 | 4 | 4 | 1.00 |
| 4 | 147103 | N | 0.917 | 4 | 4 | 1.00 |
| 5 | 147104 | N | 0.833 | 4 | 6 | 1.00 |
| 6 | 147105 | N | 0.833 | 4 | 4 | 1.00 |
| 7 | 147106 | N | 0.917 | 4 | 4 | 1.00 |
| 8 | 147107 | N | 0.917 | 4 | 4 | 1.00 |
| 9 | 147108 | N | 0.917 | 4 | 2 | 1.00 |
| 10 | 147109 | Y | 1.000 | 4 | 4 | 1.00 |

## Failure Gap Taxonomy (from `contract_gap_postretry.json`)

| reason_code | count |
|---|---:|
| required_query_mismatch | 6 |
| missing_required_pattern | 2 |
| matched_forbidden_pattern | 1 |
| too_many_errors | 1 |

Top unresolved gap signatures:

- `required_query_mismatch|required_query|reject_count`: 6
- `missing_required_pattern|required_sql_pattern|(?is)insert\s+into\s+ledger`: 2
- `matched_forbidden_pattern|forbidden_sql_pattern|(?is)delete\s+from\s+ledger`: 1
- `too_many_errors|error_budget|error_count=2 max_error_count=1`: 1
