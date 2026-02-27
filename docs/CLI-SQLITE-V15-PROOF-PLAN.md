# CLI SQLite v1.5 Proof Plan

Status: active  
Owner: Cortex core loop  
North star: prove lessons improve outcomes with deterministic evidence before adding more architecture.

## 1) Locked Decisions

These are fixed for v1.5 proof mode:

1. New isolated path: `tracks/cli_sqlite_v15/`
2. Single backend: OpenAI only
3. Single model: `gpt-5-nano` only
4. Critic path: hard disabled
5. Self-edit path: hard disabled
6. `claude -p` / `claude_print`: not used for active benchmarks
7. Proof protocol order:
   - First: one-task smoke ON/OFF (`5 + 5`)
   - Then: scale only if smoke shows clean signal

## 2) Problem Statement

Current runs show a core failure mode:

- Lessons can activate, but outcomes do not improve reliably.
- In some slices, ON is equal to or worse than OFF.

Interpretation:

- The bottleneck is lesson quality/routing and evaluation discipline, not missing features.

## 3) v1.5 Design Goals

1. Deterministic and auditable:
   - Same task, same caps, same evaluator, clean reset each run.
2. Minimal moving parts:
   - One model path, one lesson system, one benchmark runner.
3. Causal attribution:
   - If ON beats OFF, we can explain why.
4. Cheap enough to iterate:
   - Smoke first, full protocol only after clear signal.

## 4) Keep / Cut / Postpone

### Keep (v1.5 core)

1. CLI task runner and domain adapters needed for sqlite/shell proof tasks
2. Deterministic contract evaluator
3. Lesson Store V2 (single source)
4. Minimal retrieval path with strict gating
5. Benchmark runner with ON/OFF paired protocol

### Cut from proof path (not necessarily delete yet)

1. Critic pipeline execution
2. Self-edit/skill mutation execution
3. Multi-model routing/orchestration
4. `claude_print` benchmark fallback
5. Non-deterministic grading as primary outcome

### Postpone

1. Cross-domain expansion beyond proof tasks
2. Advanced retrieval heuristics
3. Variant scoreboard tuning
4. Additional observability not tied to decisions

## 5) Required v1.5 Behavior

### 5.1 Strict lesson relevance gate

Inject a lesson only if:

1. `trigger_gap_signature` exists
2. Current unresolved gap signatures include that exact signature
3. Lesson passes schema/executability validation at retrieval time

### 5.2 Retrieval-time schema/executability gate

Reject lessons at retrieval when required fields are missing or invalid.
Generation-time validation alone is not enough.

### 5.3 Negative suppression

If lesson L is repeatedly activated for signature S and is followed by failure on S, auto-demote/ban L for S.

## 6) Evaluation Protocol

### Phase A: smoke (required first)

Task: one hard deterministic task  
Arms: ON vs OFF  
Runs: `5 + 5`  
Caps: fixed (same steps, same reset policy)

Go criteria to continue:

1. ON pass rate > OFF pass rate
2. ON lesson activations > 0
3. ON retrieval help ratio > 0
4. Activated ON runs outperform non-activated ON runs

If not met: iterate on lesson gates before scaling.

### Phase B: scale (only if Phase A passes)

Target protocol (initial):

1. Start with `10 + 10` on 1-2 tasks
2. Only then move toward larger protocol (e.g. multi-task batches)

Note: the old 120-run idea is deferred until Phase A/B show reliable positive signal.

## 7) Metrics That Decide Go/No-Go

Primary:

1. Pass rate delta (ON - OFF)
2. Last-5 pass rate delta

Mechanism:

1. Lesson activations
2. Retrieval help ratio
3. Activation quality check:
   - pass rate when activated vs when not activated (within ON arm)

Reliability:

1. Median steps to success
2. Failure taxonomy concentration by reason_code/gap_signature

## 8) Implementation Sequence

1. Create `tracks/cli_sqlite_v15/` with minimal runner path (openai + nano only)
2. Wire strict relevance gate
3. Wire retrieval-time schema gate
4. Wire negative suppression
5. Run Phase A smoke (`5 + 5`)
6. Review metrics and decide:
   - If green: run Phase B (`10 + 10`)
   - If red: patch gates/suppression and rerun smoke

## 9) Non-Goals (for v1.5)

1. Solving FL Studio automation quality
2. Multi-backend parity
3. Fancy benchmark dashboards
4. General AGI claims

## 10) Exit Condition for v1.5

v1.5 is done when:

1. ON consistently beats OFF on deterministic tasks
2. Mechanism metrics are non-zero and helpful (not harmful)
3. The result is reproducible across reruns without changing prompts

