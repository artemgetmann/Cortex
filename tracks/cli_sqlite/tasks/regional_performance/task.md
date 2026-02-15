gridtool task: regional_performance.

Goal:
1) Load the sales data from sales_data.csv
2) Remove all rows where category equals "discontinued"
3) Derive a new column "margin" calculated as revenue minus cost
4) Derive a new column "margin_pct" calculated as margin divided by revenue
5) Merge in the region_targets.csv file, joining on the region column
6) Derive a new column "variance" calculated as revenue minus target
7) Group (tally) by region, computing: total revenue, average margin percentage, count of deals, and total variance
8) Keep only regions where total variance is greater than or equal to 500
9) Derive a new column "margin_ratio" from avg_margin_pct multiplied by 100
10) Rank results by total revenue in descending order
11) Then order ties/alignment alphabetically by region ascending
12) Select only the columns: region, total_rev, avg_margin_pct, margin_ratio, deals, total_variance
13) Show all results

Constraints:
- Use only run_gridtool, read_skill, and show_fixture tools.
- Read the gridtool skill document before attempting any commands.
- gridtool has its own syntax — it is NOT SQL.
