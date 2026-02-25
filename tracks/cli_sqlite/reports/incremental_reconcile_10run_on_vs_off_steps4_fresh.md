# Incremental Reconcile ON vs OFF (10-run strict, steps=4, fresh state)

Settings: anthropic API, executor/judge `claude-haiku-4-5`, docs `on/lossy`, retrieval `auto`, judge diagnostic `on`, contract-gap retry `on` (1), structured lessons required.

## Gate Verdict

- Gate: GO if ON last-5 >= 80% and ON > OFF
- ON transfer pass rate: `80.0%`
- OFF transfer pass rate: `60.0%`
- ON last-5 pass rate: `100.0%`
- Verdict: `GO`

## Arm Summary

| arm | transfer pass rate | last-5 pass rate | median steps among successes | pass count |
| --- | --- | --- | --- | --- |
| on | 80.0% | 100.0% | 4.0 | 8/10 |
| off | 60.0% | 40.0% | 4.0 | 6/10 |

## Per-Run (ON)

| run | session | pass | score | steps | tool_errors | unresolved gap signatures (postretry) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 261000 | N | 0.917 | 4 | 2 | too_many_errors|error_budget|error_count=2 max_error_count=1 |
| 2 | 261001 | Y | 1.000 | 4 | 1 | - |
| 3 | 261002 | N | 0.917 | 4 | 2 | too_many_errors|error_budget|error_count=2 max_error_count=1 |
| 4 | 261003 | Y | 1.000 | 4 | 0 | - |
| 5 | 261004 | Y | 1.000 | 4 | 0 | - |
| 6 | 261005 | Y | 1.000 | 4 | 0 | - |
| 7 | 261006 | Y | 1.000 | 4 | 0 | - |
| 8 | 261007 | Y | 1.000 | 4 | 0 | - |
| 9 | 261008 | Y | 1.000 | 4 | 0 | - |
| 10 | 261009 | Y | 1.000 | 4 | 0 | - |

## Per-Run (OFF)

| run | session | pass | score | steps | tool_errors | unresolved gap signatures (postretry) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 261100 | Y | 1.000 | 4 | 1 | - |
| 2 | 261101 | N | 0.833 | 4 | 2 | required_query_mismatch|required_query|reject_count, too_many_errors|error_budget|error_count=2 max_error_count=1 |
| 3 | 261102 | Y | 1.000 | 4 | 1 | - |
| 4 | 261103 | Y | 1.000 | 4 | 1 | - |
| 5 | 261104 | Y | 1.000 | 4 | 1 | - |
| 6 | 261105 | N | 0.917 | 4 | 3 | too_many_errors|error_budget|error_count=3 max_error_count=1 |
| 7 | 261106 | N | 0.667 | 4 | 2 | required_query_mismatch|required_query|checkpoint_row, required_query_mismatch|required_query|ledger_aggregate, required_query_mismatch|required_query|reject_count, too_many_errors|error_budget|error_count=2 max_error_count=1 |
| 8 | 261107 | Y | 1.000 | 4 | 1 | - |
| 9 | 261108 | Y | 1.000 | 4 | 1 | - |
| 10 | 261109 | N | 0.917 | 4 | 3 | too_many_errors|error_budget|error_count=3 max_error_count=1 |

## Failure Taxonomy (from contract_gap_postretry.json)

| arm | reason_code | gap_type | gap_signature | count |
| --- | --- | --- | --- | --- |
| off | required_query_mismatch | required_query | required_query_mismatch|required_query|reject_count | 2 |
| off | too_many_errors | error_budget | too_many_errors|error_budget|error_count=2 max_error_count=1 | 2 |
| off | too_many_errors | error_budget | too_many_errors|error_budget|error_count=3 max_error_count=1 | 2 |
| off | required_query_mismatch | required_query | required_query_mismatch|required_query|checkpoint_row | 1 |
| off | required_query_mismatch | required_query | required_query_mismatch|required_query|ledger_aggregate | 1 |
| on | too_many_errors | error_budget | too_many_errors|error_budget|error_count=2 max_error_count=1 | 2 |

## Concise Readout

ON clears the gate threshold on late-run stability (`100.0%` >= `80%`) and beats OFF overall on transfer pass rate (`80.0%` vs `60.0%`).
