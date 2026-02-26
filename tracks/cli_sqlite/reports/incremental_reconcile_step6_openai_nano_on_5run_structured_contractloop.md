# Incremental Reconcile (Step Cap 6) - OpenAI GPT-5 Nano - ON-only 5-run (Structured + Contract Post-Retry Validator)

Date: 2026-02-26

## Run Config
- Task: `incremental_reconcile`
- Domain: `sqlite`
- Sessions: `5` (`164100..164104`)
- Step cap: `6`
- Backend: `openai`
- Executor/Judge model: `gpt-5-nano`
- Lessons: `on` (`posttask-mode=direct`)
- Docs: `on` (`lossy`, retrieval `auto`)
- Deterministic benchmark mode: `on`
- Promoted-only retrieval: `on`
- Contract-gap retry: `on` (1 retry)
- Structured lessons required: `on`
- New behavior under test: deterministic post-retry validator on `no_tool_call`, `step_cap`, and `loop_exit`

## Artifacts
- Run log: `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_on_5run_structured_contractloop.log`
- Sessions: `tracks/cli_sqlite/sessions/session-164100` .. `tracks/cli_sqlite/sessions/session-164104`
- Prior baseline (without post-retry validator micro-policy): `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_on_5run_structured.md`

## Per-Run Outcomes
- `164100`: PASS (`score=1.00`, `steps=6`)
- `164101`: FAIL (`score=0.92`, `steps=6`)
- `164102`: PASS (`score=1.00`, `steps=6`)
- `164103`: FAIL (`score=0.83`, `steps=6`)
- `164104`: FAIL (`score=0.25`, `steps=4`)

Summary:
- Pass rate: `2/5` (`40%`)
- Median steps on successful runs: `6`
- Total runtime: `~6m01s`

## Delta vs Prior Structured ON-only Run
- Prior structured-only run (`163100..163104`): `1/5` (`20%`)
- Current structured+postretry-validator run (`164100..164104`): `2/5` (`40%`)
- Absolute lift: `+20 percentage points`

Interpretation:
- The closure micro-policy improved this slice, but still below target reliability.

## Mechanism Signal (New Micro-Policy)
- `contract_gap_retry_triggered`: `5/5` sessions
- `contract_validator_runs` (pre-retry deterministic validator): `3` total
- `contract_validator_postretry_runs` (new behavior): `3` total
- `contract_retry_repair_observed=true`: `2/5` sessions (`164101`, `164103`)
- Post-retry validator triggers observed:
  - `post_retry_after_repair` (`164101`, `164103`)
  - `no_tool_call` (`164104`)

What this means:
- The agent now performs deterministic closure checks after repair/no-tool conditions instead of stopping with unchecked state.
- This confirms the new policy is active in real runs, not only in tests.

## Failure Taxonomy (Post-Retry Unresolved Gaps)

Aggregated reason_code x gap_type:
- `missing_required_pattern | required_sql_pattern` = `6`
- `required_query_mismatch | required_query` = `4`
- `too_many_errors | error_budget` = `2`

Top unresolved signatures:
- `required_query_mismatch|required_query|reject_count` = `2`
- `required_query_mismatch|required_query|checkpoint_row` = `1`
- `required_query_mismatch|required_query|ledger_aggregate` = `1`
- `missing_required_pattern|required_sql_pattern|(?is)begin\\s+(transaction|immediate)` = `1`
- `missing_required_pattern|required_sql_pattern|(?is)commit` = `1`

## Bottom Line
- Micro-policy is mechanically correct and gives a measurable lift (`20% -> 40%` on this 5-run slice).
- Dominant unresolved failure is still `required_query_mismatch` plus missing SQL pattern closure, so the next gain should come from stronger closure-plan execution (not from more schema gating).
