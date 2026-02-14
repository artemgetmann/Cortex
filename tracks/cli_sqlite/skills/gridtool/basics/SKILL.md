---
name: gridtool-basics
description: Complete reference for the gridtool data processing CLI
version: 1
---

# gridtool Command Reference

gridtool is a pipeline-style data processing tool with its own syntax. It is NOT SQL.

## Commands

### LOAD
Load a CSV file into the workspace.
```
LOAD "file.csv"
```
- Path MUST be quoted with double quotes
- Path is relative to the working directory
- Wrong: `LOAD file.csv` → ERROR: LOAD path must be quoted

### KEEP
Filter rows where condition is true (keep matching rows).
```
KEEP column operator value
```
- Operators are WORDS not symbols: `eq`, `neq`, `gt`, `lt`, `gte`, `lte`
- Wrong: `KEEP price > 10` → ERROR: use word operators
- Right: `KEEP price gt 10`
- String values can be quoted: `KEEP category eq "electronics"`

### TOSS
Remove rows where condition is true (inverse of KEEP).
```
TOSS column operator value
```
- Same operator rules as KEEP
- Example: `TOSS stock eq 0` removes all rows where stock is 0

### TALLY
Group by a column and compute aggregates.
```
TALLY group_col -> alias=func(agg_col)
```
- Uses `->` arrow separator (NOT GROUP BY)
- Format: `alias=func(col)` (NOT `FUNC(col) AS alias`)
- Functions (LOWERCASE only): `sum`, `count`, `avg`, `min`, `max`
- Multiple aggregations separated by commas:
  ```
  TALLY region -> total=sum(amount), cnt=count(quantity)
  ```
- Wrong: `GROUP BY region SELECT SUM(amount)` → not gridtool syntax
- Wrong: `TALLY region -> SUM(amount)` → missing alias
- Wrong: `TALLY region -> total=SUM(amount)` → SUM must be lowercase `sum`

### RANK
Sort rows by a column.
```
RANK column asc|desc
```
- Direction must be `asc` or `desc`
- Wrong: `ORDER BY price DESC` → not gridtool syntax
- Wrong: `SORT price desc` → use RANK not SORT
- Right: `RANK price desc`

### PICK
Select specific columns (reorder/filter columns).
```
PICK col1, col2, col3
```
- Column names separated by commas
- Wrong: `SELECT col1, col2` → use PICK not SELECT
- Right: `PICK name, price, stock`

### DERIVE
Create a computed column.
```
DERIVE new_col = expression
```
- Supports: `+`, `-`, `*`, `/` between columns and constants
- Example: `DERIVE total = salary + bonus`
- Example: `DERIVE discount_price = price * 0.9`

### MERGE
Join with another CSV file on a matching column.
```
MERGE "file.csv" ON column
```
- Path must be quoted
- Performs inner join on the specified column

### SHOW
Print current data as CSV output.
```
SHOW          # all rows
SHOW 5        # first 5 rows only
```

## Common Mistakes

| Wrong | Right | Why |
|---|---|---|
| `SELECT col1, col2` | `PICK col1, col2` | gridtool uses PICK, not SELECT |
| `KEEP price > 10` | `KEEP price gt 10` | Word operators, not symbols |
| `ORDER BY col DESC` | `RANK col desc` | gridtool uses RANK |
| `GROUP BY col` | `TALLY col -> ...` | gridtool uses TALLY with -> |
| `TALLY col -> SUM(x)` | `TALLY col -> total=sum(x)` | Lowercase func + alias required |
| `LOAD file.csv` | `LOAD "file.csv"` | Path must be quoted |
| `SORT col desc` | `RANK col desc` | Use RANK not SORT |

## Pipeline Pattern

Commands execute in sequence, each operating on the current data state:
```
LOAD "sales.csv"
KEEP amount gt 100
TALLY region -> total=sum(amount), cnt=count(amount)
RANK total desc
SHOW
```

## Tool Reference

Use `run_gridtool` to execute gridtool commands. Pass all commands as a single string in the `commands` parameter.
