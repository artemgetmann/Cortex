---
name: sqlite-incremental-reconcile-audit-transfer
description: Incremental reconcile workflow with dedupe, invalid-amount rejects, and batch audit logging.
version: 1
---

# Incremental Reconcile Audit Transfer

Use this skill for `incremental_reconcile_audit_transfer` tasks.

## Critical Semantics

- Source rows are available in `fixture_seed`.
- `event_id` is the idempotency key.
- Insert only the first valid row for each `event_id` into `ledger`.
- Duplicate rows go to `rejects` with reason `duplicate_event`.
- Rows with invalid amount values go to `rejects` with reason `invalid_amount`.
- Write one row into `batch_audit` with tag `BATCH-MAY-01`.

## Required Flow

1. Start transaction (`BEGIN IMMEDIATE` or `BEGIN TRANSACTION`).
2. Insert first-seen valid rows from `fixture_seed` into `ledger(event_id, category, amount, batch_id)`.
3. Insert invalid amount rows into `rejects(event_id, reason)`.
4. Insert duplicate rows into `rejects(event_id, reason)`.
5. Upsert one audit row into `batch_audit(batch_tag, accepted_count, rejected_count)`.
6. Commit transaction (`COMMIT`).
7. Verify all three deterministic checks:
- `SELECT category, SUM(amount) AS total FROM ledger GROUP BY category ORDER BY category;`
- `SELECT reason, COUNT(*) FROM rejects GROUP BY reason ORDER BY reason;`
- `SELECT batch_tag, accepted_count, rejected_count FROM batch_audit ORDER BY batch_tag;`

## Guardrails

- Do not recreate or reshape the provided tables.
- Do not delete from `ledger` or `rejects`.
- Do not invent extra columns in `rejects`; it only stores `event_id` and `reason`.
- Keep behavior idempotent across reruns.

## Tool Reference

- `dispatch(sql="...")` — executes SQL against the task database.
- `probe(skill_ref="...")` — reads a skill document by reference key.
- `catalog(path_ref="...")` — shows fixture or bootstrap data by path reference.
