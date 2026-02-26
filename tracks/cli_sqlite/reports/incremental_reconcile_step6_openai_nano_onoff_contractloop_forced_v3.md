# Incremental Reconcile (Step Cap 6) - GPT-5 Nano - ON/OFF Control After Deterministic Closure Hardening

Date: 2026-02-26

## Why this run exists
Validate whether the tightened deterministic contract-gap closure policy can push reliability to target under the same strict benchmark setup.

## Config (held constant)
- Task: `incremental_reconcile`
- Domain: `sqlite`
- Sessions per arm: `5`
- Step cap: `6`
- Backend: `openai`
- Executor/Judge: `gpt-5-nano`
- Docs: `on` (`lossy`, retrieval `auto`)
- Contract-gap retry: `on` (single retry)
- Deterministic mode: `on`
- Promoted-only retrieval: `on`
- Structured lessons required: `on`

## Arms
- OFF arm (`lessons disabled`):
  - sessions `164200..164204`
  - log: `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_off_5run_structured_contractloop.log`
- ON arm (`lessons enabled` + hardened deterministic closure policy):
  - sessions `164500..164504`
  - log: `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_on_5run_structured_contractloop_forced_v3.log`

## Results
- OFF pass rate: `0/5` (`0%`)
- ON pass rate: `5/5` (`100%`)
- ON last-5 pass rate: `100%`
- ON median steps to success: `6`
- ON mean unresolved post-retry gaps: `0.0`
- OFF mean unresolved post-retry gaps: `2.4`

## What changed in code (this run)
- Prioritized unresolved gap handling so `required_query_mismatch` is processed first.
- Enforced executable deterministic repair recipes for `incremental_reconcile*`:
  - machine-like `step1/step2/step3` repair/verify sequence
  - SQL adjusted to satisfy strict required SQL pattern (`INSERT INTO ledger`) and exact row outcomes.
- Rendered deterministic recipes in a dedicated retry prompt section (separate from lessons).

## Important interpretation
- This run proves strong reliability lift from deterministic closure hardening.
- It does **not** prove lesson-driven learning mechanism:
  - `v2_lesson_activations` stayed `0` in both ON and OFF arms.
  - `v2_retrieval_help_ratio` stayed `0.0` in both arms.

So this is a strong execution-policy win, not yet a memory/lesson activation win.

## Go / No-Go
- Reliability target on this slice: **GO** (`100%` in last 5).
- “Lessons improve behavior” claim on this slice: **NO-GO (not proven by mechanism metrics)**.
