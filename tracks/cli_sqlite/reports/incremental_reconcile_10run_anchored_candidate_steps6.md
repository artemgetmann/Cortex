# Incremental Reconcile 10-Run (Anchored Candidate Retrieval, Step Cap 6)

- session_range: `147200-147209`
- pass_rate: `10%` (1/10)
- last_5_pass_rate: `20%` (1/5)
- median_steps_to_success: `6`
- mean_lesson_activations: `4.80`
- mean_retrieval_help_ratio: `0.80`

## Per-Run

| run | session | passed | score | steps | lesson_activations | retrieval_help_ratio |
|---:|---:|:---:|---:|---:|---:|---:|
| 1 | 147200 | N | 0.917 | 6 | 0 | 0.00 |
| 2 | 147201 | N | 0.917 | 6 | 4 | 1.00 |
| 3 | 147202 | N | 0.833 | 6 | 6 | 1.00 |
| 4 | 147203 | N | 0.917 | 6 | 4 | 1.00 |
| 5 | 147204 | N | 0.917 | 6 | 0 | 0.00 |
| 6 | 147205 | Y | 1.000 | 6 | 2 | 1.00 |
| 7 | 147206 | N | 0.833 | 6 | 10 | 1.00 |
| 8 | 147207 | N | 0.833 | 6 | 8 | 1.00 |
| 9 | 147208 | N | 0.917 | 6 | 6 | 1.00 |
| 10 | 147209 | N | 0.833 | 6 | 8 | 1.00 |

## Failure Gap Taxonomy (from `contract_gap_postretry.json`)

| reason_code | count |
|---|---:|
| too_many_errors | 8 |
| matched_forbidden_pattern | 3 |
| missing_required_pattern | 1 |
| required_query_mismatch | 1 |

Top unresolved gap signatures:

- `matched_forbidden_pattern|forbidden_sql_pattern|(?is)delete\s+from\s+ledger`: 3
- `too_many_errors|error_budget|error_count=2 max_error_count=1`: 3
- `too_many_errors|error_budget|error_count=3 max_error_count=1`: 3
- `too_many_errors|error_budget|error_count=4 max_error_count=1`: 2
- `missing_required_pattern|required_sql_pattern|(?is)insert\s+into\s+ledger`: 1
- `required_query_mismatch|required_query|reject_count`: 1
