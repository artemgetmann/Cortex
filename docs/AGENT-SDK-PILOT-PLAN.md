# Agent SDK Pilot Plan (Implementation Brief)

Status: planning + scaffold only (no production runtime wiring)  
Owner: user + Codex  
Last updated: 2026-02-16

## Objective
- Ship an API-first pilot that runs through Anthropic Agent SDK while using `memory.usemindmirror.com` as the memory backend.
- Preserve Memory V2 behavior signals from the current CLI harness so we can compare run quality apples-to-apples.

## Minimum Architecture (Parity Floor)
1. Agent loop runtime:
   - Agent SDK conversation loop becomes the execution runtime.
   - Keep domain adapter semantics for task fixtures + executor command contract.
2. Memory capture path (must keep all three):
   - `error`: raw tool failure text.
   - `state`: run context (`task_id`, `domain`, `step`, tool name, mode).
   - `action`: attempted tool payload/command.
3. Retrieval injection points:
   - Pre-run retrieval (lesson preload into prompt/context).
   - On-error retrieval (fingerprint/tag aligned hints injected immediately after failed tool step).
4. Judge path:
   - Deterministic evaluator first when contract exists.
   - LLM judge fallback on contract failure.
   - LLM judge primary when no contract exists.
5. Observability parity:
   - Session-level events log with step/tool/error/hints.
   - Metrics including lesson activations, fingerprint recurrence, help ratio, and eval source.

## Current CLI Loop -> Agent SDK Loop Mapping
| Current CLI Harness (`agent_cli.py`) | Agent SDK Pilot Target |
| --- | --- |
| Build system prompt + lessons (`retrieve_pre_run`) | Build Agent SDK context with pre-run memory retrieval from `memory.usemindmirror.com` |
| `client.messages.create(...)` loop | Agent SDK run/continue loop with tool-use turn handling |
| Adapter `execute(...)` tool call | Agent SDK tool handler delegates to same domain adapter command path |
| On error: fingerprint + tags (`build_error_fingerprint`, `extract_tags`) | Same capture payload shape before memory write/retrieval |
| On error retrieval (`retrieve_on_error`) and hint injection | Query memory API for top lessons and inject hint block into next turn context |
| Contract eval + `llm_judge(...)` fallback | Same policy, executed after Agent SDK run completion |
| V2 lesson/outcome updates | Initially no-op or stub call; keep interface boundary explicit for later parity pass |

## Risks
- API transport mismatch can drop structured fields and weaken fingerprint quality.
- Agent SDK tool message format may differ enough to break strict step accounting.
- Memory API latency/retries can inflate step budget and hide true model behavior.
- Judge path drift can produce non-comparable scores vs current benchmark harness.
- Pilot may accidentally be treated as production path before parity gates are met.

## Acceptance Checks
1. Pilot script runs in dry mode without changing existing CLI benchmark behavior.
2. Capture payload schema includes `error`, `state`, and `action` for each executor error.
3. Retrieval occurs at both required points: pre-run and on-error.
4. Post-run report states evaluation source clearly: `contract`, `judge_fallback`, or `judge_primary`.
5. For identical task/session settings, pilot emits events/metrics artifacts with fields needed to compute:
   - lesson activation count,
   - fingerprint recurrence before/after,
   - retrieval help ratio.
6. Pilot remains explicitly non-production until these checks pass on at least one API task and one file task.
