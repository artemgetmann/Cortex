# Memory V2 Execution Plan (Living Doc)

Status: in-progress (execution started)  
Owner: user + Codex  
Last updated: 2026-02-16

## 1) Goal
Build a demo-ready memory system that is:
- transparent (people can see exactly what the agent saw/tried/failed/learned),
- robust (low contamination),
- useful on unseen tasks/tools (not locked to one toy task),
- measurable (clear pass/fail + utility metrics).

This document is the source of truth until user says: "use the plan document to execute."

## 2) Current State (Confirmed)
- Memory V2 capture/retrieval/promotion is integrated in `tracks/cli_sqlite/agent_cli.py`.
- On-error retrieval is now strict scoped by active `domain` and optional `task_id`.
- Timeline demo now shows:
  - full attempted commands per step,
  - error + injected hints,
  - optional non-executor events,
  - optional tool outputs,
  - lesson snapshot for the session domain/task.
- Hard-mode benchmark exists and produces failure/recovery trajectories.

## 2.1) Execution Log (2026-02-16)
- Phase 0 baseline capture: completed.
  - Artifacts:
    - `/tmp/memory_stability_30001_hard12.json`
    - `/tmp/memory_health_30001_hard12.json`
  - Baseline note: `docs/MEMORY-V2-BASELINE-2026-02-16.md`
  - Commit: `2c08e2d`
- Phase 1 observability hardening: completed.
  - Added explicit sections for preloaded vs on-error injected lessons and retrieval score breakdown in timeline.
  - Commit: `1616c16`
- Phase 2 clean Memory V2 demo mode: completed.
  - Added `memory_v2_demo_mode` flag to suppress legacy `posttask_hook`/`promotion_gate` in demo/benchmark runs.
  - Wired through `run_cli_agent.py`, `run_memory_stability.py`, and `agent_cli.py`.
  - Commit: `1616c16`
- Agent-SDK pilot preparation: started (planning + scaffold complete).
  - Added pilot brief and non-production scaffold runner.
  - Commit: `b1df824`
- Phase 3 strict+transfer retrieval lanes: completed.
  - Added two-lane on-error retrieval:
    - strict lane (domain/task scoped, primary),
    - transfer lane (cross-domain backfill, lower score weight, capped quota).
  - Added lane-level observability in event payload/timeline and metrics.
  - Added retrieval-lane tests and CLI flags to control transfer behavior.
  - Commit: `5782e95`
- Artic benchmark domain integration: completed.
  - Added `artic` adapter (`run_artic`) with HTTP/parse error surfacing and compact JSON output.
  - Added progressive Artic tasks (`artic_search_basic`, `artic_followup_fetch`, `artic_pagination_extract`).
  - Wired `--domain artic` into CLI and benchmark scripts.
  - Added adapter/timeline integration tests.
  - Commit: `5782e95`

## 3) Known Frictions
- Confusion between:
  - prompt preloaded lessons vs
  - on-error injected lessons vs
  - store snapshot shown for observability.
- Legacy skill-patching events (`posttask_hook`, `promotion_gate`) still appear in logs and distract from Memory V2 story.
- Strict retrieval removes contamination but may over-limit transfer.
- Deterministic contract evaluator is brittle for truly unseen tasks.

## 4) Decision Gates (Locked For Execution)

### DG-1: Legacy Posttask Path
Question: keep or remove `posttask_hook` + legacy `promotion_gate` from demo runs?

Options:
- A) Keep in code, hide in demo output by default.
- B) Keep in code, hard-disable for Memory V2 benchmark scripts.
- C) Remove entirely from CLI track.

Recommendation: B.  
Reason: preserve compatibility while making Memory V2 signal clean.

Decision: locked (B)

### DG-2: Demo Transparency Scope
Question: how explicit should the runtime trace be?

Minimum demo artifact should show, per run:
- exact system prompt sections (task, domain fragment, preloaded lesson IDs/text),
- every executor command attempt,
- every failure + fingerprint + tags,
- retrieval ranking and selected lessons,
- injected hint text at failure point,
- corrected attempt and outcome,
- end-of-run lesson generation + status transitions.

Decision: locked (approved as written)

### DG-3: Retrieval Strategy
Question: strict-only vs strict+transfer?

Options:
- A) strict-only (max safety, less transfer)
- B) two-lane retrieval:
  - lane 1: strict local (domain/task exact),
  - lane 2: transfer pool (cross-domain, lower weight, limited quota)
- C) open semantic retrieval only (high contamination risk)

Recommendation: B.

Decision: locked (B)

### DG-4: Evaluation for Unseen Tasks
Question: contract-first always, or judge-first for no-contract tasks?

Recommendation:
- If contract exists: deterministic first, judge fallback.
- If no contract: judge-first and treat as primary score.

Decision: locked (approved)

### DG-5: Tool Expansion Path
Question: keep custom adapters only, or migrate to Anthropic Agent SDK loop?

Recommendation:
- Agent-SDK-first for real-world execution.
- Keep current CLI adapter path as controlled benchmark harness and fallback until Agent-SDK path reaches parity on observability and memory hooks.

Decision: locked (Agent-SDK-first with controlled fallback)

## 5) Proposed Execution Phases

### Phase 0: Plan lock + baseline capture
Deliverables:
- decisions in DG-1..DG-5 locked,
- baseline benchmark/report artifacts captured for before/after comparison.

### Phase 1: Observability hardening (demo-first)
Scope:
- Add explicit preloaded-vs-injected lesson sections to timeline.
- Add retrieval score breakdown per injected lesson.
- Add optional prompt dump (sanitized) for each session.

Acceptance:
- A viewer can answer "what did model know before step 1?" in <30 seconds.

### Phase 2: Clean Memory V2 run mode
Scope:
- Add benchmark flag to suppress legacy skill-patch events or disable hooks in Memory V2 mode.
- Keep backward compatibility for old scripts.

Acceptance:
- Timeline contains only Memory V2 + executor/referee events in demo mode.

### Phase 3: Strict + Transfer retrieval lanes
Scope:
- Introduce transfer lane with hard caps and lower score weight.
- Keep strict lane as primary.
- Add contamination regression tests.

Acceptance:
- No obvious syntax bleed across tools,
- measurable improvement on cross-domain holdout vs strict-only baseline.
Status:
- Completed in current CLI harness (`5782e95`).

### Phase 4: Judge-first unseen-task protocol
Scope:
- explicit mode for no-contract tasks,
- reporting distinguishes deterministic vs judge-sourced score.

Acceptance:
- benchmark can run end-to-end without contracts for new tasks.

### Phase 5: Real-world tool pilot (Agent SDK path)
Scope:
- first pilot target is one Artic API task, then one file-manipulation task (xlsx or equivalent),
- memory capture/retrieval/promotion enabled,
- repeat-run improvement measured.
- Implementation brief + scaffold reference: `docs/AGENT-SDK-PILOT-PLAN.md` and `tracks/cli_sqlite/scripts/run_agent_sdk_pilot.py`.

Acceptance:
- run-2/3 show fewer repeated fingerprints and higher completion quality.
Status:
- In progress:
  - CLI-harness Artic domain is now integrated as the first real API benchmark target (`5782e95`).
  - Agent-SDK path remains planned/scaffolded, not yet the primary execution path.

### Phase 6: Agent-SDK migration decision
Scope:
- compare current CLI harness vs Agent-SDK path on:
  - observability parity,
  - memory hook parity,
  - benchmark reproducibility,
  - development velocity.

Acceptance:
- if parity reached, make Agent-SDK path primary for new domains/tools.
- keep existing harness for deterministic regression tests.

## 6) Anthropic Agent SDK Findings (for DG-5)
Primary-source findings:
- Agent SDK overview says it provides built-in tools, agent loop, and context management similar to Claude Code.
  - https://platform.claude.com/docs/en/agent-sdk/overview
- Python SDK reference distinguishes `query()` vs `ClaudeSDKClient`; only `ClaudeSDKClient` supports hooks/custom tools/continuation.
  - https://platform.claude.com/docs/en/agent-sdk/python
- Tool docs confirm Bash tool and Code Execution tool support shell/file workflows.
  - https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool
  - https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool
- Memory tool exists (beta), client-side backend required, can persist across conversations.
  - https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool

Implication:
- Yes, Agent SDK can reduce adapter/tool-wrapper burden for real-world tasks.
- For benchmark control and deterministic replay, custom adapters are still useful.
- Best path is hybrid architecture (controlled lab + Agent-SDK real-world track).

## 7) Metrics We Will Track
- pass/fail, eval score, steps, tool errors,
- fingerprint recurrence before/after,
- preloaded lessons count,
- on-error activations count,
- retrieval help ratio,
- promoted/suppressed/archived counts,
- contamination incidents (wrong-domain hint injection),
- judge-vs-deterministic score source.

## 8) Risks
- Overfitting to demo traces instead of robust policy.
- Too much strict scoping can suppress useful transfer.
- Judge-only evaluation can drift without rubric constraints.
- Mixed legacy/new learning paths can confuse metrics attribution.

## 9) Execution Start Checklist
Before implementation starts:
1. confirm Phase 1 starts first
2. confirm benchmark profile for baseline (`hard12` or custom)
3. confirm first Agent-SDK pilot target (API or XLSX)
   - locked ordering: Artic API first, XLSX/file-manip second.

## 10) Clarifications From Latest Review

### What timeline "lessons: total=N" means
- It is a store snapshot for the active domain/task.
- It does NOT mean all N were inserted into prompt context.
- Actual preloaded set is `metrics.v2_lessons_loaded` and `metrics.v2_prerun_lesson_ids`.
- On-error injected set is separate and happens only after a failed step.

### Bootstrap mode
- `--bootstrap` disables skill-doc guidance for executor behavior.
- Prior lessons still load (that is the memory learning path under bootstrap).

### Session 29006 interpretation
- Pre-run V2 lessons loaded: 2.
- Step 2 failed on `SORT ... desc`.
- On-error retrieval injected 2 hints.
- Step 3 corrected to `SORT ... down` and passed.
- End-of-run legacy `posttask_hook`/`promotion_gate` events are not the same as V2 promotion.

### Referee architecture
- Current runtime keeps executor + referee:
  - deterministic evaluator first when contract exists,
  - LLM judge fallback or primary when no contract exists.
- For unseen tasks without contracts, judge-first is the intended path.

### Lesson authoring logic
- V2 candidate lessons are generated by executor self-reflection.
- Candidates are stored first, then promoted/suppressed by measured utility over runs.
