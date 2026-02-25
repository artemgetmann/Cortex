# Cortex Learning Invariants

## Why this exists

This document defines the minimum conditions for claiming that Cortex is learning.
It is intentionally implementation-agnostic: we can change models, prompts, or tools, but these invariants must still hold.

## First-principles definition of learning

Learning means future behavior changes because of past failures.

For Cortex, that requires all three:

1. Failure is captured in a structured way.
2. Relevant memory is retrieved when a similar failure appears.
3. Retrieved memory changes execution before the run ends.

If any one is missing, we have logging, not learning.

## Non-negotiable invariants

1. Deterministic closure signal exists.
- Every task must have a deterministic contract/verifier.
- Pre-stop checks must enumerate unresolved gaps explicitly.

2. Lessons are structured, not generic.
- Lessons must include failure identity (reason code + gap type + signature).
- Lessons must support reliable retrieval and deduplication.

3. Retrieval is gap-targeted.
- Ranking must prioritize lessons matching unresolved gaps.
- Generic similarity alone is insufficient.

4. Learning is measured by mechanism activation.
- Pass/fail alone cannot prove learning.
- Required evidence includes lesson activations and retrieval-help lift.

5. Prompt stability is preserved during experiments.
- Executor prompt remains fixed across learning curves.
- Only lessons/docs context may vary, so lift is attributable.

## What does not count as learning

- One-off success without lesson activation.
- Success caused by easier tasks or loosened contracts.
- Improvements that disappear on transfer tasks.

## Decision rule for “learning improved”

Claim improvement only when:

1. Transfer performance improves over repeated runs.
2. Lesson activations are non-zero.
3. Retrieval help shows positive trend or clear positive delta.

If pass rate rises but mechanism metrics remain near zero, classify as ambiguous.

## Design direction

Use this as the architecture filter:

1. Improve memory quality (better structured failures/lessons).
2. Improve retrieval precision (gap-first retrieval).
3. Improve in-loop correction (deterministic closure before stop).

If a change does not improve one of these, it is likely noise.

## Current code audit vs Voyager (updated to current Cortex)

This section reflects the current implementation in `tracks/cli_sqlite`, not an older snapshot.

### Mechanism comparison

1. Deterministic closure before stop
- Voyager: critic LLM checks success.
- Cortex now: deterministic contract checks + unresolved gap extraction + pre-stop retry.
- Status: stronger than Voyager for verifiability.
- Code: `tracks/cli_sqlite/agent_cli.py`, `tracks/cli_sqlite/eval_cli.py`.

2. Structured failure identity
- Voyager: critique text, mostly unstructured.
- Cortex now: `reason_code`, `gap_type`, `gap_signature` stored in lessons.
- Status: stronger than Voyager for retrieval targeting.
- Code: `tracks/cli_sqlite/lesson_store_v2.py`, `tracks/cli_sqlite/agent_cli.py`.

3. Gap-aware retrieval
- Voyager: vector similarity over skill descriptions.
- Cortex now: retrieval scoring includes explicit unresolved-gap bonus and transfer gating.
- Status: stronger for failure-driven reuse.
- Code: `tracks/cli_sqlite/lesson_retrieval_v2.py`.

4. Documentation to executor and judge
- Voyager: fixed prompt + environment observations.
- Cortex now: docs pipeline with `none|lossy|full`, optional retrieval, docs artifacts persisted.
- Status: net-new capability beyond Voyager.
- Code: `tracks/cli_sqlite/docs_pipeline.py`, `tracks/cli_sqlite/agent_cli.py`, `tracks/cli_sqlite/scripts/run_cli_agent.py`.

5. Prompt and judging observability
- Voyager: console logs + checkpoint files.
- Cortex now: per-session `prompt_artifacts.json`, `learning_artifacts.json`, docs artifacts, judge input/result bundles.
- Status: stronger for auditability.
- Code: `tracks/cli_sqlite/agent_cli.py`.

6. Learning gate for claims
- Voyager: performance outcomes and ablations.
- Cortex now: explicit mechanism gate (activation and retrieval-help trend), not pass/fail only.
- Status: aligned with first-principles learning claims.
- Code: `tracks/cli_sqlite/scripts/run_realworld_learning_benchmark.py`.

### What is still missing (high impact)

1. Executable lesson recipes
- Current: lessons are mostly text rules.
- Missing: canonical `recipe_cmd` + `verify_cmd` blocks that can be executed directly.
- Why it matters: reduces interpretation errors and speeds retry quality.

2. Automatic failure-driven curriculum scheduler
- Current: benchmark runs are scripted by task list.
- Missing: scheduler that automatically selects next task by dominant unresolved failure signatures.
- Why it matters: better sample efficiency and less manual benchmark steering.

3. Step-level corrective memo
- Current: strong post-run artifacts and retry prompts.
- Missing: compact deterministic “what is still wrong right now” memo injected every step after each failed verification.
- Why it matters: prevents drift and repeated mistakes inside the same run.

4. Lesson store integrity guardrails
- Current: good telemetry and dedup/rejection counters.
- Missing: strict startup integrity checks that fail fast on index/store drift for all memory artifacts.
- Why it matters: prevents silent corruption from degrading retrieval over long runs.

## Why this is not “copying Voyager”

We are copying invariants, not implementation.

- We keep the same physics (capture -> retrieve -> behavior change -> verify).
- We keep Cortex-native architecture (contracts, gap taxonomy, docs pipeline, strict learning gate).
- We only adopt ideas that measurably improve those invariants.
