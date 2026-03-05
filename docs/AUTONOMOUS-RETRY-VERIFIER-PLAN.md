# Autonomous Retry + Verifier Plan

## North Star
Make Cortex behave like a real autonomous agent:
- do not stop on model confidence
- stop only on verifier pass or hard budget
- learn from each failed attempt
- solve repeated tasks faster over time

This plan is intentionally task/domain agnostic.

## Problem Statement
Current behavior can stop too early because:
1. Inner loop has tight step caps.
2. Model may output "done" before objective completion.
3. Verifier feedback is not yet the hard stop condition for all flows.

Result: GPT-5 nano can exit before closure, even when more retries would succeed.

## First-Principles Design
Use two loops, not one:

1. Inner loop (execution steps)
- model proposes actions
- action validator checks syntax/shape
- execute tool
- capture evidence/errors

2. Outer loop (attempt retries)
- run verifier at end of attempt
- if fail: extract gaps, write lessons, retry
- if pass: stop
- if budget exhausted: fail closed

Stop condition must be verifier truth, not model self-judgment.

## Why This Is AGI-Aligned
- Generic execution hygiene [valid tool calls] is universal.
- Gap extraction + structured lessons is universal.
- Retrieval by gap family (signature or reason+type) is universal.
- Domain specifics stay in tools/contracts, not in orchestration logic.

## What This Plan Adds
### A) Verifier-gated retry orchestrator (core)
Add an outer attempt loop around current run:
- `max_attempts` (default 3, configurable)
- `max_total_steps` (default 40, configurable)
- `max_wall_time_s` (default 900, configurable)

If verifier fails and budgets remain:
- create/update structured lessons
- retrieve top 1-3 targeted lessons
- run next attempt automatically

### B) Generic action validator (core)
Before tool execution:
- validate tool input schema
- run tool-specific parse sanity (syntax only, no task logic)
  - shell: parse/unmatched quote/backtick/obvious command token issues
  - sqlite: parse-level sanity / forbidden-op checks when configured

On validation fail:
- emit deterministic error code
- ask model to repair action in same step

### C) Structured lesson enforcement (core)
Require lesson shape:
- trigger: `reason_code`, `gap_type`, optional `gap_signature`
- action: `action_template`
- proof: `expected_evidence`

Promotion rules:
- promote only if targeted gap disappears after activation
- suppress if same lesson repeatedly precedes same-gap failure

### D) Adaptive lesson injection (already partially done, keep)
- inject 1-3 lessons per attempt (not fixed)
- one lesson per gap family
- block noisy legacy free-text hints in strict mode

### E) Observability for real proof (core)
Persist per attempt:
- `attempt_index`
- `attempt_passed`
- `attempt_steps`
- `attempt_error_count`
- `lessons_in`
- `lesson_activations`
- unresolved gap families before/after
- stop reason: `pass|budget_steps|budget_attempts|timeout|manual`

## Direct Answer to "Why Codex/Claude keep trying?"
They often have a stronger built-in agent loop:
- larger effective context/strategy quality
- better default retry behavior
- better self-check heuristics

Cortex must implement this loop explicitly to make weaker/cheaper models reliable.

## Experiments to Separate Root Causes
### Experiment 1: Step-cap sensitivity (no outer retries)
- same task, nano, steps: 6 vs 12 vs 20
- if success rises sharply with steps, cap is dominant blocker

### Experiment 2: Outer retry impact (fixed total budget)
- same total budget, compare:
  - single-attempt long run
  - multi-attempt verifier-gated retries
- if retries win, orchestration is dominant blocker

### Experiment 3: Model capability floor
- same orchestrator, nano vs stronger model
- if stronger model succeeds and nano doesn't, capability floor is real
- then decide whether to simplify tasks or use tiered model policy

## Worktree + Parallel Execution Plan
### Worktree A (orchestrator)
- outer retry loop
- stop reasons
- attempt budgets

### Worktree B (validator)
- generic action validator interface
- shell/sqlite syntax sanity adapters

### Worktree C (metrics/reporting)
- attempt-level metrics
- run summaries showing attempts-to-success

Merge order:
1. C first (safe visibility)
2. B second (execution safety)
3. A last (behavioral change)

## Acceptance Criteria
For one hard transfer slice:
1. Attempt 1 can fail.
2. Later attempt in same run passes via verifier.
3. `attempts_to_success` is tracked.
4. Lessons activated on failed attempts are visible.
5. Repeated runs show lower median attempts-to-success.

## Go/No-Go Rule
Go to larger benchmark only if smoke shows:
- verifier-gated retry converts at least one fail-first case to pass
- no infinite loops
- stable metrics with clear stop reason

No-Go if:
- retry loop churns without gap reduction
- validator blocks too aggressively
- metrics cannot explain outcomes

## Optional Phase: Agents SDK Spike (time-boxed)
Time-box: 1 day.
Goal: compare custom orchestrator vs Anthropic Agents SDK behavior on one identical task.
Decision:
- keep custom if it is clearer/cheaper/reliable enough
- adopt SDK if it gives cleaner autonomous retries with less code

This is a spike, not a migration commitment.
