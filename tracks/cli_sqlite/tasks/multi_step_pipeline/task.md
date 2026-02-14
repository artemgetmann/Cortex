gridtool task: multi_step_pipeline.

Goal:
1) Load employee data from fixture.csv
2) Derive a new column `total_comp` equal to salary + bonus
3) Group (tally) by department, computing average total compensation
4) Rank by average compensation in descending order
5) Show all results

Constraints:
- Use only run_gridtool, read_skill, and show_fixture tools.
- Read the gridtool skill document before attempting any commands.
- gridtool has its own syntax — it is NOT SQL.
