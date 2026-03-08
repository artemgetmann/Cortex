SQLite task: incremental_reconcile_replay_safe.

Goal:
1) Import rows from `fixture.csv` into `ledger`.
2) Deduplicate by `event_id` and store duplicate rows in `rejects` with reason `duplicate_event`.
3) Route rows with invalid amount values into `rejects` with reason `invalid_amount`.
4) Record two replay passes for the same batch in `replay_log`.
5) Keep the final state replay-safe [safe to repeat without changing the result].
6) Return deterministic aggregate totals by category.

Constraints:
- Use only run_sqlite, read_skill, and show_fixture tools.
- Read relevant skills before SQL execution.
- Keep SQL deterministic and transaction-safe.
