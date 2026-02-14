---
name: sqlite-incremental-reconcile
description: Stateful ingest workflow with dedupe, rejects, and checkpoint logging.
version: 1
---

# Incremental Reconcile

Use this skill for `incremental_reconcile` tasks.

## Critical Semantics

- Use checkpoint tag: `CKP-APR-01`
- Source rows are available in `fixture_seed`.
- `event_id` is the idempotency key.
- Duplicate rows must be written to `rejects` with reason `duplicate_event`.

## Required Flow

1. Start transaction (`BEGIN TRANSACTION`).
2. Insert first-seen rows from `fixture_seed` into `ledger` with checkpoint tag `CKP-APR-01`.
3. Insert duplicate rows into `rejects` with reason `duplicate_event`.
4. Upsert one row in `checkpoint_log` with checkpoint tag and inserted row count.
5. Commit transaction (`COMMIT`).
6. Verify aggregate output with deterministic ordering:
- `SELECT category, SUM(amount) AS total FROM ledger GROUP BY category ORDER BY category;`

## Guardrails

- Never delete from `ledger` to satisfy dedupe.
- Never drop `ledger`.
- Keep behavior idempotent across reruns.

## Tool Reference

- `dispatch(sql="...")` — executes SQL against the task database.
- `probe(skill_ref="...")` — reads a skill document by reference key.
- `catalog(path_ref="...")` — shows fixture or bootstrap data by path reference.
