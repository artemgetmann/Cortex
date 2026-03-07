SQLite task: incremental_reconcile_audit_transfer.

Goal:
1) Import rows from `fixture.csv` into `ledger`.
2) Deduplicate by `event_id` and store duplicate rows in `rejects` with reason `duplicate_event`.
3) Route rows with invalid amount values into `rejects` with reason `invalid_amount`.
4) Write one audit row into `batch_audit`.
5) Return deterministic aggregate totals by category.

Constraints:
- Use only run_sqlite, read_skill, and show_fixture tools.
- Read relevant skills before SQL execution.
- Keep SQL deterministic and transaction-safe.
