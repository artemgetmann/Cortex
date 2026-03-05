# ON/OFF Benchmark Summary: incremental_reconcile (step4, 10 runs, OpenAI nano, promoted-only disabled)

## Headline Metrics

- ON pass_rate: 30.0%
- OFF pass_rate: 50.0%
- ON last5_pass_rate: 0.0%
- OFF last5_pass_rate: 20.0%
- ON median_steps_to_success: 4
- OFF median_steps_to_success: 4
- ON-OFF pass delta: -20.0 pp
- mean_lesson_activations ON/OFF: 2.30 / 0.00
- mean_retrieval_help_ratio ON/OFF: 0.70 / 0.00

## Per-Run (ON)

| session | pass | score | steps | tool_errors | lesson_activations | retrieval_help_ratio |
|---:|:---:|---:|---:|---:|---:|---:|
| 196000 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 196001 | N | 0.917 | 4 | 2 | 0 | 0.00 |
| 196002 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 196003 | N | 0.833 | 4 | 2 | 6 | 1.00 |
| 196004 | Y | 1.000 | 4 | 0 | 1 | 1.00 |
| 196005 | N | 0.667 | 4 | 2 | 2 | 1.00 |
| 196006 | N | 0.750 | 4 | 0 | 2 | 1.00 |
| 196007 | N | 0.917 | 4 | 2 | 6 | 1.00 |
| 196008 | N | 0.750 | 4 | 0 | 2 | 1.00 |
| 196009 | N | 0.917 | 4 | 1 | 4 | 1.00 |

## Per-Run (OFF)

| session | pass | score | steps | tool_errors | lesson_activations | retrieval_help_ratio |
|---:|:---:|---:|---:|---:|---:|---:|
| 196200 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 196201 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 196202 | Y | 1.000 | 4 | 1 | 0 | 0.00 |
| 196203 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 196204 | N | 0.917 | 4 | 1 | 0 | 0.00 |
| 196205 | N | 0.917 | 4 | 2 | 0 | 0.00 |
| 196206 | N | 0.917 | 4 | 0 | 0 | 0.00 |
| 196207 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| 196208 | N | 0.833 | 4 | 3 | 0 | 0.00 |
| 196209 | N | 0.833 | 4 | 3 | 0 | 0.00 |

## Failure Taxonomy (ON)

reason_code / gap_type counts:
- required_query_mismatch / required_query: 7
- missing_required_pattern / required_sql_pattern: 5
- too_many_errors / error_budget: 3

top signatures:
- 5x required_query_mismatch|required_query|reject_count
- 3x missing_required_pattern|required_sql_pattern|(?is)insert\s+into\s+ledger
- 3x too_many_errors|error_budget|error_count=2 max_error_count=1
- 2x missing_required_pattern|required_sql_pattern|(?is)insert\s+into\s+rejects
- 1x required_query_mismatch|required_query|checkpoint_row
- 1x required_query_mismatch|required_query|ledger_aggregate

## Failure Taxonomy (OFF)

reason_code / gap_type counts:
- required_query_mismatch / required_query: 3
- too_many_errors / error_budget: 3
- missing_required_pattern / required_sql_pattern: 1

top signatures:
- 3x required_query_mismatch|required_query|reject_count
- 2x too_many_errors|error_budget|error_count=3 max_error_count=1
- 1x missing_required_pattern|required_sql_pattern|(?is)insert\s+into\s+ledger
- 1x too_many_errors|error_budget|error_count=2 max_error_count=1

