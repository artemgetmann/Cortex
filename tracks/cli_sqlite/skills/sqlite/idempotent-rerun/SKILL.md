---
name: sqlite-idempotent-rerun
description: Idempotent import pattern using ON CONFLICT for duplicate-safe ingestion.
version: 1
---

# Idempotent Rerun

Use this skill for `idempotent_rerun` tasks.

## Critical Semantics

- Fixture rows may contain duplicates (same SKU appearing multiple times).
- `sku` is the PRIMARY KEY and idempotency key.
- Use `INSERT OR IGNORE` or `INSERT ... ON CONFLICT DO NOTHING` to skip duplicates.
- Plain `INSERT` will fail on duplicate PKs or cause double-counting.

## Required Flow

1. Read `fixture.csv` with `show_fixture` to inspect the data.
2. Table `inventory(sku TEXT PRIMARY KEY, product TEXT, quantity INTEGER)` is pre-created by bootstrap.
3. Insert all fixture rows using `INSERT OR IGNORE INTO inventory(sku, product, quantity) VALUES (...)`.
4. Verify exactly 3 unique rows exist:
   - `SELECT COUNT(*) FROM inventory;` → 3
5. Verify correct data:
   - `SELECT sku, product, quantity FROM inventory ORDER BY sku;`

## Common Failures

- Using plain `INSERT INTO` without `OR IGNORE` causes UNIQUE constraint violations.
- Importing all 6 rows without dedup results in count=6 instead of count=3.
- Forgetting `ORDER BY sku` in the verification query.

## Guardrails

- Never `DELETE FROM inventory` to fix duplicates after the fact.
- Never `DROP TABLE inventory`.
- The fix must be at insert time, not post-hoc cleanup.

## Tool Reference

- `dispatch(sql="...")` — executes SQL against the task database.
- `probe(skill_ref="...")` — reads a skill document by reference key.
- `catalog(path_ref="...")` — shows fixture or bootstrap data by path reference.
