# Incremental Reconcile (Step Cap 6) - OpenAI GPT-5 Nano - ON-only 8-run

Date: 2026-02-26

## Run Config
- Task: `incremental_reconcile`
- Domain: `sqlite`
- Sessions: `8`
- Step cap: `6`
- Backend: `openai`
- Executor/Judge model: `gpt-5-nano`
- Lessons: `on` (`posttask-mode=direct`)
- Docs: `on` (`lossy`, retrieval `auto`)
- Deterministic benchmark mode: `on`
- Promoted-only retrieval: `on`
- Contract-gap retry: `on` (1 retry)
- Structured lessons required: `on`
- Start session: `162100`
- Code baseline: `09b8ccf` + `3492a9c`

## Artifacts
- Run log: `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_on_8run_rerun.log`
- Sessions: `tracks/cli_sqlite/sessions/session-162100` .. `tracks/cli_sqlite/sessions/session-162107`

## Results
- Pass rate: `0/8` (`0%`)
- Score trajectory:
  - `0.25 -> 0.92 -> 0.83 -> 0.50 -> 0.25 -> 0.75 -> 0.75 -> 0.83`
- Improvement in score only:
  - first run `0.25` -> last run `0.83` (`+0.58`)
- Contract pass still `false` in all runs.

## Failure Taxonomy (post-retry unresolved gaps)

Top reason/gap counts:
- `required_query_mismatch | required_query` = `15`
- `missing_required_pattern | required_sql_pattern` = `14`
- `too_many_errors | error_budget` = `5`
- `matched_forbidden_pattern | forbidden_sql_pattern` = `1`

Top unresolved signatures:
- `required_query_mismatch|required_query|reject_count` = `8`
- `missing_required_pattern|required_sql_pattern|(?is)insert\\s+into\\s+ledger` = `4`
- `required_query_mismatch|required_query|checkpoint_row` = `4`
- `required_query_mismatch|required_query|ledger_aggregate` = `3`
- transaction/checkpoint pattern misses also persist in some runs.

## Interpretation
- Increasing step cap from `4` to `6` did not unlock pass under this strict config.
- Mechanism activation is present, but closure quality remains below contract threshold.
- Dominant blocker is deterministic end-state mismatch on required query `reject_count`, followed by missing required SQL pattern coverage in some runs.

## Next Decision
- Do not spend tokens on ON/OFF ablations yet.
- First add a generic closure micro-policy for unresolved `required_query_mismatch`:
  - force validator query -> one targeted repair -> validator query before stop.
- Re-run ON-only 5-run at step `6`.
- Only if ON lifts, run a tiny OFF control (2-3 runs) to confirm delta.

