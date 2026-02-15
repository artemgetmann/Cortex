# Strict Transfer Refactor Plan

## Summary
Refactor CLI learning from domain-hardcoded assistance to a strict, retrieval-driven learning loop that can be validated on a real holdout domain. Keep a legacy mode for comparability and demo fallback.

## Locked Decisions
- Primary objective: honest benchmark over inflated in-domain performance.
- Critic knowledge source: retrieval-backed context (local docs first).
- Validation scope: one holdout domain in v1.

## Target Outcomes
- Strict mode has no gridtool-specific critic examples or command regex dependency in the core learning path.
- One holdout domain exists with remapped syntax/operators.
- Cross-domain train->test runner reports measurable transfer vs baseline.
- Legacy mode remains available for backward-compatible runs.

## Workstreams

### 1) Learning Modes (`strict` vs `legacy`)
Status: `pending`
- Add `--learning-mode {strict,legacy}` to:
  - `tracks/cli_sqlite/scripts/run_cli_agent.py`
  - `tracks/cli_sqlite/scripts/run_learning_curve.py`
  - `tracks/cli_sqlite/scripts/demo_learning.py`
- Thread mode into `run_cli_agent(...)` and metrics.

### 2) Generic Critic Contract (Strict Mode)
Status: `pending`
- Replace strict-mode critic prompt examples with schema-only instructions.
- Keep `LessonGenerationResult(raw_lessons, filtered_lessons)`.
- Preserve current prompt path under legacy mode.

### 3) Retrieval-Backed Critic Context
Status: `pending`
- Add `knowledge_provider` interface and local-doc retrieval implementation.
- Expose domain docs manifest from adapters.
- Inject retrieved chunks into critic context in strict mode.

### 4) Generic Runtime Hint Matching
Status: `pending`
- Strict mode: semantic/tag overlap matching instead of command-name regex map.
- Legacy mode: keep current `_ERROR_COMMAND_PATTERNS` path.
- Cap strict hint injection to max 2 per failed step.

### 5) Holdout Domain
Status: `pending`
- Add new fictional domain with remapped command/operator language.
- Add adapter + tasks + docs pack.
- Register domain in adapter resolution and runner choices.

### 6) Cross-Domain Runner
Status: `pending`
- Add `tracks/cli_sqlite/scripts/run_cross_domain.py`.
- Support `--train-domain/--test-domain` and common experiment params.
- Emit transfer metrics (first-pass index, post-pass regressions, delta).

### 7) Validation + Docs
Status: `pending`
- Add/adjust tests for strict/legacy behavior split.
- Add holdout and cross-domain validation commands to docs.
- Add acceptance gates and expected signatures.

## Acceptance Criteria
- Strict mode can run without domain-specific critic examples.
- Strict mode can run without domain-specific command regex routing for hint matching.
- Cross-domain runner executes end-to-end with one holdout domain.
- Test suite remains green for existing coverage.
- Legacy mode behavior remains available and documented.

## Notes for Step-by-Step Updates
When a workstream is completed:
1. Change `Status` from `pending` to `completed`.
2. Add a short bullet under the workstream with commit hash and date.
3. Link any new/changed test commands used for verification.
