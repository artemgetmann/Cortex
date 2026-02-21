Shell XLSX quick reference for reproducible reports.

Typical Python workflow:
```bash
python3 - <<'PY'
import pandas as pd
from pathlib import Path

df = pd.read_csv("fixture.csv")
with pd.ExcelWriter("sales_report.xlsx", engine="openpyxl") as writer:
    df.to_excel(writer, sheet_name="RawData", index=False)
    region = (
        df.groupby("region", as_index=False)
        .agg(total_amount=("amount", "sum"), avg_quantity=("quantity", "mean"), txn_count=("quantity", "count"))
        .sort_values("total_amount", ascending=False)
    )
    region.to_excel(writer, sheet_name="RegionSummary", index=False)
PY
```

Determinism rules:
- Use explicit column names in aggregations.
- Sort summary outputs before writing to workbook.
- Print one strict verification line with row counts and totals.
