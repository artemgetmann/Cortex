# OpenClaw AGI Bridge

This integration runs a second OpenClaw profile for live Telegram testing while keeping Cortex as the single source of truth for learning logic.

Design:
1. `~/.openclaw` (existing bot) remains untouched.
2. `~/.openclaw-agi` is an isolated runtime state for the AGI bot.
3. Workspace is inside Cortex for visibility:
   `/Users/user/Programming_Projects/Cortex/integrations/openclaw-agi/workspace`
4. OpenClaw calls the thin bridge script:
   `workspace/bin/cortex_openclaw_dispatch.sh`
5. Bridge executes Cortex runner directly:
   `tracks/cli_sqlite/scripts/run_cli_agent.py`

Result:
- Any improvement in Cortex learning code automatically applies to AGI bot runs.
- No double-maintenance between OpenClaw and Cortex.

## Quick Start

1. Prepare isolated runtime:
```bash
cd /Users/user/Programming_Projects/Cortex
./scripts/openclaw_agi_setup.sh
```

2. Enable dedicated Telegram bot token:
```bash
OPENCLAW_AGI_TELEGRAM_BOT_TOKEN="123:abc" ./scripts/openclaw_agi_setup.sh
```

Optional allowlist override:
```bash
OPENCLAW_AGI_ALLOW_FROM="1336356696,6783130823" ./scripts/openclaw_agi_setup.sh
```

3. Start AGI gateway:
```bash
cd /Users/user/Programming_Projects/Cortex
./scripts/openclaw_agi_start.sh
```

4. Verify profile isolation:
```bash
OPENCLAW_STATE_DIR=$HOME/.openclaw-agi OPENCLAW_CONFIG_PATH=$HOME/.openclaw-agi/openclaw.json openclaw gateway status
OPENCLAW_STATE_DIR=$HOME/.openclaw OPENCLAW_CONFIG_PATH=$HOME/.openclaw/openclaw.json openclaw gateway status
```

## Dispatcher Usage

Run from the AGI workspace:
```bash
cd /Users/user/Programming_Projects/Cortex/integrations/openclaw-agi/workspace
./bin/cortex_openclaw_dispatch.sh \
  --chat-id tg-1336356696 \
  --text "/run shell_git_transfer_hotfix"
```

Run an unseen task in dynamic mode:
```bash
./bin/cortex_openclaw_dispatch.sh \
  --chat-id tg-1336356696 \
  --text "/run domain=shell steps=6 build a git hotfix flow and verify final status"
```

Run safely without mutating shared lesson stores:
```bash
./bin/cortex_openclaw_dispatch.sh \
  --chat-id tg-1336356696 \
  --text "/run domain=shell steps=2 learn=off print current working directory and list files"
```

Inspect learning signals:
```bash
./bin/cortex_openclaw_dispatch.sh \
  --chat-id tg-1336356696 \
  --text "/learn-status"
```

## Notes

1. `setup` disables Telegram in AGI config unless a dedicated token is provided.
2. OAuth credentials are copied once into `~/.openclaw-agi/credentials/oauth.json` for convenience.
3. Runtime artifacts under `integrations/openclaw-agi/workspace` are gitignored.
4. Only `/run` triggers task mode; plain chat stays non-learning mode to avoid memory pollution.
