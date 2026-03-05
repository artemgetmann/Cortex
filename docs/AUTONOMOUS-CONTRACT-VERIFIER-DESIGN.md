# Autonomous Contract + Verifier Generation Design

Date: 2026-03-05
Owner: Cortex core runtime
Status: design proposal (no runtime change yet)

## Problem Statement

Today, Cortex gets strong signal when a task has a deterministic `CONTRACT.json`.
For new or dynamic tasks (especially free-text `/run` requests), contract coverage is uneven, so evaluation can fall back to weaker signals. That reduces learning quality and makes pass/fail less trustworthy.

We need a way to generate contract + verifier assets automatically without letting the model grade its own homework.

Goal: increase deterministic coverage for unknown tasks while preserving the current v1.5 Telegram runtime guarantees.

## First-Principles Architecture

Start from invariants:
1. Verifier truth decides pass/fail, not model confidence.
2. Generator and evaluator must be separated.
3. New generated logic starts as provisional, never trusted by default.
4. Runtime must fail closed to current behavior.

### Components

1. Contract Generator
- Input: task text, domain hint, tool traces, failure/gap artifacts.
- Output: `provisional_contract.json` (normalized schema) + `verifier_spec.json` (declarative checks first, code only if unavoidable).

2. Static Safety Validator
- Schema check, forbidden operations check, complexity/time budget check.
- Rejects unsafe or underspecified contracts before any execution.

3. Sandboxed Verifier Runner
- Runs generated verifier code (if present) in isolated process with strict CPU/time/fs/network limits.
- Produces deterministic pass/fail + structured evidence.

4. Calibrator
- Replays verifier against known pass/fail fixtures or recent lane artifacts.
- Measures disagreement against trusted baseline checks.

5. Promotion Gate
- States: `shadow` -> `candidate` -> `promoted`.
- Promotion requires stable calibration over repeated runs.
- Any regression demotes to `shadow` automatically.

6. Runtime Selector
- During evaluation, prefer:
  1. Native task contract (`tasks/<task>/CONTRACT.json`)
  2. Promoted generated verifier
  3. Existing fallback path (current judge path)
- Never skip baseline deterministic checks when they exist.

### Data Model (Minimal)

- `runtime/<lane>/contracts/generated/<task_or_signature>/contract.json`
- `runtime/<lane>/contracts/generated/<task_or_signature>/verifier.json`
- `runtime/<lane>/contracts/generated/<task_or_signature>/state.json`
  - `state`: `shadow|candidate|promoted|demoted`
  - `calibration_runs`
  - `disagreement_rate`
  - `last_updated_ts`

## Safety Constraints

1. Separation of roles
- Generator model cannot be the sole evaluator for the same run outcome.

2. Deterministic-first policy
- If static deterministic contract exists, it remains source of truth.

3. Sandboxing
- Generated verifier execution runs with no network, restricted fs, hard timeout, and memory cap.

4. Bounded complexity
- Max verifier length, max helper functions, max runtime per check.

5. No silent promotion
- Promotion requires explicit measurable thresholds and audit trail.

6. Lane isolation
- Telegram lane artifacts stay inside `runtime/telegram` and never mix with benchmark lane by default.

7. Fail-closed fallback
- Any validator/runtime/sandbox error falls back to current v15 evaluation flow.

8. Full observability
- Every generated asset and decision logged with reason codes.

## Phased Rollout

### P0: Shadow Generation Only
- Generate provisional contract/verifier after runs.
- Do not use for pass/fail.
- Track schema validity, safety rejects, and calibration disagreement offline.

Exit gate:
- >=99% schema-valid outputs.
- 0 sandbox policy violations in canary sample.

### P1: Candidate Use for Non-Critical Dynamic Tasks
- Enable for dynamic task IDs only (`openclaw_dynamic_*`) in Telegram lane canary.
- Generated verifier may provide advisory score, not final pass/fail.
- Compare against current baseline for drift.

Exit gate:
- No increase in false-pass incidents.
- Disagreement with trusted checks below threshold for N consecutive runs.

### P2: Controlled Promotion to Deterministic Path
- Allow promoted generated verifiers to participate in pass/fail for scoped domains.
- Keep automatic demotion on divergence.
- Expand gradually by domain and user scope.

Exit gate:
- Measurable pass-rate lift with stable OFF controls.
- No material regression in learning quality metrics.

## Success Metrics

Primary:
1. Deterministic coverage rate for dynamic tasks.
2. False-pass rate delta vs baseline (must not regress).
3. Transfer lift on repeated similar tasks in Telegram lane.

Secondary:
1. Contract-gap unresolved count reduction.
2. Attempts-to-success reduction.
3. Median run latency overhead from verifier stack.
4. Promotion durability (time in promoted state without demotion).

Guardrail:
1. OFF/control arm remains statistically stable.

## Risks And Kill-Switches

### Key Risks

1. Self-grading bias
- Risk: generated rules hide failures.
- Mitigation: role separation + calibration + conservative promotion.

2. Overfitting to narrow phrasing
- Risk: verifier passes one wording, fails equivalent tasks.
- Mitigation: replay set with paraphrases and counterexamples.

3. Sandbox escape or unsafe checker behavior
- Risk: code execution hazard.
- Mitigation: strict sandbox + declarative-first verifier format.

4. Cost/latency blow-up
- Risk: too much generation and replay per run.
- Mitigation: trigger only on missing-contract or repeated gap families.

5. Metric gaming
- Risk: pass-rate rises while real utility drops.
- Mitigation: keep independent utility checks and manual spot audits.

### Kill-Switches (Immediate)

1. `CORTEX_AUTON_CONTRACT_GEN=0`
- Disable generation pipeline.

2. `CORTEX_AUTON_VERIFIER_USE=0`
- Ignore generated verifiers in runtime selection.

3. `CORTEX_AUTON_PROMOTION=0`
- Freeze all states at `shadow`.

4. Dispatcher-level rollback
- Force current locked path by keeping `CORTEX_DISPATCH_PROFILE=v15` and bypassing generated verifier selector.

5. Lane-level rollback
- Disable only `runtime/telegram` generated artifacts while preserving other lanes.

## Integration With Current v15 Telegram Flow

Current path (today):
1. Telegram bot receives `/run` or auto-routed task in `integrations/cortex-telegram-agi-bot`.
2. Bot calls `integrations/cortex_dispatch.py` (defaults `CORTEX_DISPATCH_PROFILE=v15`).
3. Dispatcher (`integrations/openclaw_agi_dispatch.py`) routes to `tracks/cli_sqlite_v15/run_cli_agent_v15.py`.
4. v15 runner enforces locked flags (OpenAI + `gpt-5-nano`, deterministic controls, contract-gap retry).
5. Core runtime evaluates via existing contract/judge path and writes lane-scoped artifacts.

Planned integration:
1. Add generation hook in post-run phase (after existing metrics/artifacts write).
2. For P0/P1, hook is sidecar only: writes provisional contract/verifier artifacts in telegram lane runtime path.
3. Extend `/run-status` payload to include generated verifier state (`shadow/candidate/promoted`) and last calibration result.
4. Keep existing v15 locked execution contract unchanged unless explicit feature flag enables selector.
5. If selector is enabled and fails at any point, runtime falls back to current deterministic/judge behavior in the same run.

Net effect:
- v15 Telegram flow remains stable by default.
- Autonomous contract+verifier generation can be introduced incrementally without breaking transport semantics (`/run`, `/learn-status`, `/run-status`, `/followup`, `/cancel`).
