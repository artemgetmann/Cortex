# Phase 2/3 Dispatcher Runbook

Scope: command-level verification for `integrations/openclaw_agi_dispatch.py`.

## Preconditions
- Run from repo root: `/Users/user/Programming_Projects/Cortex`
- Python available as `python3`
- For safe verification, prefer `--dry-run` and `learn=off`

## Command Checklist

1. `/run` (dry-run, explicit `run_id`)
```bash
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-e2e-phase23 \
  --dry-run \
  --text "/run run_id=run_e2e_phase23_001 domain=shell steps=2 learn=off print current working directory and list files"
```
Expected JSON fields:
- `mode: "run"`
- `plan.mode: "run"`
- `plan.run_id` equals requested run id
- `result.ok: true`
- `result.dry_run: true`
- `result.command` (array for `run_cli_agent.py`)
- `result.session_id` (integer)

2. `/status` for a `run_id`
```bash
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-e2e-phase23 \
  --text "/status run_id=run_e2e_phase23_001"
```
Expected JSON fields:
- `ok: true`
- `mode: "status"`
- `run_id` echoes request
- `run` object or `null`
- `active_runs` (array)
- `lessons_total` (integer)
- `lessons_scoped` (integer)
- `latest_session.task_id|domain|eval_passed|eval_score|lesson_activations|v2_retrieval_help_ratio`

3. `/run-status` (Phase 3 progress mode)
```bash
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-e2e-phase23 \
  --text "/run-status run_id=run_e2e_phase23_001 progress=on limit=6"
```
Expected JSON fields:
- `ok: true`
- `mode: "status"`
- `run_id` echoes request
- `progress_mode: true`
- `progress_limit: 6` (or clamped value in 1..20)
- `lifecycle_events` array with per-event fields:
  - `ts`
  - `event`
  - `step`
  - `trigger`
  - `session_id`
  - `task_id`
  - `domain`
- note: `run-status` defaults to progress mode unless explicitly disabled.

4. `/cancel` for a `run_id`
```bash
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-e2e-phase23 \
  --text "/cancel run_id=run_e2e_phase23_001"
```
Expected JSON fields:
- Success path: `ok: true`, `mode: "cancel"`, `run_id`, `run` object
- Not-found path: `ok: false`, `mode: "cancel"`, `run_id`, `error: "run_id not found"` and process exit code `1`
- Missing id path: `ok: false`, `error: "Missing run_id. Usage: /cancel run_id=<run_id>"`, exit code `1`

5. `/followup` steering for an active `run_id`
```bash
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-e2e-phase23 \
  --text "/followup run_id=run_e2e_phase23_001 Add a retry before final verification"
```
Expected JSON fields:
- Success path: `ok: true`, `mode: "followup"`, `run_id`, `accepted: true`
- Success path includes `result.followups` with appended steering entries
- Missing id path: `ok: false`, `mode: "followup"`, `error: "Missing run_id. Usage: /followup run_id=<run_id> <text>"`, exit code `1`
- Missing text path: `ok: false`, `mode: "followup"`, `error: "Missing follow-up text..."`, exit code `1`
- Not-found path: `ok: false`, `mode: "followup"`, `run_id`, `error: "run_id not found"`, exit code `1`

6. `/learn-status`
```bash
python3 integrations/openclaw_agi_dispatch.py \
  --chat-id tg-e2e-phase23 \
  --text "/learn-status"
```
Expected JSON fields:
- Same shape as `/status`
- `mode: "status"`
- `run_id: null` unless provided

7. `/stop` behavior note
- Dispatcher does not implement a `/stop` mode; direct `/stop` input falls back to chat payload (`mode: "chat"`).
- Telegram bot `/stop` is transport-level query interruption in `integrations/cortex-telegram-agi-bot/src/handlers/commands.ts` (`handleStop`), intentionally silent.
- For dispatcher-run cancellation, use `/cancel run_id=<run_id>`.
