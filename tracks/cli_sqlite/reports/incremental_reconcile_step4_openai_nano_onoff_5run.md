# Incremental Reconcile (Step Cap 4) - OpenAI GPT-5 Nano - 5-Run ON/OFF

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

## Artifacts
- ON log: `tracks/cli_sqlite/reports/incremental_reconcile_step4_openai_nano_on_5run.log`
- OFF log: `tracks/cli_sqlite/reports/incremental_reconcile_step4_openai_nano_off_5run.log`
- ON sessions: `tracks/cli_sqlite/sessions/session-141100` .. `tracks/cli_sqlite/sessions/session-141104`
- OFF sessions: `tracks/cli_sqlite/sessions/session-141200` .. `tracks/cli_sqlite/sessions/session-141204`

## Results Summary
- Lessons ON pass rate: `0/5` (`0%`)
- Lessons OFF pass rate: `0/5` (`0%`)
- ON mean steps: `2.2`
- OFF mean steps: `1.8`
- ON mean lesson activations: `1.6`
- OFF mean lesson activations: `0.0`
- ON mean retrieval help ratio: `0.8`
- OFF mean retrieval help ratio: `0.0`
- Lessons generated: `0` in both ON and OFF runs

## What This Means
- This slice did not show learning lift because both arms failed all runs.
- The model often stopped early after `read_skill`, triggering contract-gap retry but still not closing required outputs.
- Mechanism metrics (`lesson_activations`, `retrieval_help_ratio`) moved in ON, but with zero passes and zero promoted lesson writes this is not usable evidence of improvement.

## Immediate Next Step
- Do not run larger curves on this exact config yet.
- First run a 1-session backend sanity check on the same task with a stronger model and same harness to verify the issue is model capability vs orchestration.
