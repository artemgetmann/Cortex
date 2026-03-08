---
name: sqlite-incremental-reconcile-replay-safe
description: Replay-safe incremental reconcile workflow with dedupe, invalid-amount rejects, and two-pass audit logging.
version: 2
---

# Incremental Reconcile Replay Safe

Use this skill for `incremental_reconcile_replay_safe` tasks.

## Critical Semantics

- Source rows are available in `fixture_seed`.
- `event_id` is the idempotency key for `ledger`.
- The same batch must be processed twice.
- Final state must stay replay-safe:
  - `ledger` still contains only the 4 accepted rows
  - `rejects` still contains only 2 rows total
  - `replay_log` contains exactly steps 1 and 2
  - `batch_audit` shows accepted `4`, rejected `2`, replay_count `2`

## Required Flow

1. Start one transaction.
2. Process pass 1 for batch tag `BATCH-REPLAY-01`.
3. Process pass 2 for the same batch tag `BATCH-REPLAY-01`.
4. Keep `ledger` idempotent by inserting first-seen valid rows only.
5. Keep `rejects` replay-safe so the second pass does not duplicate reject rows.
6. Write `replay_log(batch_tag, replay_step)` for steps `1` and `2`.
7. Upsert one `batch_audit` row with accepted `4`, rejected `2`, replay_count `2`.
8. Commit the transaction.
9. Verify all four deterministic checks:
   - `SELECT category, SUM(amount) AS total FROM ledger GROUP BY category ORDER BY category;`
   - `SELECT reason, COUNT(*) FROM rejects GROUP BY reason ORDER BY reason;`
   - `SELECT batch_tag, replay_step FROM replay_log ORDER BY replay_step;`
   - `SELECT batch_tag, accepted_count, rejected_count, replay_count FROM batch_audit ORDER BY batch_tag;`

## Guardrails

- Do not recreate or reshape the provided tables.
- Do not delete from `ledger`, `rejects`, or `replay_log`.
- `rejects` has no uniqueness constraint, so replay-safe behavior must come from your insert logic.
- Keep behavior deterministic and safe to repeat.

## Tool Reference

- `dispatch(sql="...")` — executes SQL against the task database.
- `probe(skill_ref="...")` — reads a skill document by reference key.
- `catalog(path_ref="...")` — shows fixture or bootstrap data by path reference.

## Learned Updates
- [2026-03-08] Enforce two-pass replay for batch BATCH-REPLAY-01 with idempotent ledger inserts (evidence steps: 2, 4)
- [2026-03-08] Deduplicate by event_id to keep ledger final state replay-safe (evidence steps: 2, 4)
- [2026-03-08] Route non-numeric amounts to rejects with reason invalid_amount and keep duplicates in rejects with reason duplicate_event (evidence steps: 2, 4)
