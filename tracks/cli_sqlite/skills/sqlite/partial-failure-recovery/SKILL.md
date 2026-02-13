---
name: sqlite-partial-failure-recovery
description: Handle bad data rows by routing errors to error_log while importing valid rows.
version: 1
---

# Partial Failure Recovery

Use this skill for `partial_failure_recovery` tasks.

## Critical Semantics

- Fixture contains rows with non-numeric `amount` values (e.g., `INVALID`, `BAD_DATA`).
- Valid rows must be inserted into `transactions`.
- Bad rows must be logged into `error_log` with the `txn_id` and a descriptive `reason`.
- Do NOT skip bad rows silently — they must appear in `error_log`.

## Required Flow

1. Read `fixture.csv` with `show_fixture` to inspect the data.
2. Tables are pre-created by bootstrap:
   - `transactions(txn_id TEXT PRIMARY KEY, account TEXT, amount INTEGER)`
   - `error_log(txn_id TEXT, reason TEXT)`
3. For each fixture row, check if `amount` is a valid integer.
4. If valid: `INSERT INTO transactions(txn_id, account, amount) VALUES (...)`.
5. If invalid: `INSERT INTO error_log(txn_id, reason) VALUES ('T003', 'non_numeric_amount')`.
6. Verify:
   - `SELECT COUNT(*) FROM transactions;` → 4
   - `SELECT COUNT(*) FROM error_log;` → 2
   - `SELECT account, SUM(amount) AS total FROM transactions GROUP BY account ORDER BY account;`

## Common Failures

- Treating non-numeric amounts as 0 instead of routing to `error_log`.
- Forgetting to log bad rows, resulting in error_log count = 0.
- Attempting to cast `INVALID` to integer, causing SQL errors.

## Guardrails

- Never drop `transactions` or `error_log`.
- Every fixture row must end up in exactly one table (transactions or error_log).
- Validate amounts before attempting INSERT into transactions.

## Tool Reference

- `dispatch(sql="...")` — executes SQL against the task database.
- `probe(skill_ref="...")` — reads a skill document by reference key.
- `catalog(path_ref="...")` — shows fixture or bootstrap data by path reference.
