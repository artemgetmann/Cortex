# Incremental Reconcile Strict 10-Run Compare (Query-Gap Fix)

Task: `incremental_reconcile`

## Headline
- lessons_on: pass_rate=50.0% (5/10), last5=80.0%, median_steps_to_success=4
- lessons_off: pass_rate=30.0% (3/10), last5=0.0%, median_steps_to_success=4
- delta(pass_rate): +20.0 pp

## Mechanism Signal
- lessons_on: mean_lesson_activations=2.60, mean_retrieval_help_ratio=0.50, activation_delta=+0.00, retrieval_help_ratio_delta=+0.00
- lessons_off: mean_lesson_activations=0.00, mean_retrieval_help_ratio=0.00, activation_delta=+0.00, retrieval_help_ratio_delta=+0.00

## Gap Taxonomy (failures)
### lessons_on
- reason counts: `{"matched_forbidden_pattern": 3, "required_query_mismatch": 7, "too_many_errors": 4}`
- gap type counts: `{"error_budget": 4, "forbidden_sql_pattern": 3, "required_query": 7}`
- top signatures: `[{"gap_signature": "matched_forbidden_pattern|forbidden_sql_pattern|(?is)delete\\s+from\\s+ledger", "count": 3}, {"gap_signature": "required_query_mismatch|required_query|checkpoint_row", "count": 3}, {"gap_signature": "required_query_mismatch|required_query|ledger_aggregate", "count": 3}, {"gap_signature": "too_many_errors|error_budget|error_count=2 max_error_count=1", "count": 3}, {"gap_signature": "required_query_mismatch|required_query|reject_count", "count": 1}, {"gap_signature": "too_many_errors|error_budget|error_count=3 max_error_count=1", "count": 1}]`

### lessons_off
- reason counts: `{"matched_forbidden_pattern": 1, "missing_required_pattern": 2, "required_query_mismatch": 7, "too_many_errors": 5}`
- gap type counts: `{"error_budget": 5, "forbidden_sql_pattern": 1, "required_query": 7, "required_sql_pattern": 2}`
- top signatures: `[{"gap_signature": "too_many_errors|error_budget|error_count=2 max_error_count=1", "count": 4}, {"gap_signature": "required_query_mismatch|required_query|reject_count", "count": 3}, {"gap_signature": "missing_required_pattern|required_sql_pattern|(?is)insert\\s+into\\s+ledger", "count": 2}, {"gap_signature": "required_query_mismatch|required_query|checkpoint_row", "count": 2}, {"gap_signature": "required_query_mismatch|required_query|ledger_aggregate", "count": 2}, {"gap_signature": "matched_forbidden_pattern|forbidden_sql_pattern|(?is)delete\\s+from\\s+ledger", "count": 1}, {"gap_signature": "too_many_errors|error_budget|error_count=3 max_error_count=1", "count": 1}]`

## Per-run
| arm | session | pass | score | steps | tool_errors | activations | help_ratio |
| --- | ---: | :---: | ---: | ---: | ---: | ---: | ---: |
| lessons_on | 146100 | N | 0.750 | 4 | 2 | 0 | 0.00 |
| lessons_on | 146101 | N | 0.750 | 4 | 2 | 6 | 1.00 |
| lessons_on | 146102 | N | 0.750 | 4 | 1 | 4 | 1.00 |
| lessons_on | 146103 | N | 0.667 | 4 | 3 | 8 | 1.00 |
| lessons_on | 146104 | Y | 1.000 | 4 | 1 | 2 | 1.00 |
| lessons_on | 146105 | N | 0.917 | 4 | 2 | 6 | 1.00 |
| lessons_on | 146106 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_on | 146107 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_on | 146108 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_on | 146109 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_off | 146200 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_off | 146201 | Y | 1.000 | 4 | 1 | 0 | 0.00 |
| lessons_off | 146202 | N | 0.917 | 4 | 2 | 0 | 0.00 |
| lessons_off | 146203 | Y | 1.000 | 4 | 1 | 0 | 0.00 |
| lessons_off | 146204 | N | 0.750 | 4 | 3 | 0 | 0.00 |
| lessons_off | 146205 | N | 0.917 | 4 | 1 | 0 | 0.00 |
| lessons_off | 146206 | N | 0.667 | 4 | 2 | 0 | 0.00 |
| lessons_off | 146207 | N | 0.917 | 4 | 1 | 0 | 0.00 |
| lessons_off | 146208 | N | 0.667 | 4 | 2 | 0 | 0.00 |
| lessons_off | 146209 | N | 0.917 | 4 | 2 | 0 | 0.00 |
