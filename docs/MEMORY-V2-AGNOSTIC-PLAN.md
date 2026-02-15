# Memory V2 Agnostic Plan (Executor + Referee + Learning Memory)

## Goal

Build a domain/task-agnostic memory system that:
1. Captures repeated failures as structured events.
2. Learns reusable lessons automatically.
3. Retrieves the right lessons at the right time.
4. Promotes useful lessons and suppresses harmful ones.
5. Preserves old knowledge while learning new tools/tasks.

This plan intentionally does not depend on task-specific contracts to function.

## Architecture Decisions (locked)

### Runtime roles

- `executor`: executes tools and solves tasks.
- `referee`: independent scorer.
  - deterministic evaluator if available.
  - LLM judge fallback if deterministic evaluator is unavailable.
- no separate required `critic` role in hot path.

### Memory representation

Use a hybrid model:
1. **Atomic lesson text** (human-readable rule).
2. **Connection graph metadata** (machine-usable associations).

Each lesson stores:
- trigger fingerprints (normalized recurring errors),
- tags (domain-agnostic failure semantics),
- tool/domain/task scope,
- reliability/impact scores,
- conflict links.

This keeps lessons interpretable while enabling graph-style retrieval (HippoRAG-like association behavior without full KG/PPR complexity in v1).

## Core Logic

### 0) Universal feedback interface (not CLI-only)

Every domain adapter must expose the same four feedback channels:
1. `hard_failure`: binary signal (exception, non-zero exit, API/tool error, safety violation).
2. `constraint_failure`: required condition not met (wrong output shape, missing artifact, invariant broken).
3. `progress_signal`: scalar distance/progress metric toward goal (can be heuristic).
4. `efficiency_signal`: steps/time/cost.

This makes "mistake detection" task-agnostic. CLI parser errors are only one source of `hard_failure`.

Examples:
- CLI: syntax error, exit code, failed query, wrong table output.
- Robot navigation: collision, no distance reduction to target room, repeated stuck state.
- FL Studio/computer-use: target BPM/pattern not reached, repeated ineffective UI actions, safety guard hit.

### 1) Domain-agnostic error capture

On each failed step (from `hard_failure` or `constraint_failure` or "no progress"):
1. Build `error_fingerprint` from available evidence:
   - normalize error text if available,
   - otherwise normalize failed state-transition signature (`state_before + action + state_after + failure_reason`),
   - lowercase,
   - strip volatile literals/paths/numbers,
   - keep structural failure language (`syntax`, `unknown`, `missing`, `expected`, `not found`, `stuck`, `no_progress`, `constraint_failed`).
2. Extract generic tags from error text and action/state context:
   - `syntax_structure`, `unknown_symbol`, `path_quote`, `operator_mismatch`, `arity_mismatch`, `column_reference`, `function_case`, `sort_direction`, `unknown_command`, etc.
   - add non-CLI tags: `no_progress`, `constraint_failed`, `state_stall`, `unsafe_action`, `goal_distance_increase`.
3. Write `ErrorEvent` to `memory_events.jsonl` with:
   - fingerprint,
   - tags,
   - action attempted,
   - local outcome deltas (progress/efficiency/constraint flags).

No command-name regex table is required for this path.

### 2) Candidate lesson generation

End of run:
1. Group errors by fingerprint.
2. Prioritize recurring fingerprints (count >= 2 in a run or repeated across runs).
3. Ask executor model for strict JSON lesson candidates:
   - `trigger_fingerprint(s)`
   - `rule_text` (WRONG -> CORRECT form when possible)
   - `scope_hint` (`task|domain|global`)
4. Store as `status=candidate`.

### 3) Retrieval (how system knows memory is relevant)

Two retrieval points:
1. **Pre-run**: retrieve top-K lessons by task intent + domain + recent failure context.
2. **On-error**: retrieve by exact fingerprint match first, then fallback ranking.

Ranking:

`score = 0.40*fingerprint_match + 0.25*tag_overlap + 0.20*text_similarity + 0.10*reliability + 0.05*recency`

Guards:
- max lessons per prior session,
- max lessons per tag bucket,
- exclude suppressed/archived lessons,
- contradiction resolution by higher reliability + newer evidence.

### 4) Promotion (usefulness test)

#### When deterministic evaluator exists

Promote candidate if, across at least 3 relevant runs:
1. error recurrence for its fingerprints drops materially (target >= 50%), and
2. either pass-rate or score improves, with no major regression.

#### When deterministic evaluator does not exist

Use proxy utility from independent referee + runtime signals.
This is the default path for unseen tasks.

`utility = 0.65*error_reduction + 0.35*step_efficiency_gain` if only runtime/referee-lite is available.

If LLM referee is available:

`utility = 0.50*error_reduction + 0.30*step_efficiency_gain + 0.20*referee_score_gain`.

Promote if:
- utility >= 0.20,
- evidence window >= 3 runs,
- no major regressions.

How "positive utility" is computed in real-world/no-contract settings:
1. Track each lesson activation event.
2. For each activation, compare short-horizon outcomes against baseline:
   - did matched fingerprint recurrence drop?
   - did progress improve after activation?
   - did extra failures decrease?
3. Aggregate over runs into lesson-level utility.
4. Promote only if aggregated utility stays positive and stable across independent runs.

### 5) Suppression (harmfulness test)

A lesson is suppressed if:
- it was retrieved >= 3 times, and
- utility for those activations is non-positive (<= 0), or
- it participates in a contradiction cluster and consistently loses to an alternative lesson.

Suppressed lessons remain in store for audit, but are excluded from retrieval.

Interpretation in no-contract tasks:
- "non-positive utility" means lesson activations did not improve recurrence/progress/efficiency over repeated opportunities.
- This avoids requiring a pre-programmed evaluator for every new task.

### 6) Dedup + contradiction + lifecycle

- dedup by normalized rule text + trigger signatures.
- conflict linking for lessons that share triggers but propose incompatible fixes.
- aging/pruning:
  - archive low-reliability unused lessons after threshold,
  - never hard delete by default.

## Answering the scalability problem

This scales across tasks/domains because:
1. trigger representation is error-structure-based, not command-name-based,
2. utility is outcome-based, not task-template-based,
3. retrieval uses fingerprints+tags+similarity+reliability, not fixed task IDs,
4. suppression prevents memory pollution from growing unchecked.

## Unseen-task adaptation flow (explicit)

When user gives a task the system has never seen:
1. Use docs/internet/context to attempt execution (executor behavior).
2. Run feedback interface (`hard_failure`, `constraint_failure`, `progress`, `efficiency`) at each step.
3. First run builds initial error map (fingerprints + tags).
4. Generate candidate lessons from repeated failures and failed transitions.
5. Next runs retrieve those lessons and re-attempt.
6. Promote/suppress based on measured utility, not handcrafted task logic.

This is the core autonomous learning loop: attempt -> detect failure/progress -> store -> retrieve -> verify impact.

## Experimental protocol (locked to your requested flow)

### Phase A: Docs-enabled bootstrap (teach tool syntax fast)

1. Gridtool run with docs enabled.
2. Next gridtool run uses memory; expect fewer steps/errors.

### Phase B: New tool acquisition

1. Fluxtool first run (cold-ish), with docs allowed.
2. Fluxtool next runs: memory should reduce steps/errors and stabilize pass.

### Phase C: Retention check

1. Switch back to gridtool after fluxtool learning.
2. Validate gridtool stays efficient (no catastrophic forgetting).

### Phase D: Cross-task within same tool

1. Run a different task in gridtool and fluxtool.
2. Measure whether memories transfer partially and adapt, not just overfit.

### Required metrics per run

- pass/fail, score,
- steps,
- tool_errors,
- lesson_activations,
- fingerprint recurrence,
- promoted/suppressed counts,
- retrieval precision proxy:
  - activated_lessons_that_helped / activated_lessons_total.

## Implementation workstreams

1. Add `error_capture.py` (fingerprint + tag extraction + event logging).
2. Add `lesson_store_v2.py` (candidate/promoted/suppressed schema + dedup/conflicts).
3. Add `lesson_retrieval_v2.py` (pre-run + on-error ranking).
4. Add `lesson_promotion_v2.py` (utility windows + promotion/suppression).
5. Integrate V2 path in `agent_cli.py` behind flag, then default-on.
6. Add benchmark scripts:
   - `run_memory_stability.py`,
   - `report_memory_health.py`.
7. Document results in `docs/AB-FINDINGS.md` and a new memory benchmark doc.

## Acceptance criteria

1. Works without task-specific deterministic contracts.
2. On at least one new tool/task, recurrence of key errors decreases over runs.
3. After learning tool B, tool A performance does not materially regress.
4. Suppression activates on at least one harmful or contradictory lesson in stress test.
5. Memory retrieval remains high signal (activation helps more often than harms).

## Non-goals (for this phase)

- full HippoRAG/PPR implementation,
- external vector DB migration,
- web-scale knowledge graph extraction.

These can be phase-2 upgrades after memory health is proven with this lightweight hybrid.

## Implementation status (2026-02-15)

Implemented in `exp/memory-v2-agnostic`:

- [x] Universal failure capture module (`tracks/cli_sqlite/error_capture.py`)
  - fingerprint normalization from error/state/action
  - generic tag extraction for CLI and non-CLI contexts
  - channelized event representation + serialization
- [x] Lesson store V2 (`tracks/cli_sqlite/lesson_store_v2.py`)
  - JSONL lifecycle states: `candidate|promoted|suppressed|archived`
  - dedup + conflict-linking + archive support
  - legacy adapter/migration helper for `learning/lessons.jsonl`
- [x] Retrieval V2 (`tracks/cli_sqlite/lesson_retrieval_v2.py`)
  - pre-run + on-error retrieval
  - weighted ranking formula from this plan
  - guards for session/tag caps and conflict-aware selection
- [x] Promotion/suppression V2 (`tracks/cli_sqlite/lesson_promotion_v2.py`)
  - utility formulas with/without referee score
  - promotion and suppression gates from this plan
- [x] Agent loop integration (`tracks/cli_sqlite/agent_cli.py`)
  - failed-step ErrorEvent capture
  - on-error retrieval + hint injection
  - end-of-run candidate generation + utility update
  - deterministic evaluator + LLM judge behavior preserved
- [x] Benchmark tooling
  - `tracks/cli_sqlite/scripts/run_memory_stability.py`
  - `tracks/cli_sqlite/scripts/report_memory_health.py`
- [x] Tests added
  - `tracks/cli_sqlite/tests/test_error_capture_v2.py`
  - `tracks/cli_sqlite/tests/test_lesson_memory_v2.py`
