---
name: sqlite-incremental-reconcile-nano
description: Lightweight dedupe + reject workflow for nano benchmark transfer runs.
version: 1
---

# Incremental Reconcile Nano

Use this skill for `incremental_reconcile_nano`.

## Core Rules

- Read from `fixture_seed`.
- `event_id` is the dedupe key.
- Keep only first-seen rows in `ledger`.
- Send duplicates to `rejects` with reason `duplicate_event`.

## Minimal Flow

1. Insert non-duplicate rows into `ledger`.
2. Insert duplicate rows into `rejects`.
3. Verify deterministic totals:
   - `SELECT category, SUM(amount) AS total FROM ledger GROUP BY category ORDER BY category;`
   - `SELECT COUNT(*) FROM rejects WHERE reason = 'duplicate_event';`

## Guardrails

- Do not delete from `ledger`.
- Do not drop `ledger`.
- Keep SQL deterministic across reruns.
