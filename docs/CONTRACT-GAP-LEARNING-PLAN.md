# Contract-Gap Learning Upgrade (CLI Memory V2)

## Summary

We will improve learning quality by making failures explicit and machine-actionable.

Core change: before the agent stops, run a deterministic contract-gap check, return exact missing requirements, allow one focused retry, then write structured lessons tied to concrete failure codes.

This keeps behavior scalable across domains because it learns from invariant failure structure (`reason_code + gap_type`) instead of prompt wording.

## Scope and Success Criteria

1. Scope is only `tracks/cli_sqlite` (no FL/VM work).
2. Learning success requires all three:
   - Transfer pass-rate lift on hard tasks.
   - `lesson_activations > 0`.
   - Positive `retrieval_help_ratio` lift over run index.
3. Milestone gate: reach at least 80% on the two hard transfer tasks in learning-on mode before running expensive ablations.

## Implementation Plan

### 1) In-loop deterministic contract-gap checker with one retry

1. Reuse deterministic evaluator logic in `tracks/cli_sqlite/eval_cli.py` and expose a reusable function that returns unresolved gaps as structured JSON.
2. Add a pre-stop hook in `tracks/cli_sqlite/agent_cli.py`: when the model intends to stop (or stalls), run the gap check.
3. If unresolved gaps exist and retry budget is unused, inject the unresolved-gap payload into executor context and force exactly one targeted retry step.
4. Guardrails: one retry max, no retry loop, skip retry when no steps remain.
5. Persist artifacts:
   - `contract_gap_prestop.json`
   - `contract_gap_postretry.json`

### 2) Make lessons failure-structured (not generic)

1. Extend lesson schema in `tracks/cli_sqlite/lesson_store_v2.py` with:
   - `reason_code`
   - `gap_type`
   - `task_id`
   - `domain`
   - `gap_signature`
   - `source_session`
   - `status` (`candidate|promoted|suppressed`)
2. Enforce write-time validation for promotion-eligible lessons: `reason_code` and `gap_type` required.
3. Keep backward compatibility by allowing old lessons and marking them `legacy_unstructured`.

### 3) Retrieval should prioritize unresolved gaps

1. Update scoring in `tracks/cli_sqlite/lesson_retrieval_v2.py` priority order:
   - Exact `domain + reason_code + gap_type + task_family`
   - `domain + reason_code + gap_type`
   - `reason_code + gap_type`
   - fallback semantic score
2. Include unresolved gaps from pre-stop checker in retrieval query input.
3. Add retrieval metrics:
   - `retrieval_gap_queries`
   - `retrieval_gap_hits`
   - `retrieval_help_ratio`

### 4) Promotion only when targeted gap disappears

1. Update `tracks/cli_sqlite/lesson_promotion_v2.py`:
   - Promote only when matching `gap_signature` disappears in subsequent successful validation for that task family.
2. If the same gap repeats, keep candidate unpromoted and increment suppression counters.
3. Add reason-coded rejection telemetry:
   - `reject_digest_mismatch`
   - `reject_duplicate_jaccard`
   - `reject_replace_miss`
   - `reject_parse_fail`
   - `reject_gap_not_resolved`

### 5) Guarantee end-of-run lesson finalization

1. In `tracks/cli_sqlite/agent_cli.py`, finalize lessons on all terminal paths:
   - success
   - max-steps
   - early-stop
   - retry-exhausted
2. If model lesson output is invalid, create deterministic fallback lessons from unresolved gaps (template-based).
3. Persist:
   - `posttask_lessons_raw.json`
   - `posttask_lessons_applied.json`

### 6) Scalable cross-domain path (JSON-first, DB-later)

1. Add lightweight domain registry file:
   - `tracks/cli_sqlite/learning/domains.json`
2. Unknown-domain onboarding flow:
   - Create provisional domain profile (data only, no codegen).
   - Attach docs retrieval brief and generic contract validators.
3. Store docs in the existing artifacts pipeline and pass same docs to executor and judge.

### 7) Keep docs context symmetric between executor and judge

1. Ensure identical selected docs/chunks are persisted and passed when `--executor-docs on` and `--judge-docs on`.
2. Enforce prompt artifact bundle fields in `prompt_artifacts.json`:
   - executor system prompt
   - executor task payload
   - docs passed
   - selected lessons
   - skill list
   - judge system prompt
   - judge payload
   - judge docs context

## Public Interface / Flags

1. Keep existing flags.
2. Add:
   - `--contract-gap-retry on|off` (default: `on`)
   - `--contract-gap-retry-steps <int>` (default: `1`, hard-capped to `1`)
   - `--structured-lessons-required on|off` (default: `on`)

## Test Plan

1. Unit test: pre-stop gap checker returns deterministic unresolved gaps on failing fixtures.
2. Unit test: one retry is injected exactly once when unresolved gaps exist.
3. Unit test: lesson write rejects promotion-eligible lessons missing `reason_code` or `gap_type`.
4. Unit test: retrieval ranking prefers exact gap matches over semantic-only matches.
5. Unit test: promotion occurs only after gap-disappearance evidence.
6. Unit test: finalizer runs on every terminal path and emits fallback lessons when parse fails.
7. Integration test: hard task session with known contract misses improves after retry and writes structured lessons.
8. Full suite:
   - `python3 -m pytest tracks/cli_sqlite/tests -q`

## Benchmark Protocol (post-implementation)

1. Run learning-on only first (no ablations yet), hard tasks only:
   - `sqlite/incremental_reconcile`
   - `shell/shell_git_transfer_hotfix`
2. Run 10 sessions each, step cap 6, API `claude-haiku-4-5`.
3. Report per-session:
   - pass/fail
   - median steps
   - repeated-error-rate
   - unresolved-gap-count
   - lesson_activations
   - retrieval_help_ratio
4. Milestone pass condition:
   - each hard transfer task reaches >=80% in the last 5 sessions
   - lesson activations non-zero
   - retrieval_help_ratio delta positive
5. Only then run docs/lessons ablations.

## Assumptions and Defaults

1. Deterministic contract specs remain source of truth for pass/fail.
2. Infra-invalid runs (lock/capture/tool outages) are excluded from learning claims.
3. JSON storage remains primary in this milestone; DB migration deferred.
4. Executor prompt remains stable; only lessons/docs/gap payload vary.
5. One retry step is intentionally strict to limit token/time blowups.
