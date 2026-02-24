# Incremental Reconcile Strict 10-Run Compare (Post-Patch)

Task: `incremental_reconcile`

## Headline
- lessons_on: pass_rate=60.0% (6/10), last5=80.0%, median_steps_to_success=3.5
- lessons_off: pass_rate=10.0% (1/10), last5=0.0%, median_steps_to_success=4
- delta(pass_rate): +50.0 pp

## Mechanism Signal
- lessons_on: mean_lesson_activations=2.00, mean_retrieval_help_ratio=0.50, activation_delta=+0.00, retrieval_help_ratio_delta=+0.00
- lessons_off: mean_lesson_activations=0.00, mean_retrieval_help_ratio=0.00, activation_delta=+0.00, retrieval_help_ratio_delta=+0.00

## Gap Taxonomy (failures)
### lessons_on
- reason counts: `{"matched_forbidden_pattern": 1, "missing_required_pattern": 1, "required_query_mismatch": 1, "too_many_errors": 2}`
- gap type counts: `{"error_budget": 2, "forbidden_sql_pattern": 1, "required_query": 1, "required_sql_pattern": 1}`
- top signatures: `[{"gap_signature": "too_many_errors|error_budget|error_count=2 max_error_count=1", "count": 2}, {"gap_signature": "matched_forbidden_pattern|forbidden_sql_pattern|(?is)delete\\s+from\\s+ledger", "count": 1}, {"gap_signature": "missing_required_pattern|required_sql_pattern|(?is)insert\\s+into\\s+ledger", "count": 1}, {"gap_signature": "required_query_mismatch|required_query|reject_count", "count": 1}]`

### lessons_off
- reason counts: `{"matched_forbidden_pattern": 2, "required_query_mismatch": 12, "too_many_errors": 8}`
- gap type counts: `{"error_budget": 8, "forbidden_sql_pattern": 2, "required_query": 12}`
- top signatures: `[{"gap_signature": "too_many_errors|error_budget|error_count=2 max_error_count=1", "count": 5}, {"gap_signature": "required_query_mismatch|required_query|checkpoint_row", "count": 4}, {"gap_signature": "required_query_mismatch|required_query|ledger_aggregate", "count": 4}, {"gap_signature": "required_query_mismatch|required_query|reject_count", "count": 4}, {"gap_signature": "too_many_errors|error_budget|error_count=3 max_error_count=1", "count": 3}, {"gap_signature": "matched_forbidden_pattern|forbidden_sql_pattern|(?is)delete\\s+from\\s+ledger", "count": 2}]`

## Per-run
| arm | session | pass | score | steps | tool_errors | activations | help_ratio |
| --- | ---: | :---: | ---: | ---: | ---: | ---: | ---: |
| lessons_on | 144000 | Y | 1.000 | 4 | 1 | 0 | 0.00 |
| lessons_on | 144001 | N | 0.833 | 4 | 2 | 6 | 1.00 |
| lessons_on | 144002 | N | 0.917 | 4 | 0 | 2 | 1.00 |
| lessons_on | 144003 | N | 0.917 | 4 | 2 | 6 | 1.00 |
| lessons_on | 144004 | Y | 1.000 | 3 | 0 | 0 | 0.00 |
| lessons_on | 144005 | Y | 1.000 | 4 | 1 | 4 | 1.00 |
| lessons_on | 144006 | N | 0.917 | 4 | 0 | 2 | 1.00 |
| lessons_on | 144007 | Y | 1.000 | 3 | 0 | 0 | 0.00 |
| lessons_on | 144008 | Y | 1.000 | 3 | 0 | 0 | 0.00 |
| lessons_on | 144009 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_off | 144100 | N | 0.750 | 4 | 3 | 0 | 0.00 |
| lessons_off | 144101 | N | 0.750 | 4 | 3 | 0 | 0.00 |
| lessons_off | 144102 | Y | 1.000 | 4 | 1 | 0 | 0.00 |
| lessons_off | 144103 | N | 0.833 | 4 | 2 | 0 | 0.00 |
| lessons_off | 144104 | N | 0.833 | 4 | 3 | 0 | 0.00 |
| lessons_off | 144105 | N | 0.917 | 4 | 2 | 0 | 0.00 |
| lessons_off | 144106 | N | 0.667 | 4 | 2 | 0 | 0.00 |
| lessons_off | 144107 | N | 0.583 | 4 | 2 | 0 | 0.00 |
| lessons_off | 144108 | N | 0.917 | 4 | 1 | 0 | 0.00 |
| lessons_off | 144109 | N | 0.917 | 4 | 2 | 0 | 0.00 |
