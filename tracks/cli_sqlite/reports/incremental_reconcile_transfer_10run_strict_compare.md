# Incremental Reconcile Transfer 10-Run Strict Comparison

## Setup
- task: `incremental_reconcile`
- domain: `sqlite`
- sessions per arm: `10`
- max_steps: `4`
- model: executor/judge `claude-haiku-4-5` via API
- docs: `on`, `lossy`, retrieval `auto`
- retry: contract-gap retry `on` (1)
- structured lessons: `required`

## Results
| arm | pass_rate | last5_pass_rate | median_steps_success | mean_lesson_activations | mean_retrieval_help_ratio | activation_nonzero_runs | retrieval_positive_runs |
|---|---:|---:|---:|---:|---:|---:|---:|
| lessons_on | 50.00% | 80.00% | 4 | 2.2000 | 0.6000 | 6 | 6 |
| lessons_off | 30.00% | 40.00% | 4 | 0.0000 | 0.0000 | 0 | 0 |

## Per-step Lesson Activations (mean per run)
- lessons_on: `{"2": 0.9, "3": 0.7, "4": 0.6}`
- lessons_off: `{}`

## Gap Taxonomy (post-retry unresolved)
- lessons_on reason_codes: `{"missing_required_pattern": 1, "required_query_mismatch": 1, "too_many_errors": 5}`
- lessons_off reason_codes: `{"missing_required_pattern": 2, "required_query_mismatch": 7, "too_many_errors": 5}`
- lessons_on top signatures: `[{"gap_signature": "too_many_errors|error_budget|error_count=2 max_error_count=1", "count": 3}, {"gap_signature": "too_many_errors|error_budget|error_count=3 max_error_count=1", "count": 2}, {"gap_signature": "missing_required_pattern|required_sql_pattern|(?is)insert\\s+into\\s+ledger", "count": 1}, {"gap_signature": "required_query_mismatch|required_query|checkpoint_row", "count": 1}]`
- lessons_off top signatures: `[{"gap_signature": "required_query_mismatch|required_query|reject_count", "count": 4}, {"gap_signature": "too_many_errors|error_budget|error_count=3 max_error_count=1", "count": 3}, {"gap_signature": "required_query_mismatch|required_query|checkpoint_row", "count": 2}, {"gap_signature": "too_many_errors|error_budget|error_count=2 max_error_count=1", "count": 2}, {"gap_signature": "missing_required_pattern|required_sql_pattern|(?is)insert\\s+into\\s+ledger", "count": 2}]`

## Strict Gate
- criterion: `{"activation_nonzero_required": true, "last5_pass_rate_min": 0.8, "retrieval_trend_positive_required": true}`
- verdict: `GO`
- rationale: last5_pass_rate=80.00%, activation_nonzero_runs=6, retrieval_help_ratio_delta=1.0000
