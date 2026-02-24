# Incremental Reconcile 10-Run (Anchored Candidate + Forbidden/Error-Budget Fallback Hardening)

- session_range: `147300-147309`
- pass_rate: `70%` (7/10)
- last_5_pass_rate: `80%` (4/5)
- median_steps_to_success: `4`
- mean_lesson_activations: `0.80`
- mean_retrieval_help_ratio: `0.17`

## Per-Run

| run | session | passed | score | steps | tool_errors | lesson_activations | retrieval_help_ratio |
|---:|---:|:---:|---:|---:|---:|---:|---:|
| 1 | 147300 | N | 0.917 | 4 | 2 | 0 | 0.00 |
| 2 | 147301 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 3 | 147302 | N | 0.833 | 4 | 2 | 0 | 0.00 |
| 4 | 147303 | Y | 1.000 | 4 | 1 | 2 | 1.00 |
| 5 | 147304 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 6 | 147305 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 7 | 147306 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 8 | 147307 | N | 0.833 | 4 | 3 | 6 | 0.67 |
| 9 | 147308 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 10 | 147309 | Y | 1.000 | 4 | 0 | 0 | 0.00 |

## Failure Gap Taxonomy (from `contract_gap_postretry.json`)

| reason_code | count |
|---|---:|
| too_many_errors | 3 |
| matched_forbidden_pattern | 1 |
| required_query_mismatch | 1 |

Top unresolved gap signatures:

- `too_many_errors|error_budget|error_count=2 max_error_count=1`: 2
- `matched_forbidden_pattern|forbidden_sql_pattern|(?is)delete\s+from\s+ledger`: 1
- `required_query_mismatch|required_query|reject_count`: 1
- `too_many_errors|error_budget|error_count=3 max_error_count=1`: 1
