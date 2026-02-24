# Cortex Telegram Bridge

This is a direct Telegram ingress for Cortex learning runs.

It does not require OpenClaw. It uses the same core dispatcher:
`integrations/openclaw_agi_dispatch.py`.

Why this setup:
- Cortex remains the single source of truth for learning behavior.
- Telegram is just transport (ingress/egress).
- Any change in `tracks/cli_sqlite` is reflected immediately in bot behavior.

## Safety

- If another process is already running on the same Telegram bot token, stop it first.
- Use `TELEGRAM_ALLOWED_USERS` to enforce a strict allowlist.
- Use `/run ... learn=off` for smoke tests without lesson writes.

## Start

```bash
cd /Users/user/Programming_Projects/Cortex
export TELEGRAM_BOT_TOKEN="YOUR_EXISTING_BOT_TOKEN"
export TELEGRAM_ALLOWED_USERS="1336356696"
./scripts/telegram_cortex_bot_start.sh
```

Optional:

```bash
export CORTEX_TELEGRAM_AUTO_RUN=1
export CORTEX_TELEGRAM_RUN_TIMEOUT_S=2400
export CORTEX_TELEGRAM_STATE_PATH=/Users/user/Programming_Projects/Cortex/integrations/telegram-cortex-bot/state.json
```

## Message protocol

- `/run shell_git_transfer_hotfix`
- `/run domain=shell steps=6 build a hotfix flow and verify status`
- `/run domain=shell steps=2 learn=off print current dir and list files`
- `/learn-status`
- Plain text:
  - If `CORTEX_TELEGRAM_AUTO_RUN=1`, plain text is converted to `/run <text>`.
  - If `CORTEX_TELEGRAM_AUTO_RUN=0`, plain text is ignored unless prefixed with `/run`.
