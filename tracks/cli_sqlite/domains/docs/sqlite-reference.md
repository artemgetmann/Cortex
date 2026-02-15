# SQLite Reference (CLI Track)

Use `run_sqlite` for deterministic SQL execution against the task-local database.

Key reminders:
- Use explicit `ORDER BY` for stable output.
- Prefer idempotent writes (`INSERT OR IGNORE`, `ON CONFLICT`) for replay-safe tasks.
- Keep statements concise and avoid unsupported shell dot-commands.
- For transaction-sensitive tasks, use `BEGIN TRANSACTION` and `COMMIT` intentionally.

Common patterns:
- Aggregate: `SELECT category, SUM(amount) AS total FROM sales GROUP BY category ORDER BY category;`
- Idempotent insert: `INSERT OR IGNORE INTO table_name(...) VALUES (...);`
- Upsert: `INSERT INTO table_name(...) VALUES (...) ON CONFLICT(key) DO UPDATE SET ...;`
