# incremental_reconcile step4 ON/OFF benchmark (openai, gpt-5-nano)

## Headline
- ON pass_rate: 60.0%
- OFF pass_rate: 60.0%
- ON last5_pass_rate: 60.0%
- OFF last5_pass_rate: 40.0%
- ON median_steps_to_success: 4.0
- OFF median_steps_to_success: 4.0
- ON-OFF pass delta: 0.0 pp
- mean_lesson_activations ON/OFF: 0.000 / 0.000
- mean_retrieval_help_ratio ON/OFF: 0.000 / 0.000

## ON per-run

| session | pass | score | steps | tool_errors | lesson_activations | retrieval_help_ratio |
|---:|:---:|---:|---:|---:|---:|---:|
| 195000 | Y | 1.00 | 4 | 0 | 0 | 0.000 |
| 195001 | N | 0.92 | 4 | 2 | 0 | 0.000 |
| 195002 | Y | 1.00 | 4 | 0 | 0 | 0.000 |
| 195003 | N | 0.83 | 4 | 2 | 0 | 0.000 |
| 195004 | Y | 1.00 | 4 | 1 | 0 | 0.000 |
| 195005 | Y | 1.00 | 4 | 2 | 0 | 0.000 |
| 195006 | N | 0.83 | 4 | 3 | 0 | 0.000 |
| 195007 | Y | 1.00 | 4 | 2 | 0 | 0.000 |
| 195008 | Y | 1.00 | 4 | 0 | 0 | 0.000 |
| 195009 | N | 0.92 | 4 | 2 | 0 | 0.000 |

## ON failure taxonomy (from contract_gap_postretry.json)

| reason_code | gap_type | count |
|---|---|---:|
| too_many_errors | error_budget | 4 |
| matched_forbidden_pattern | forbidden_sql_pattern | 1 |
| required_query_mismatch | required_query | 1 |

| top_signature | count |
|---|---:|
| error_count=2 max_error_count=1 | 3 |
| (?is)delete\s+from\s+ledger | 1 |
| error_count=3 max_error_count=1 | 1 |
| reject_count | 1 |

## OFF per-run

| session | pass | score | steps | tool_errors | lesson_activations | retrieval_help_ratio |
|---:|:---:|---:|---:|---:|---:|---:|
| 195200 | Y | 1.00 | 4 | 1 | 0 | 0.000 |
| 195201 | Y | 1.00 | 4 | 1 | 0 | 0.000 |
| 195202 | Y | 1.00 | 4 | 1 | 0 | 0.000 |
| 195203 | Y | 1.00 | 4 | 0 | 0 | 0.000 |
| 195204 | N | 0.58 | 4 | 4 | 0 | 0.000 |
| 195205 | Y | 1.00 | 4 | 2 | 0 | 0.000 |
| 195206 | N | 0.92 | 4 | 1 | 0 | 0.000 |
| 195207 | Y | 1.00 | 3 | 0 | 0 | 0.000 |
| 195208 | N | 0.75 | 4 | 3 | 0 | 0.000 |
| 195209 | N | 0.92 | 4 | 2 | 0 | 0.000 |

## OFF failure taxonomy (from contract_gap_postretry.json)

| reason_code | gap_type | count |
|---|---|---:|
| required_query_mismatch | required_query | 4 |
| missing_required_pattern | required_sql_pattern | 3 |
| too_many_errors | error_budget | 3 |

| top_signature | count |
|---|---:|
| (?is)insert\s+into\s+ledger | 3 |
| reject_count | 2 |
| checkpoint_row | 1 |
| error_count=2 max_error_count=1 | 1 |
| error_count=3 max_error_count=1 | 1 |
| error_count=4 max_error_count=1 | 1 |
| ledger_aggregate | 1 |
