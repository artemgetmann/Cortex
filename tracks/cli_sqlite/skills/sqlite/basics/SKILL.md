---
name: sqlite-basics
description: Baseline SQL workflow for deterministic sqlite3 CLI tasks.
version: 1
---

# SQLite Basics

Use this skill for every sqlite task.

- Start with explicit schema setup before inserts.
- Keep statements deterministic and idempotent where possible (`DROP TABLE IF EXISTS ...` only when safe).
- Prefer one clear query per `run_sqlite` call while debugging.
- Use `ORDER BY` for deterministic output.
- If errors mention missing table/column, inspect schema immediately and correct forward.
