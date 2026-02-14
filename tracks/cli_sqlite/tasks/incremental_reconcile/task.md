SQLite task: incremental_reconcile.

Goal:
1) Ingest rows from the fixture into `ledger`.
2) Deduplicate by `event_id` and store duplicate rows in `rejects`.
3) Write checkpoint metadata in `checkpoint_log`.
4) Return deterministic aggregate totals by category.

Constraints:
- Use only run_sqlite, read_skill, and show_fixture tools.
- Read relevant skills before SQL execution.
- Keep SQL deterministic and transaction-safe.
