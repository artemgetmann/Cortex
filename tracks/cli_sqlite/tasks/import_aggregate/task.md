SQLite task: import_aggregate.

Goal:
1) Build table `sales(category TEXT, amount INTEGER)`.
2) Import the CSV rows from `fixture.csv` into `sales`.
3) Return grouped totals ordered by category:
   SELECT category, SUM(amount) AS total FROM sales GROUP BY category ORDER BY category;

Constraints:
- Use only run_sqlite, read_skill, and show_fixture tools.
- Keep SQL deterministic and concise.
