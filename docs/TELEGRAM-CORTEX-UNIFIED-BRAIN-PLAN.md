# Telegram Cortex Unified Brain Plan

## Objective

Make `tracks/cli_sqlite` the only execution/learning brain for live Telegram task-mode.

Practical translation:
1. Telegram and OpenClaw stay thin transports.
2. Cortex owns execute, verify, judge, lesson write, and artifacts.
3. Live chat testing uses the same path as benchmark runs, so improvements transfer automatically.

## Current State (As Implemented)

Current task-mode path:
1. Telegram text handler checks `maybeHandleCortexRoute` in `integrations/cortex-telegram-agi-bot/src/integrations/cortex/router.ts`.
2. Router sends `/run` or `/learnstatus` to `runCortexDispatch` in `integrations/cortex-telegram-agi-bot/src/integrations/cortex/bridge.ts`.
3. Bridge spawns `python3 integrations/openclaw_agi_dispatch.py`.
4. Dispatcher parses controls (`domain`, `steps`, `model`, `backend`, `learn`) and runs `tracks/cli_sqlite/scripts/run_cli_agent.py`.
5. Summary is returned to Telegram from dispatcher JSON.

What is already good:
1. Cortex is already the learning source of truth.
2. `learn=off` exists for safe live smoke runs.
3. Authorization, rate limit, path guardrails, and timeout knobs exist in Telegram config.
4. OpenClaw has isolated profile setup and can call the same dispatcher.

Main gaps:
1. No first-class run lifecycle object for cancellation/steering (`/stop` does not control Cortex run subprocess reliably).
2. No streaming progress from Cortex run to Telegram while task is running.
3. Session IDs are epoch-second based, which is collision-prone under concurrency.
4. Observability is split across audit logs and session artifacts with no unified run ledger.

## Target Architecture

## Core Principle

Keep transport dumb and deterministic. Put behavior in Cortex core once.

## Components

1. Transport adapters:
- Telegram adapter: accepts messages, enforces auth/rate/safety, forwards normalized run requests.
- OpenClaw adapter: same request/response contract as Telegram.

2. Cortex run service (new internal layer in `tracks/cli_sqlite`):
- `start_run(request) -> run_id`
- `get_run(run_id) -> state`
- `stream_run(run_id) -> event iterator`
- `cancel_run(run_id) -> accepted`
- `append_followup(run_id, text) -> accepted`
- `get_learning_status(scope) -> summary`

3. Existing CLI runner compatibility:
- `tracks/cli_sqlite/scripts/run_cli_agent.py` stays as CLI entrypoint.
- Internally, CLI entrypoint calls the same run service APIs instead of owning orchestration logic.

4. Artifact and telemetry layer:
- Existing `session-*/metrics.json`, `events.jsonl`, `memory_events.jsonl` stay.
- Add transport-facing run ledger for fast troubleshooting.

## Message Routing Contract

## Inbound Message Classes

1. `run`:
- Explicit: `/run ...`
- Confirmed auto-route: plain text task intent + user confirms

2. `status`:
- `/learn-status`, `/learnstatus`, `/learn_status`

3. `chat`:
- Everything else

## Run Control Syntax (keep deterministic)

Accepted front controls from `/run` payload:
1. `domain=<sqlite|gridtool|fluxtool|artic|shell>`
2. `steps=<2..20>`
3. `model=<executor model id>`
4. `backend=<anthropic|claude_print>`
5. `learn=<on|off>`
6. `task_id=<known task id>` optional

Tail text after controls is task text. If no known `task_id`, dispatcher creates deterministic dynamic task id scoped by chat.

## Response Contract

All transport callers receive JSON with:
1. `mode` (`run` | `status` | `chat`)
2. `ok` boolean
3. `run_id` (new canonical identifier)
4. `session_id`
5. `task_id`
6. `domain`
7. `metrics` subset (`eval_passed`, `eval_score`, `lesson_activations`, `v2_retrieval_help_ratio`)
8. `stdout_tail` and `stderr_tail` on failure

## Safety Toggles and Defaults

## Transport-Level Safety (Telegram/OpenClaw)

Required:
1. `TELEGRAM_ALLOWED_USERS` non-empty
2. OpenClaw AGI profile isolated from `~/.openclaw`

Recommended defaults for live testing:
1. `CORTEX_BRIDGE_ENABLED=true`
2. `CORTEX_CONFIRMATION_ENABLED=true`
3. `CORTEX_AUTO_TASK_ROUTING=true` only for canary users; otherwise use explicit `/run`
4. `RATE_LIMIT_ENABLED=true`
5. `CORTEX_BRIDGE_TIMEOUT_MS=420000`
6. Narrow `ALLOWED_PATHS` / `ALLOWED_PATHS_EXTRA` to minimum required

OpenClaw isolation controls:
1. `OPENCLAW_STATE_DIR=~/.cloudcode-telegrambot-cortex-agi`
2. dedicated `OPENCLAW_AGI_TELEGRAM_BOT_TOKEN`
3. optional strict allowlist with `OPENCLAW_AGI_ALLOW_FROM`

## Learning Safety

1. Default exploratory smoke runs use `learn=off`.
2. Enable `learn=on` only when verification path is confirmed stable.
3. Keep `--structured-lessons-required` and `--contract-gap-retry` enabled for task runs.
4. Retain `--posttask-mode direct` for live loop unless explicitly testing candidate queue behavior.

## Observability Plan

## Sources of Truth

1. Telegram audit log:
- `AI_RUNTIME_DIR/.../claude-telegram-audit.log` (`AUDIT_LOG_JSON=true` recommended for analysis)

2. Cortex run artifacts:
- `tracks/cli_sqlite/sessions/session-*/metrics.json`
- `tracks/cli_sqlite/sessions/session-*/events.jsonl`
- `tracks/cli_sqlite/sessions/session-*/memory_events.jsonl`
- `tracks/cli_sqlite/learning/lessons_v2.jsonl`

3. Dispatcher summary output:
- JSON payload returned to transports including `stdout_tail`, `stderr_tail`, and metrics snapshot

## New Observability Additions (Implementation Work)

1. Add `run_ledger.jsonl` under `tracks/cli_sqlite/sessions/` with one record per run:
- `run_id`, `chat_scope`, `transport`, `task_id`, `domain`, `learn_mode`, timestamps, exit state

2. Add run lifecycle events:
- `queued`, `started`, `step`, `contract_gap_retry`, `lesson_written`, `completed`, `failed`, `canceled`, `timed_out`

3. Add quick health script:
- Report last N runs, fail rate, cancel rate, timeout rate, learning write count, and retrieval help ratio trend

## Phased Rollout

## Phase 0: Baseline Freeze and Validation

Goal: establish known-good baseline before refactor.

Implementation:
1. Snapshot current dispatcher contract and sample payloads.
2. Run CLI tests: `python3 -m pytest tracks/cli_sqlite/tests -q`.
3. Run Telegram smoke:
- `/learnstatus`
- `/run domain=shell steps=2 learn=off print current working directory and list files`
4. Record baseline failure/timeout behavior.

Exit criteria:
1. Baseline commands succeed.
2. Current behavior documented with real payload examples.

## Phase 1: Run Service Extraction (No Behavior Change)

Goal: move orchestration into reusable Cortex module.

Implementation:
1. Introduce internal run service in `tracks/cli_sqlite`.
2. Refactor CLI script to call run service.
3. Refactor dispatcher to call run service instead of shelling core logic indirectly.
4. Keep external CLI arguments unchanged.

Exit criteria:
1. Existing CLI tests pass unchanged.
2. Dispatcher responses are backward compatible.
3. No duplicate orchestration logic in transport code.

## Phase 2: Lifecycle Controls (Cancel + Status Polling)

Goal: make live task runs controllable.

Implementation:
1. Add stable `run_id` and run registry keyed by `chat_scope`.
2. Add `cancel_run(run_id)` and chat-scope cancel shortcut.
3. Wire Telegram `/stop` to cancel active Cortex run for that chat.
4. Add `/run-status <run_id>` or equivalent route for long runs.

Exit criteria:
1. `/stop` cancels task-mode run within SLA.
2. Canceled runs write deterministic terminal state and partial artifacts.
3. No zombie subprocesses after cancel/timeout.

## Phase 3: Streaming Progress and Follow-up Steering

Goal: interactive live execution instead of fire-and-wait.

Implementation:
1. Stream run events from Cortex to Telegram (throttled updates).
2. Accept follow-up messages during active run and append as steering input.
3. Persist steering events in run artifacts.

Exit criteria:
1. User sees progress updates without waiting for final summary.
2. User can adjust run objective mid-flight.
3. Final summary includes steering and resulting metric impact.

## Phase 4: Learning Guardrails and Canary

Goal: prevent lesson pollution while enabling real learning.

Implementation:
1. Canary cohort runs with `learn=on`; broader users default to `learn=off`.
2. Add lesson write counters and rollback trigger when noise spikes.
3. Add per-chat or per-domain learning toggles if needed.

Exit criteria:
1. `learn=off` runs prove zero lesson writes.
2. Canary `learn=on` shows non-zero useful lesson activation without major regression.

## Phase 5: OpenClaw Parity

Goal: identical behavior between standalone Telegram frontend and OpenClaw ingress.

Implementation:
1. Point OpenClaw dispatcher path to same run service contract.
2. Reuse same run/status/cancel payloads.
3. Validate isolation and no impact on primary `~/.openclaw` profile.

Exit criteria:
1. Same task produces same metrics shape through both transports.
2. OpenClaw and standalone Telegram share one brain path and one observability model.

## Rollout Checklist

## Preflight

1. Verify AGI profile isolation (`scripts/openclaw_agi_setup.sh`, `scripts/openclaw_agi_start.sh`).
2. Confirm Telegram allowlist and token are scoped correctly.
3. Confirm `CORTEX_ROOT` and dispatcher path exist.
4. Ensure runtime directories are writable.

## Canary

1. Start with one allowed user and explicit `/run` only.
2. Keep `CORTEX_CONFIRMATION_ENABLED=true`.
3. Keep default `learn=off` for first batch.
4. Run 20 mixed tasks; inspect failures and artifacts.

## Enable Learning

1. Turn on `learn=on` for selected tasks/users.
2. Monitor lesson growth and retrieval-help metrics daily.
3. Revert to `learn=off` immediately if lesson quality degrades.

## Broader Rollout

1. Expand allowlist in small batches.
2. Optionally enable auto task routing only after false-positive rate is acceptable.
3. Keep rollback path documented and tested.

## Rollback

1. Set `CORTEX_BRIDGE_ENABLED=false` to hard-disable task-mode routing.
2. Force explicit `/run ... learn=off` if keeping run path alive without learning writes.
3. Revert dispatcher to last known good release tag/commit.

## Risks and Mitigations

1. Risk: `/stop` does not terminate long subprocess reliably.
- Mitigation: explicit run registry + process group kill + terminal state write.

2. Risk: dynamic task-id/session collisions under concurrent chats.
- Mitigation: replace epoch-only session id with monotonic + random suffix run id.

3. Risk: false auto-routing of normal chat into task mode.
- Mitigation: keep confirmation gate and conservative heuristics; require `/run` for non-canary users.

4. Risk: low-signal lessons pollute shared memory.
- Mitigation: default `learn=off` for smoke, canary gating for `learn=on`, anomaly alerts on lesson growth.

5. Risk: telemetry scattered across files slows incident response.
- Mitigation: add unified run ledger and single run_id across transport + Cortex artifacts.

## Acceptance Criteria

The plan is complete when all are true:

1. Unified brain:
- Telegram and OpenClaw task-mode both call the same Cortex run service contract.

2. Control:
- `/stop` cancels active task-mode runs for the same chat in under 5 seconds (p95).

3. Observability:
- Every run has one canonical `run_id` visible in transport logs and Cortex artifacts.

4. Safety:
- Unauthorized users cannot trigger runs.
- `learn=off` causes zero new lines in `tracks/cli_sqlite/learning/lessons_v2.jsonl`.

5. Learning signal quality:
- In canary `learn=on`, at least one domain shows positive trend in `lesson_activations` and `v2_retrieval_help_ratio` across repeated tasks, with no increase in hard failure rate versus baseline.

6. Operational readiness:
- Rollout and rollback can be executed from checklist without ad-hoc steps.
