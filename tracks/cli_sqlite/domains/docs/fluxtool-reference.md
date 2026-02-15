# Fluxtool Syntax Reference (Holdout Domain)

Fluxtool remaps gridtool semantics to different command and operator vocabulary.

Commands:
- `IMPORT "file.csv"` (load dataset)
- `FILTER column op value` (keep matching rows)
- `EXCLUDE column op value` (drop matching rows)
- `GROUP group_col => alias=func(col), alias2=func(col2)` (aggregate)
- `SORT column up|down` (order rows)
- `COLUMNS col1, col2, col3` (select columns)
- `COMPUTE new_col := expression` (derive column)
- `ATTACH "file.csv" BY key_col` (join)
- `DISPLAY` or `DISPLAY N` (render rows)

Operator words:
- `is`, `isnt`, `above`, `below`, `atleast`, `atmost`

Rules:
- Fluxtool is not SQL.
- GROUP requires `=>` and `alias=func(column)` specs.
- Aggregation functions are lowercase (`sum`, `count`, `avg`, `min`, `max`).
- File paths in IMPORT/ATTACH must be quoted.
