---
name: fluxtool-basics
description: Holdout fluxtool syntax reference with remapped command/operator language
version: 2
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

## Learned Updates
- [2026-02-23] SKILL_MISMATCH: fluxtool/basics is for pipeline data processing (IMPORT, FILTER, GROUP, SORT). Task shell_git_transfer_hotfix requires git command execution in bash, not data transformation. (evidence steps: 2)
- [2026-02-23] This skill should not be routed for shell git tasks. Verify routing logic excludes non-shell skills for domain=shell tasks. (evidence steps: 2)
