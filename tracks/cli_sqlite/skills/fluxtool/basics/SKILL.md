---
name: fluxtool-basics
description: Holdout fluxtool syntax reference with remapped command/operator language
version: 1
---

# fluxtool Command Reference

fluxtool is a holdout pipeline CLI. It is not SQL and command names differ from gridtool.

## Commands

### IMPORT
Load CSV data.
```text
IMPORT "file.csv"
```

### FILTER
Keep rows matching condition.
```text
FILTER column op value
```

### EXCLUDE
Drop rows matching condition.
```text
EXCLUDE column op value
```

Operator words:
- `is`, `isnt`, `above`, `below`, `atleast`, `atmost`

### GROUP
Aggregate by key column.
```text
GROUP group_col => alias=func(col)
```
- Uses `=>` (not `->`)
- Multiple aggregations are comma-separated
- Functions are lowercase: `sum`, `count`, `avg`, `min`, `max`

### SORT
Order rows.
```text
SORT column up|down
```

### COLUMNS
Select output columns.
```text
COLUMNS col1, col2, col3
```

### COMPUTE
Create derived column.
```text
COMPUTE new_col := expression
```

### ATTACH
Join external CSV.
```text
ATTACH "file.csv" BY join_col
```

### DISPLAY
Print output.
```text
DISPLAY
DISPLAY 5
```
