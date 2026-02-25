# Telegram Transport Canary (Phase 4/5 Readiness)

Date: 2026-02-25  
Repo: `/Users/user/Programming_Projects/Cortex`  
Dispatcher: `integrations/openclaw_agi_dispatch.py`

## Scope

Command-level canary checks for:

- `/run` (dry-run)
- `/run-status` (progress mode)
- `/followup`
- `/cancel`

## Isolation

To avoid touching shared run-service state, all dispatcher calls were run with isolated env vars:

- `CORTEX_RUN_SERVICE_STATE_PATH=/tmp/cortex_telegram_canary_1772026206/run_service_state.json`
- `CORTEX_RUN_SERVICE_LIFECYCLE_PATH=/tmp/cortex_telegram_canary_1772026206/run_lifecycle.jsonl`

## Commands And Output Summary

1. `/run` dry-run

```bash
CORTEX_RUN_SERVICE_STATE_PATH=/tmp/cortex_telegram_canary_1772026206/run_service_state.json \
CORTEX_RUN_SERVICE_LIFECYCLE_PATH=/tmp/cortex_telegram_canary_1772026206/run_lifecycle.jsonl \
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-canary-phase45 \
  --dry-run \
  --text "/run run_id=run_canary_phase45_dry_001 domain=shell steps=2 learn=off print current working directory and list files"
```

Output summary:

- exit code: `0`
- `mode: "run"`
- `plan.mode: "run"`
- `plan.run_id: "run_canary_phase45_dry_001"`
- `result.ok: true`
- `result.dry_run: true`
- `result.command`: present (runner command array)
- `result.session_id: 1000`

Result: `PASS`

2. Seed active run for positive `/followup` and `/cancel` checks

```bash
CORTEX_RUN_SERVICE_STATE_PATH=/tmp/cortex_telegram_canary_1772026206/run_service_state.json \
CORTEX_RUN_SERVICE_LIFECYCLE_PATH=/tmp/cortex_telegram_canary_1772026206/run_lifecycle.jsonl \
python3 - <<'PY'
from tracks.cli_sqlite import run_service
run_service.start_run(
    task_id="shell_git_transfer_hotfix",
    domain="shell",
    session_id=9901,
    run_id="run_canary_phase45_live_001",
    metadata={"source": "telegram_transport_canary"},
)
print("seeded")
PY
```

Output summary:

- stdout: `seeded`
- exit code: `0`

3. `/followup`

```bash
CORTEX_RUN_SERVICE_STATE_PATH=/tmp/cortex_telegram_canary_1772026206/run_service_state.json \
CORTEX_RUN_SERVICE_LIFECYCLE_PATH=/tmp/cortex_telegram_canary_1772026206/run_lifecycle.jsonl \
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-canary-phase45 \
  --text "/followup run_id=run_canary_phase45_live_001 Add a retry before final verification"
```

Output summary:

- exit code: `0`
- `mode: "followup"`
- `ok: true`
- `accepted: true`
- `run_id: "run_canary_phase45_live_001"`
- `result.followups`: appended with source `transport:tg-canary-phase45`

Result: `PASS`

4. `/run-status` progress mode

```bash
CORTEX_RUN_SERVICE_STATE_PATH=/tmp/cortex_telegram_canary_1772026206/run_service_state.json \
CORTEX_RUN_SERVICE_LIFECYCLE_PATH=/tmp/cortex_telegram_canary_1772026206/run_lifecycle.jsonl \
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-canary-phase45 \
  --text "/run-status run_id=run_canary_phase45_live_001 progress=on limit=6"
```

Output summary:

- exit code: `0`
- `mode: "status"`
- `ok: true`
- `run_id: "run_canary_phase45_live_001"`
- `progress_mode: true`
- `progress_limit: 6`
- `lifecycle_events`: contains followup event with:
  - `event: "followup"`
  - `trigger: "transport:tg-canary-phase45"`
  - `session_id: 9901`
  - `task_id: "shell_git_transfer_hotfix"`
  - `domain: "shell"`

Result: `PASS`

5. `/cancel`

```bash
CORTEX_RUN_SERVICE_STATE_PATH=/tmp/cortex_telegram_canary_1772026206/run_service_state.json \
CORTEX_RUN_SERVICE_LIFECYCLE_PATH=/tmp/cortex_telegram_canary_1772026206/run_lifecycle.jsonl \
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-canary-phase45 \
  --text "/cancel run_id=run_canary_phase45_live_001"
```

Output summary:

- exit code: `0`
- `mode: "cancel"`
- `ok: true`
- `run_id: "run_canary_phase45_live_001"`
- `run.status: "cancel_requested"`
- `run.cancel_requested: true`
- `run.cancel_reason: "transport_requested"`

Result: `PASS`

## Pass/Fail Matrix

| Check | Status |
|---|---|
| `/run` dry-run contract | PASS |
| `/followup` append contract | PASS |
| `/run-status` progress contract | PASS |
| `/cancel` state transition contract | PASS |

Overall Phase 4/5 transport canary verdict: `PASS`.
