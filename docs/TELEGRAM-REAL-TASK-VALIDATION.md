# Telegram Real-Task Validation Runbook

Goal: verify memory helps on real natural-language Telegram tasks with a clean ON/OFF protocol.

## Scope

- Surface: `integrations/cortex-telegram-agi-bot`
- Brain: `tracks/cli_sqlite`
- Runtime lane: `telegram` (`CORTEX_RUNTIME_LANE=telegram`)

## New Controls

Use these in Telegram chat with the AGI bot:

- `/validation status`
- `/validation auto`
- `/validation on attempts=3 steps=6`
- `/validation off attempts=3 steps=6`

How it works:

- `auto`: normal behavior (default memory settings inferred by dispatcher).
- `on`: natural-language task routing injects `learn=on`.
- `off`: natural-language task routing injects `learn=off`.
- `attempts` and `steps` are optional lane overrides for natural-language task routing only.
- Explicit `/run ...` and `/learnrun ...` commands are respected as typed.

## Real-Task A/B Protocol

1. Choose 1 task family and write 10 natural-language variants.
2. Set OFF lane:
   - `/validation off attempts=3 steps=6`
3. Send all 10 prompts (natural language, no slash commands).
4. Set ON lane:
   - `/validation on attempts=3 steps=6`
5. Re-send the same 10 prompts (same order).
6. Compare OFF vs ON on:
   - pass rate
   - first-attempt pass rate
   - attempts to success
   - error count
   - lesson activations
   - retrieval help ratio

## Evidence Locations

- Session artifacts:
  - `tracks/cli_sqlite/runtime/telegram/sessions/`
- Run lifecycle log:
  - `tracks/cli_sqlite/runtime/telegram/sessions/run_lifecycle.jsonl`
- Memory:
  - `tracks/cli_sqlite/runtime/telegram/learning/lessons_v2.jsonl`

## Pass/Fail Bar

Treat validation as successful only if ON beats OFF on outcome metrics (not just activation counts).

- required: ON pass rate > OFF pass rate
- required: ON median attempts to success < OFF
- expected: non-zero useful activations on ON (`retrieval_help_ratio > 0`)

