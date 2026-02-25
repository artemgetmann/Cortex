# Cortex vs Voyager: 80/20 AGI Plan (Copy Principles, Not the Whole Stack)

Date: 2026-02-25

## Decision

Do not copy Voyager end-to-end.

Copy the 20% of ideas that drive 80% of learning lift for Cortex's goal:

- task-agnostic learning from failures,
- transfer across domains,
- measurable improvement over repeated runs.

## 80/20 for This Project (Plain Version)

80/20 here means:

- keep what increases learning speed and transfer quality,
- drop what is domain-specific or tied to Minecraft internals,
- ship smallest useful version first, benchmark, then expand.

If a component does not improve cross-domain learning metrics, we do not keep it.

## What to Copy from Voyager

## 1) Semantic memory retrieval [meaning-based lookup]

Why this is high value:

- lexical matching misses paraphrased failures,
- semantic lookup increases reuse of past fixes across different wording.

Implementation direction:

1. Add optional semantic index for lessons and doc chunks.
2. Blend semantic score with existing strict safety gates.
3. Keep default off until benchmark win is proven.

## 2) Adaptive curriculum [next task chosen by learning need]

Why this is high value:

- fixed task order wastes runs on solved tasks,
- planner should focus unresolved gaps and weak transfer zones.

Implementation direction:

1. Add planner that picks next task from unresolved gap signatures and recent failures.
2. Add `--curriculum-mode fixed|auto`.
3. Compare auto vs fixed on the same seeds.

## 3) Lightweight episodic state [small reusable run memory]

Why this is high value:

- agent repeatedly re-derives known context (paths, schema facts, failed command variants),
- tiny state reuse removes repeated setup errors.

Implementation direction:

1. Add scoped episodic store with TTL and size caps.
2. Start with `shell` and `sqlite` only.
3. Inject compactly into prompts with strict token budget.

## What Not to Copy from Voyager

1. Minecraft-specific environment wrappers and control primitives.
2. Multi-agent orchestration that increases complexity before proof of gain.
3. Any subsystem that weakens Cortex's current reliability gates.
4. Heavy infra dependencies before we pass benchmark thresholds.

Reason:

Those are not the core learning mechanism for Cortex's 0->1 objective.

## Cortex-First Guardrails (Non-Negotiable)

1. Reliability spine stays intact:
   - promotion/suppression logic,
   - contract-gap retry,
   - strict/transfer lane controls.
2. New memory paths must be benchmark-gated.
3. No feature graduates to default-on without measurable lift.

## Revised Priority Order (80/20)

Phase A: Hardening first (1-2 days)

1. Lesson-store atomic write + file lock (prevent memory loss during parallel runs).
2. Add learning telemetry needed to prove transfer and first-success speed.

Phase B: Core lift (3-5 days)

1. Semantic retrieval module behind feature flag.
2. Benchmark strict baseline vs semantic-on.

Phase C: Adaptive loop (3-5 days)

1. Curriculum planner (fixed vs auto mode).
2. Minimal episodic state for `shell` + `sqlite`.

Phase D: Keep or kill (1-2 days)

1. Keep only changes that beat baseline.
2. Remove/disable anything with neutral or negative impact.

## Keep-or-Kill Metrics

A feature survives only if it helps these:

1. repeated error fingerprint rate: down >= 15%.
2. first-success session index: improved >= 10% on >= 2 domains.
3. strict benchmark pass-rate: no regression.
4. lesson store integrity under concurrency: zero lost writes in stress test.

## Concrete File Targets

- `tracks/cli_sqlite/lesson_store_v2.py` (atomic + lock)
- `tracks/cli_sqlite/run_observability.py` (additional learning metrics)
- `tracks/cli_sqlite/scripts/report_run_health.py` (transfer/first-success summaries)
- `tracks/cli_sqlite/lesson_retrieval_v2.py` (semantic blending with safety gates)
- `tracks/cli_sqlite/scripts/run_learning_curve.py` (curriculum modes)
- new: `tracks/cli_sqlite/semantic_index.py`
- new: `tracks/cli_sqlite/curriculum_planner.py`
- new: `tracks/cli_sqlite/episodic_state.py`

## Worktree Rule (Implementation Hygiene)

Implement in a dedicated worktree only:

- `/Users/user/Programming_Projects/Cortex/.worktree/voyager`
- branch: `feat/voyager-gap-plan-20260225`

## Final Step

When the accepted phases are complete and benchmarks pass, merge this worktree branch back into `main`.
