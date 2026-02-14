# Progress Log

## Status: WORKING ON

## Completed
- [2026-02-14] Read and analyzed all key files: agent_cli.py, learning_cli.py, gridtool.py, gridtool_adapter.py, run_learning_curve.py, judge_llm.py, task.md, SKILL.md, fixture.csv
- [2026-02-14] Root cause analysis complete — identified 4 compounding issues preventing learning curves

## Root Cause Analysis
1. **Helpful errors = no learning needed** — error messages literally contain the fix (e.g., `"Use: LOAD "filename.csv""`), so agent passes on run 1 without needing lessons
2. **Cryptic errors = no learning possible** — stripped errors like `"TALLY: syntax error."` give zero info to build lessons from
3. **Lessons only from failures** — `generate_lessons()` returns `[]` when score >= 1.0, so successful runs accumulate nothing
4. **Quality filter may kill domain-specific lessons** — generic pattern filter can reject valid gridtool lessons

## Strategy: Combined A+B+C
- **A: Semi-helpful errors** — new `--semi-helpful` mode that hints without giving full syntax
- **B: Fix lesson pipeline** — generate lessons from successes too; improve critic prompt for gridtool domain
- **C: Tight step budget** — run with `--max-steps 6` to force learning dependency

## Blocked
- (none yet)

## Next Up
1. Implement semi-helpful error mode in gridtool.py
2. Fix generate_lessons to also learn from successes
3. Wire semi-helpful mode through adapter + run scripts
4. Run 10-session experiment
5. Analyze results

## Decisions Made
- Combined approaches A+B+C rather than picking just one — they address different failure modes and are complementary
- Semi-helpful errors are the primary lever (biggest impact on forcing a learning curve)
- Keeping max_steps tight (6) makes prior knowledge matter more
