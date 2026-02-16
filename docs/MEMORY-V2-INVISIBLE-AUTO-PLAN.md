# Memory V2 Invisible Auto-Learning Plan

## Objective
Build a memory system that improves agent performance across chats without requiring users to understand memory internals. The system must:
- Learn from failures automatically.
- Reuse useful lessons automatically.
- Avoid cross-domain contamination.
- Stay domain-agnostic at the memory layer.

## Product Requirement
User experience target:
- User gives task in chat.
- Agent tries tools.
- Agent fails/succeeds.
- Memory updates happen silently.
- Next chat improves for related work.
- No user-facing "strict lane / transfer lane" controls required.

## Core Design Principles
1. Separate structural invalid input from runtime failure.
2. Keep memory capture generic (hard failure, constraint failure, no progress, efficiency regression).
3. Use deterministic metadata for safety (domain/task/tool/session), not model-authored tags as ground truth.
4. Allow transfer memory, but cap and downweight it unless strict memory is weak.
5. Promote lessons only when repeated outcome improvement is measurable.
6. Suppress lessons that are repeatedly retrieved but unhelpful.

## End-to-End Runtime Flow
1. Task intake:
- Input: user task text.
- System infers active execution context from selected tools and adapter metadata.

2. Pre-run retrieval:
- Pull candidate lessons before first action.
- Rank by fingerprint, tags, text similarity, reliability, recency.
- Primary source: active context matches.
- Secondary source: transfer pool (limited quota, lower score multiplier).

3. Step loop:
- Model proposes tool call.
- Validation gate runs before execution.
  - If invalid structurally: return validation error, do not execute tool.
  - If valid: execute tool.
- Runtime outcome processed:
  - Success: continue.
  - Failure: emit ErrorEvent(s), retrieve on-error hints, inject top hints.
- Repetition monitor:
  - If repeated fingerprint or error threshold reached, force short reflection turn before next tool execution.

4. End-of-run:
- Executor self-reflection generates candidate lessons.
- Candidate lessons upserted into v2 store with fingerprints/tags/metadata.
- Outcome updater computes utility over relevant runs.
- Promotion/suppression rules applied.

## Validation and Error Logic (Important)
Validation gate catches only structural issues:
- Missing required keys.
- Wrong top-level type.
- Empty required strings.
- Unknown keys when schema forbids extras.

Validation gate does NOT catch semantic/runtime correctness:
- Bad bash command syntax.
- SQL logic errors.
- Python exceptions.
- HTTP 4xx/5xx.
- Wrong business logic.

Those are handled by runtime failure capture:
- Tool returns error text/output.
- ErrorEvent fingerprint + tags created.
- Retrieval uses that signal to inject lessons.

## Retry Without Spending Step (Completed)
Goal: avoid wasting step budget on malformed tool payload loops.

Flow:
1. Model emits tool input.
2. If validation fails:
- Return structured validation error to model.
- Ask model to regenerate tool input immediately.
- Keep same step index (no step increment).
3. Retry cap:
- Max 2 validation retries for same step.
- After cap, force reflection turn, then continue normal loop.

Why this is tool-agnostic:
- It works on schema structure, not command semantics.
- Applies equally to `run_bash`, `run_sqlite`, `run_artic`, future tools.

## Automatic Context Scoping (No User Knobs)
Backend-only policy:
1. Compute active context key:
- Primary: execution tool family + adapter domain.
- Secondary: task cluster hash from task text + tool usage pattern.

2. Retrieval policy:
- Always attempt strict-context retrieval first.
- If strict yields low-confidence/low-count matches, automatically add transfer candidates with capped quota.
- No user flags in normal product mode.

3. Safety checks:
- Conflict resolver keeps higher-confidence lesson when contradictions exist.
- Transfer hints include lower trust score and can be suppressed faster if unhelpful.

## Lesson Schema Requirements
Each lesson record should include:
- `lesson_id`
- `status` (`candidate|promoted|suppressed|archived`)
- `rule_text`
- `fingerprints`
- `tags` (system tags + optional model tags)
- `domain_key` (system-computed context key)
- `task_cluster` (optional grouped task signature)
- `source_session_id`
- `retrieval_count`, `helpful_count`, `harmful_count`
- `conflicts_with` list
- `created_at`, `updated_at`

## Promotion / Suppression Policy
Promotion:
- Utility threshold met (>= 0.20) across >= 3 relevant runs.
- No major regressions.

Suppression:
- Retrieved >= 3 times with non-positive utility.
- Or loses contradiction resolution repeatedly.

Relevant run matching:
- Prefer same domain key.
- Include task cluster neighbors when strict sample is too small.

## Observability and Demo UX
Need human-readable timeline output per step:
- step number
- model attempt (full tool input)
- validation result
- execution result
- emitted ErrorEvent channels + fingerprint
- injected hints + source lesson IDs + lane label (internal)
- whether next step changed behavior

Expose three clear views:
1. Raw attempt trace.
2. Memory decisions trace (retrieve/inject/suppress/promote).
3. Outcome summary (pass rate, steps, errors, recurrence, help ratio).

## Benchmark Plan
Scenarios:
1. Interference/retention: `grid -> fluxtool -> excel -> sqlite -> grid`.
2. Hard-task pressure: low step budget (`max_steps=5`) repeated sessions.
3. Transfer comparison:
- Run A: strict-only backend policy.
- Run B: auto-transfer backend policy.

Metrics:
- pass_rate, score, mean_steps, tool_errors
- validation_retry_count
- fingerprint_recurrence_before/after
- lesson_activations
- retrieval_help_ratio
- promoted/suppressed counts
- transfer_activation_rate

Success criteria:
- Fewer wasted steps from malformed inputs.
- Lower fingerprint recurrence over runs.
- Equal or better pass rate with no contamination spikes.

## Implementation Status by Workstream
1. Runtime loop: completed.
- Same-step validation retry (`max=2`) with reflection fallback is live.
- Retry metrics are live (`tool_validation_retry_attempts`, `tool_validation_retry_capped_events`).

2. Retrieval policy: completed.
- Auto policy is live (`off|auto|always`) with strict-first default.
- Transfer lane in `auto` mode is evidence-gated to reduce low-signal cross-domain contamination.

3. Context inference: deferred (out of hackathon scope).
- Domain/task metadata scoping is live.
- Task-cluster derivation/persistence beyond current domain/task keys is intentionally deferred.

4. Observability: completed.
- Timeline now surfaces transfer policy, validation retry/cap stats, injected lessons, and lane labels.

5. Benchmarks: partial.
- Dedicated mixed-protocol one-command runner is implemented (`run_mixed_benchmark.py`).
- Transfer-pressure benchmark runner is implemented (`run_transfer_pressure.py`).
- High-N transfer-pressure sweeps are intentionally deferred for hackathon scope.

## Hackathon Scope Decisions
1. Transfer policy validation:
- Keep safety-first behavior; do not require proving aggressive cross-domain transfer gains for this demo.
- High-N transfer-pressure runs are optional and currently skipped.

2. Task-cluster inference:
- Deferred. Current domain/task scoping is sufficient for hackathon demo goals.

3. Demo priority:
- Live reproducibility of mixed protocol + timeline observability is the primary success criterion.

## Live Demo Script (Prepared)
Script:
- `tracks/cli_sqlite/scripts/run_hackathon_demo.sh`

Status:
- Created and documented.
- Not executed by assistant (manual run only).

What it does:
- Runs 3 sequential mixed-benchmark waves with stable flags.
- Wave 1 clears lessons (cold start).
- Waves 2 and 3 reuse memory from prior waves.
- Writes JSON artifacts for each wave to `/tmp` by default.
- Prints timeline commands for step-by-step narration in demo video.

Manual run:
- `bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh`
- Optional overrides:
  - `START_SESSION=56001`
  - `MAX_STEPS=5`
  - `OUTPUT_DIR=/tmp`

## Benchmark Status (Executed)
Executed mixed protocol in 3 waves using sessions:
- Wave 1: `51001..51005`
- Wave 2: `51101..51105`
- Wave 3: `51201..51205`

Results:
- Wave 1 pass rate: `20%` (1/5)
- Wave 2 pass rate: `80%` (4/5)
- Wave 3 pass rate: `100%` (5/5)
- Mean score: `0.421 -> 0.800 -> 1.000`
- Mean steps: `4.60 -> 3.80 -> 3.40`
- Transfer lane activations: `0` across all 15 runs (no observed cross-domain contamination in this sweep)

Interpretation:
- Memory-assisted improvement across repeated sessions is demonstrated.
- Auto transfer policy is currently conservative/safe in this benchmark (no transfer hints injected).

## Still Not Done
1. FL Studio / computer-use integration.
- Deferred to Phase 2 and not implemented in active code.

## Phase 2: FL Studio / Computer-Use Integration (Deferred)
Status:
- Deferred for current execution.
- Current implementation scope remains CLI Memory V2 (`tracks/cli_sqlite/`) only.

Phase 2 scope (when unblocked):
- Apply the same Memory V2 retrieval/capture/promotion pipeline to FL Studio computer-use runs.
- Capture `computer` tool failures (click misses, focus loss, invalid coordinates, no UI state change) as runtime ErrorEvents with stable fingerprints.
- Reuse lessons during active FL Studio sessions without adding user-facing memory controls.

Required interfaces:
- `computer_use.py` -> memory adapter event contract: structured action/outcome/error payload with tool name, action type, target coordinates, app focus state, and screenshot hash.
- `agent.py` loop -> retrieval hook parity with CLI path: pre-run hint retrieval and on-error hint injection.
- Outcome evaluator contract for computer-use tasks: deterministic or judge-assisted success signal per run so utility and promotion logic remain measurable.

Success criteria for enabling Phase 2:
- Lower repeated computer-use failure fingerprints across repeated FL Studio sessions.
- Equal or better task completion rate with no increase in cross-task contamination.
- Observable trace parity with CLI demo (attempt -> failure -> injected hint -> corrected action).
- No new user-facing knobs; context scoping remains backend-only (`auto_context`).

## Risks
- Over-reliance on deterministic context keys can reduce transfer.
- Over-transfer can reintroduce contamination.
- Reflection turns may increase latency.
- Candidate lesson quality may be noisy without stronger filters.

## Mitigations
- Strict-first retrieval plus capped transfer quota.
- Conflict-aware ranking and fast suppression.
- Keep reflection threshold conservative.
- Maintain reliable system tags; treat model tags as soft only.

## Real-World / Robot Applicability
The same memory pipeline works if tools are replaced with robot actions, but evaluation must be explicit:
- Tool layer = robot capabilities (move arm, grasp, camera check, etc.).
- Runtime failure capture = actuator/sensor/controller errors or failed preconditions.
- Success measurement = referee checks observable outcomes (state checks, sensors, vision, or judge model).
- Memory lessons = corrective rules tied to failure fingerprints and context.

Important distinction:
- Memory capture does not require human-written error strings.
- Reliable "task succeeded" still needs an evaluator signal (deterministic checks, judge model, or both).

## Execution Decisions (Locked)
1. Default runtime mode:
- `auto_context`.
2. Validation retry cap:
- `2` retries on the same step, then reflection fallback.
3. Reflection trigger:
- `repeat fingerprint once` OR `>=3 hard failures`.
4. Transfer quota:
- `1` hint max per on-error retrieval initially.
5. Demo benchmark target:
- mixed protocol: `grid -> fluxtool -> excel -> sqlite -> grid`.
