SQLite task: partial_failure_recovery.

Goal:
1) Import valid rows from `fixture.csv` into `transactions(txn_id, account, amount)`.
2) Some rows have non-numeric amounts — route those to `error_log(txn_id, reason)`.
3) Verify: 4 valid transactions, 2 error log entries, correct aggregates.

Constraints:
- Use only run_sqlite, read_skill, and show_fixture tools.
- Read relevant skills before SQL execution.
- Keep SQL deterministic and concise.
