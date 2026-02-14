SQLite task: idempotent_rerun.

Goal:
1) Import rows from `fixture.csv` into `inventory(sku, product, quantity)`.
2) The fixture contains duplicate rows — use idempotent insert to handle them.
3) Verify exactly 3 unique rows exist with correct data.

Constraints:
- Use only run_sqlite, read_skill, and show_fixture tools.
- Read relevant skills before SQL execution.
- Keep SQL deterministic and concise.
