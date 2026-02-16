# Strict Transfer Refactor Plan

Note: active planning for next iteration is now tracked in `docs/MEMORY-V2-EXECUTION-PLAN.md` (living doc).

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
Status: `completed`
- Add `--learning-mode {strict,legacy}` to:
  - `tracks/cli_sqlite/scripts/run_cli_agent.py`
  - `tracks/cli_sqlite/scripts/run_learning_curve.py`
  - `tracks/cli_sqlite/scripts/demo_learning.py`
- Thread mode into `run_cli_agent(...)` and metrics.
- `2026-02-15`: Completed (commit hash: `pending-user-confirmation`).
- Verification: `python3 -m pytest tracks/cli_sqlite/tests -q` (`49 passed`).

### 2) Generic Critic Contract (Strict Mode)
Status: `completed`
- Replace strict-mode critic prompt examples with schema-only instructions.
- Keep `LessonGenerationResult(raw_lessons, filtered_lessons)`.
- Preserve current prompt path under legacy mode.
- `2026-02-15`: Completed (commit hash: `pending-user-confirmation`).
- Verification: strict prompt split wired in `tracks/cli_sqlite/learning_cli.py`; existing tests pass (`49 passed`).

### 3) Retrieval-Backed Critic Context
Status: `completed`
- Add `knowledge_provider` interface and local-doc retrieval implementation.
- Expose domain docs manifest from adapters.
- Inject retrieved chunks into critic context in strict mode.
- `2026-02-15`: Completed (commit hash: `pending-user-confirmation`).
- Verification: `tracks/cli_sqlite/knowledge_provider.py` + adapter `docs_manifest()` + strict-mode injection in `tracks/cli_sqlite/agent_cli.py`; tests pass (`49 passed`).

### 4) Generic Runtime Hint Matching
Status: `completed`
- Strict mode: semantic/tag overlap matching instead of command-name regex map.
- Legacy mode: keep current `_ERROR_COMMAND_PATTERNS` path.
- Cap strict hint injection to max 2 per failed step.
- `2026-02-15`: Completed (commit hash: `pending-user-confirmation`).
- Verification: strict/legacy split in `find_lessons_for_error(...)` and new tests in `tracks/cli_sqlite/tests/test_strict_transfer.py`.

### 5) Holdout Domain
Status: `completed`
- Add new fictional domain with remapped command/operator language.
- Add adapter + tasks + docs pack.
- Register domain in adapter resolution and runner choices.
- `2026-02-15`: Completed (commit hash: `pending-user-confirmation`).
- Verification:
  - `python3 tracks/cli_sqlite/domains/fluxtool.py --workdir tracks/cli_sqlite/tasks/aggregate_report_holdout` with fluent command script returns grouped output.
  - Fluxtool smoke test included in `tracks/cli_sqlite/tests/test_strict_transfer.py`.

### 6) Cross-Domain Runner
Status: `completed`
- Add `tracks/cli_sqlite/scripts/run_cross_domain.py`.
- Support `--train-domain/--test-domain` and common experiment params.
- Emit transfer metrics (first-pass index, post-pass regressions, delta).
- `2026-02-15`: Completed (commit hash: `pending-user-confirmation`).
- Verification: `python3 tracks/cli_sqlite/scripts/run_cross_domain.py --help` includes train/test domain flags and learning mode.

### 7) Validation + Docs
Status: `completed`
- Add/adjust tests for strict/legacy behavior split.
- Add holdout and cross-domain validation commands to docs.
- Add acceptance gates and expected signatures.
- `2026-02-15`: Completed (commit hash: `pending-user-confirmation`).
- Verification:
  - `python3 -m pytest tracks/cli_sqlite/tests -q` (`49 passed`).
  - Added `docs/STRICT-TRANSFER-VALIDATION.md` with command matrix + expected signatures.
  - API-backed matrix executed on `2026-02-15` (strict in-domain `18001`, strict holdout `18002`, legacy sanity `18003`, cross-domain sessions `18100`-`18107`).

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
