shell task: shell_excel_build_report.

Goal:
1) Using files in the current workspace, create an Excel workbook named `sales_report.xlsx`.
2) Sheet `RawData` must contain all rows from `fixture.csv` with headers.
3) Sheet `Summary` must contain totals by `region` sorted by total amount descending.
4) Print exactly this verification line:
   - `BUILD_OK path=<abs_path> raw_rows=10 summary_rows=3`

Constraints:
- Use `run_bash` only.
- Do not fabricate values.
- Keep everything inside the task working directory.
