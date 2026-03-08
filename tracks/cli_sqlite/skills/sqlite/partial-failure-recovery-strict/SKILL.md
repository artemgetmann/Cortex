---
name: sqlite-partial-failure-recovery-strict
description: Validate numeric amounts before insert, route bad rows to error_log with exact reason invalid_amount, and use a transaction.
version: 1
---

# Partial Failure Recovery Strict

Use this skill for `partial_failure_recovery_strict` tasks.

## Critical Semantics

- Fixture contains non-numeric `amount` values.
- Valid rows go to `transactions`.
- Bad rows must go to `error_log(txn_id, reason)` with exact reason `invalid_amount`.
- Do not silently coerce bad data to 0.

## Required Flow

1. Read `fixture.csv`.
2. Start a transaction (`BEGIN IMMEDIATE` or `BEGIN TRANSACTION`).
3. Insert only numeric rows into `transactions`.
4. Insert invalid rows into `error_log` with exact reason `invalid_amount`.
5. Commit.
6. Verify:
- `SELECT COUNT(*) FROM transactions;`
- `SELECT COUNT(*) FROM error_log;`
- `SELECT txn_id, reason FROM error_log ORDER BY txn_id;`
- `SELECT account, SUM(amount) AS total FROM transactions GROUP BY account ORDER BY account;`

## Guardrails

- Tables are already created by bootstrap.
- Do not drop or delete from `transactions` or `error_log`.
- Every fixture row must end up in exactly one table.

## Tool Reference

- `dispatch(sql="...")` — executes SQL against the task database.
- `probe(skill_ref="...")` — reads a skill document by reference key.
- `catalog(path_ref="...")` — shows fixture or bootstrap data by path reference.
