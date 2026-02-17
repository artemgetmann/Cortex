shell task: shell_excel_multi_summary.

Goal:
1) Create `sales_report.xlsx` from `fixture.csv`.
2) `RawData` sheet: all rows from fixture with headers.
3) `RegionSummary` sheet: `region,total_amount,avg_quantity,txn_count`, sorted by `total_amount` desc.
4) `ProductSummary` sheet: `product,total_amount`, sorted by `total_amount` desc.
5) Write `report_manifest.json` with exact keys:
   `raw_rows`, `region_rows`, `product_rows`, `grand_total`, `top_region`, `top_product`.
6) Print exactly these 3 verification lines:
   - `REPORT_OK path=<abs_path> raw_rows=10 region_rows=3 product_rows=3 grand_total=10150 top_region=North top_product=Alpha`
   - `REGION_ORDER North,South,East`
   - `PRODUCT_ORDER Alpha,Beta,Gamma`

Constraints:
- Use `run_bash` only.
- Do not fabricate values.
- Keep everything inside the task working directory.
