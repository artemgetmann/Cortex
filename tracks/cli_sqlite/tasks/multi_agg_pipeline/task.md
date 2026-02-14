gridtool task: multi_agg_pipeline.

Goal:
1) Load the sales data from sales_data.csv
2) Filter out all rows where category equals "discontinued"
3) Derive a new column "margin" calculated as revenue minus cost
4) Group (tally) by region, computing: total revenue, average margin, and count of deals
5) Rank results by average margin in descending order
6) Select only the columns: region, total_rev, avg_margin, deals
7) Show all results

Constraints:
- Use only run_gridtool, read_skill, and show_fixture tools.
- Read the gridtool skill document before attempting any commands.
- gridtool has its own syntax — it is NOT SQL.
