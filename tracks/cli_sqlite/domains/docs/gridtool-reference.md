# Gridtool Syntax Reference

Gridtool is not SQL. Use command pipelines line-by-line.

Commands:
- `LOAD "file.csv"`
- `KEEP column op value`
- `TOSS column op value`
- `TALLY group_col -> alias=func(col), alias2=func(col2)`
- `RANK column asc|desc`
- `PICK col1, col2, col3`
- `DERIVE new_col = expression`
- `MERGE "file.csv" ON join_col`
- `SHOW` or `SHOW N`

Rules:
- Operators are words: `eq`, `neq`, `gt`, `lt`, `gte`, `lte`.
- Aggregation functions are lowercase: `sum`, `count`, `avg`, `min`, `max`.
- `count(*)` is invalid; use a real column name.
- `TALLY` requires arrow syntax `->` and `alias=func(col)` specs.
