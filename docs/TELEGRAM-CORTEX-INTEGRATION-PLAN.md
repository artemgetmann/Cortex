# Telegram ↔ Cortex Integration Plan

## Goal

Use Telegram as a frontend while Cortex stays the only learning brain.

That means:
- one core loop (`execute -> judge -> lesson -> persist -> retry`)
- one lesson store
- one retrieval path
- no duplicate logic in separate bot repos

## Architecture

1. Telegram transport receives user message.
2. Transport maps message to Cortex dispatcher protocol (`/run`, `/learn-status`, `/chat`).
3. Dispatcher invokes `tracks/cli_sqlite/scripts/run_cli_agent.py`.
4. Cortex artifacts/lessons are written in Cortex paths.
5. Transport returns structured result summary to Telegram.

## Why this is correct

- If Cortex logic improves, Telegram behavior improves automatically.
- No porting step is required.
- No OpenClaw dependency is required for this path.

## Current implementation

- `integrations/telegram_cortex_gateway.py`
  - Telegram long polling
  - allowlist enforcement
  - auto-run mapping for plain text
  - dispatch to `integrations/openclaw_agi_dispatch.py`
- `scripts/telegram_cortex_bot_start.sh`
  - minimal start wrapper
- `integrations/telegram-cortex-bot/README.md`
  - runbook + protocol

## Testing protocol

1. Stop any other process using the same Telegram token.
2. Start bridge with token + allowed users.
3. Send `/run shell_git_transfer_hotfix`.
4. Send `/run domain=shell steps=2 learn=off print current directory and list files`.
5. Send `/learn-status`.

## Next step (optional, if needed)

If you still want to keep the existing `claude-code-telegram-bot` UX layer, add a thin pass-through mode there that forwards text to this bridge instead of model inference. Keep forwarding-only logic in that bot; keep learning logic in Cortex.
