# Telegram-Cortex Integration Plan (80/20)

Owner: Cortex core
Status: done
Scope: thin integration only (no new memory algorithms)

## North Star

User sends a normal Telegram message -> Cortex decides/executes -> lessons persist -> repeated similar messages improve.

## Why this plan

We need real-world learning data without contaminating benchmark evidence.
So we isolate runtime artifacts by lane:
- benchmark/programmatic lane (default)
- Telegram lane (`runtime/telegram`)

This keeps ON/OFF benchmark signals clean while still allowing live bot learning.

## Architecture decision: vendored copy vs subtree

Decision: vendored copy (current repo path: `integrations/cortex-telegram-agi-bot`)

Why:
1. Faster right now: zero git subtree workflow overhead.
2. We need Cortex-specific bridge behavior, not upstream parity.
3. Less moving parts while proving product loop.

Tradeoff:
- Upstream sync is manual (acceptable for current phase).

## Implementation checklist

1. Runtime lane isolation in Cortex CLI track
- Add lane-aware path resolver.
- Keep default paths unchanged when lane is empty.
- Telegram lane writes under:
  - `tracks/cli_sqlite/runtime/telegram/sessions`
  - `tracks/cli_sqlite/runtime/telegram/learning`

2. Dispatcher lane enforcement
- Dispatcher defaults to `CORTEX_RUNTIME_LANE=telegram`.
- Run-service state/lifecycle files moved to same lane.
- Child runner process inherits lane env vars.

3. Telegram frontend bridge wiring
- Bridge explicitly passes `CORTEX_RUNTIME_LANE` to dispatcher.
- `.env.example` documents lane variable.

4. Documentation update
- Telegram README points verification commands to lane paths.

5. Validation
- Unit tests pass.
- Dispatcher dry-run shows lane=telegram.
- Live smoke creates session + lessons in telegram lane only.

Completed evidence (2026-03-01):
- Tests:
  - `python3 -m pytest tracks/cli_sqlite/tests/test_runtime_paths.py tests/test_openclaw_agi_dispatch.py -q` -> `23 passed`
  - `cd integrations/cortex-telegram-agi-bot && bun run typecheck` -> passed
- Non-dry natural-language smoke via dispatcher:
  - command: `python3 integrations/openclaw_agi_dispatch.py --chat-id tg-final-smoke --text "Import a CSV of sales events into SQLite. Deduplicate by event_id, track rejects, and return category totals. Use only 5 steps."`
  - result: `runtime_lane=telegram`, `attempts=3`, `ok=true`
  - run IDs: `run_1772371227042_00000048`, `run_1772371271829_00000075`, `run_1772371306392_00000076`
  - session IDs: `1035`, `1062`, `1063`
  - artifacts confirmed:
    - `tracks/cli_sqlite/runtime/telegram/sessions/session-1035/metrics.json`
    - `tracks/cli_sqlite/runtime/telegram/sessions/session-1062/metrics.json`
    - `tracks/cli_sqlite/runtime/telegram/sessions/session-1063/metrics.json`
    - `tracks/cli_sqlite/runtime/telegram/learning/lessons_v2.jsonl`

## Acceptance criteria

1. Natural-language message (no slash) can route to Cortex run mode.
2. Session artifact appears in:
   `tracks/cli_sqlite/runtime/telegram/sessions/session-XXX/metrics.json`
3. Lesson artifact appears in:
   `tracks/cli_sqlite/runtime/telegram/learning/lessons_v2.jsonl`
4. Default benchmark roots remain unaffected:
   `tracks/cli_sqlite/sessions` and `tracks/cli_sqlite/learning`

## Out of scope (explicitly)

- OpenClaw runtime cutover
- New lesson formats or memory algorithms
- Multi-agent orchestration changes
