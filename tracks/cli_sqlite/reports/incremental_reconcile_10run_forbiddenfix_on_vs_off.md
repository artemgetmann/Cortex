# Incremental Reconcile 10-Run ON vs OFF (after forbidden/error-budget fallback hardening)

## Summary

- lessons_on pass_rate: `70%` (7/10)
- lessons_off pass_rate: `20%` (2/10)
- pass_rate_delta (on-off): `+50%`
- lessons_on last_5_pass_rate: `80%`
- lessons_off last_5_pass_rate: `20%`
- last_5_pass_rate_delta (on-off): `+60%`
- lessons_on mean_lesson_activations: `0.80`
- lessons_off mean_lesson_activations: `0.00`
- lessons_on mean_retrieval_help_ratio: `0.17`
- lessons_off mean_retrieval_help_ratio: `0.00`

## Failure Taxonomy

| arm | reason_code | count |
|---|---|---:|
| lessons_on | too_many_errors | 3 |
| lessons_on | matched_forbidden_pattern | 1 |
| lessons_on | required_query_mismatch | 1 |
| lessons_off | required_query_mismatch | 9 |
| lessons_off | too_many_errors | 6 |
| lessons_off | matched_forbidden_pattern | 4 |
| lessons_off | missing_required_pattern | 1 |

Top unresolved gap signatures (lessons_on):
- `too_many_errors|error_budget|error_count=2 max_error_count=1`: 2
- `matched_forbidden_pattern|forbidden_sql_pattern|(?is)delete\s+from\s+ledger`: 1
- `required_query_mismatch|required_query|reject_count`: 1
- `too_many_errors|error_budget|error_count=3 max_error_count=1`: 1

Top unresolved gap signatures (lessons_off):
- `too_many_errors|error_budget|error_count=2 max_error_count=1`: 6
- `matched_forbidden_pattern|forbidden_sql_pattern|(?is)delete\s+from\s+ledger`: 4
- `required_query_mismatch|required_query|checkpoint_row`: 3
- `required_query_mismatch|required_query|ledger_aggregate`: 3
- `required_query_mismatch|required_query|reject_count`: 3
- `missing_required_pattern|required_sql_pattern|(?is)insert\s+into\s+ledger`: 1
