SQLite task: incremental_reconcile_nano.

Goal:
1) Insert first-seen rows from `fixture.csv` into `ledger`.
2) Route duplicate `event_id` rows into `rejects` with reason `duplicate_event`.
3) Return deterministic totals by category.

Constraints:
- Use only run_sqlite, read_skill, and show_fixture tools.
- Read relevant skills before SQL execution.
- Keep SQL deterministic and idempotent.
