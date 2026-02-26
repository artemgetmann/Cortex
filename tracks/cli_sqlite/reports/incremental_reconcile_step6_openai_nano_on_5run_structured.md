# Incremental Reconcile (Step Cap 6) - OpenAI GPT-5 Nano - ON-only 5-run (Structured Lessons)

Date: 2026-02-26

## Run Config
- Task: `incremental_reconcile`
- Domain: `sqlite`
- Sessions: `5`
- Step cap: `6`
- Backend: `openai`
- Executor/Judge model: `gpt-5-nano`
- Lessons: `on` (`posttask-mode=direct`)
- Docs: `on` (`lossy`, retrieval `auto`)
- Deterministic benchmark mode: `on`
- Promoted-only retrieval: `on`
- Contract-gap retry: `on` (1 retry)
- Structured lessons required: `on`
- Start session: `163100`
- Code baseline: `5b93a7d` (structured executable lesson enforcement)

## Artifacts
- Run log: `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_on_5run_structured.log`
- Sessions: `tracks/cli_sqlite/sessions/session-163100` .. `tracks/cli_sqlite/sessions/session-163104`

## Per-Run Outcomes
- `163100`: PASS (`score=1.00`, `steps=6`)
- `163101`: FAIL (`score=0.83`, `steps=6`)
- `163102`: FAIL (`score=0.92`, `steps=6`)
- `163103`: FAIL (`score=0.75`, `steps=5`)
- `163104`: FAIL (`score=0.25`, `steps=4`)

Summary:
- Pass rate: `1/5` (`20%`)
- Total runtime: `~6m23s`

## Mechanism Signal
- `v2_schema_rejection_counts` became active and observable.
- No malformed-lesson drops in this sample except unbound trigger filtering:
  - `unbound_trigger_gap_signature`: seen in sessions `163102`, `163103`.
- `lessons_generated` (V2): non-zero in failed runs (`2-3` per run).
- Activation/help remained inconsistent:
  - Effective lesson activation was mostly `0`, except session `163104`.

Interpretation:
- Schema enforcement is working mechanically.
- The bottleneck shifted to execution/closure reliability, not missing schema checks.

## Failure Taxonomy (post-retry unresolved gaps)

Top reason/gap counts:
- `missing_required_pattern | required_sql_pattern` = `6`
- `required_query_mismatch | required_query` = `6`
- `too_many_errors | error_budget` = `3`

Top unresolved signatures:
- `required_query_mismatch|required_query|reject_count` = `3`
- `required_query_mismatch|required_query|checkpoint_row` = `2`
- remaining misses are split across transaction/checkpoint/insert required SQL patterns.

## What This Tells Us
- Structured lesson schema enforcement did not regress runtime and produced one full pass.
- But this slice is still below target reliability; the main remaining issue is closure quality on exact required query state.

## Recommended Next Move
1. Add one generic closure micro-policy for `required_query_mismatch` before stop:
   - force `validator query -> one repair -> validator query` loop for the same signature.
2. Re-run ON-only 5-run at step `6`.
3. If ON improves materially (target last-5 >= 80%), run OFF control for 2-3 runs only.

