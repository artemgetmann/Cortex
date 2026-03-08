SQLite task: partial_failure_recovery_strict.

Goal:
1) Import valid rows from `fixture.csv` into `transactions(txn_id, account, amount)`.
2) Route non-numeric amount rows into `error_log(txn_id, reason)` with exact reason `invalid_amount`.
3) Verify: 4 valid transactions, exact rejected ids, correct aggregates, transaction-safe execution.

Constraints:
- Use only run_sqlite, read_skill, and show_fixture tools.
- Read relevant skills before SQL execution.
- Keep SQL deterministic and concise.
