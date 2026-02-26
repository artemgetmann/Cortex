# Incremental Reconcile (Step Cap 4) - OpenAI GPT-5 Nano - 5-Run ON/OFF (Post-Refactor)

Date: 2026-02-26

## Run Config
- Task: `incremental_reconcile`
- Domain: `sqlite`
- Sessions per arm: `5`
- Step cap: `4`
- Backend: `openai`
- Executor/Judge model: `gpt-5-nano`
- Docs: `on` (`lossy`, retrieval `auto`)
- Deterministic benchmark mode: `on`
- Promoted-only retrieval: `on`
- Contract-gap retry: `on` (1 retry)
- Structured lessons required: `on`
- Code baseline: `09b8ccf` (adapter-level deterministic recipes; core orchestrator domain-agnostic)

## Artifacts
- ON log: `tracks/cli_sqlite/reports/incremental_reconcile_step4_openai_nano_on_5run_refactor.log`
- OFF log: `tracks/cli_sqlite/reports/incremental_reconcile_step4_openai_nano_off_5run_refactor.log`
- ON sessions: `tracks/cli_sqlite/sessions/session-161100` .. `tracks/cli_sqlite/sessions/session-161104`
- OFF sessions: `tracks/cli_sqlite/sessions/session-161200` .. `tracks/cli_sqlite/sessions/session-161204`

## Results Summary
- Lessons ON pass rate: `0/5` (`0%`)
- Lessons OFF pass rate: `0/5` (`0%`)
- ON mean steps: `4.0`
- OFF mean steps: `3.6`
- ON mean lesson activations: `3.2`
- OFF mean lesson activations: `0.0`
- ON mean retrieval help ratio: `0.8`
- OFF mean retrieval help ratio: `0.0`
- ON mean deterministic hint count: `3.0`
- OFF mean deterministic hint count: `3.0`

## Failure Taxonomy (from `contract_gap_postretry.json`)

ON dominant unresolved gaps:
- `required_query_mismatch | required_query` = `8`
- `too_many_errors | error_budget` = `4`
- `missing_required_pattern | required_sql_pattern` = `2`

ON top unresolved signatures:
- `required_query_mismatch|required_query|reject_count` = `4`
- `too_many_errors|error_budget|error_count=2 max_error_count=1` = `4`
- `required_query_mismatch|required_query|checkpoint_row` = `2`
- `required_query_mismatch|required_query|ledger_aggregate` = `2`

OFF dominant unresolved gaps:
- `missing_required_pattern | required_sql_pattern` = `12`
- `required_query_mismatch | required_query` = `9`
- `too_many_errors | error_budget` = `2`

OFF top unresolved signatures:
- `required_query_mismatch|required_query|reject_count` = `4`
- `required_query_mismatch|required_query|checkpoint_row` = `3`
- `missing_required_pattern|required_sql_pattern|(?is)insert\\s+into\\s+ledger` = `2`
- `missing_required_pattern|required_sql_pattern|(?is)insert\\s+into\\s+rejects` = `2`

## Interpretation
- The refactor succeeded architecturally (core is domain-agnostic), but this exact transfer slice remains execution-limited for `gpt-5-nano` at step cap `4`.
- Mechanism metrics move in ON (activations/help), but not enough to produce pass lift on this run.
- Main blocker is closure quality on required query end-state, not retrieval triggering.

## Recommended Next Move
1. Keep this architecture.
2. Add one generic closure micro-policy (pre-stop verifier nudge) for unresolved `required_query_mismatch`:
   - if mismatch remains, force one exact validator-query + one repair + re-validate cycle.
3. Re-run ON/OFF 5-run at step cap `4`.
4. If still flat, run step cap `5` as a stress split to confirm capability ceiling vs orchestration issue.

