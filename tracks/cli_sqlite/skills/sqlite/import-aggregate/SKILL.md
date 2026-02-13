---
name: sqlite-import-aggregate
description: Procedure for importing fixture rows and computing grouped totals.
version: 1
---

# Import + Aggregate

Use this when a task asks for CSV import and grouped totals.

## Procedure

1. Read `fixture.csv` with `show_fixture`.
2. Build target table with strict column types.
3. Insert all fixture rows exactly once.
4. Run aggregate query with:
- `SUM(amount)`
- `GROUP BY category`
- `ORDER BY category`
5. Re-run the final aggregate query to verify deterministic output.

## Common Failures

- Missing one fixture row.
- Incorrect numeric parsing for `amount`.
- Forgetting `ORDER BY`, causing unstable output.

## Tool Reference

- `dispatch(sql="...")` — executes SQL against the task database.
- `probe(skill_ref="...")` — reads a skill document by reference key.
- `catalog(path_ref="...")` — shows fixture or bootstrap data by path reference.
