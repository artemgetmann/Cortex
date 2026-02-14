# Progress Log

## Status: BLOCKED (no ANTHROPIC_API_KEY)

## Completed
- [2026-02-14] Read and analyzed all key files: agent_cli.py, learning_cli.py, gridtool.py, gridtool_adapter.py, run_learning_curve.py, judge_llm.py, task.md, SKILL.md, fixture.csv
- [2026-02-14] Root cause analysis complete — identified 4 compounding issues preventing learning curves
- [2026-02-14] Analyzed historical experiment data (sessions 6001-9210) confirming the diagnosis
- [2026-02-14] Implemented semi-helpful error mode in gridtool.py (--semi-helpful flag)
- [2026-02-14] Wired semi-helpful mode through gridtool_adapter.py, agent_cli.py, run_cli_agent.py, run_learning_curve.py
- [2026-02-14] Fixed lesson pipeline: generate_lessons now creates positive lessons from successful runs
- [2026-02-14] Improved critic prompt with gridtool-specific examples for both success and failure cases
- [2026-02-14] Tuned quality filter: boosted domain keyword weight (0.15->0.2), added syntax pattern bonus for quotes/arrows/function-calls, increased max_lessons from 8 to 12
- [2026-02-14] All 7 integration tests pass for semi-helpful errors
- [2026-02-14] Quality filter tests pass: good gridtool lessons score 0.7-0.9, generic advice scores 0.0

## Root Cause Analysis
1. **Helpful errors = no learning needed** — error messages literally contain the fix, agent passes run 1
2. **Cryptic errors = no learning possible** — stripped errors give zero info to build lessons from
3. **Lessons only from failures** — `generate_lessons()` returned `[]` when score >= 1.0 (FIXED)
4. **Quality filter too strict for gridtool** — keyword weights too low (FIXED)

## Historical Data Analysis
- Sessions 9201-9210 (bootstrap + helpful errors): 9/10 scored 1.0 from run 1, 0 lessons generated
- Sessions 9001-9005 (bootstrap + helpful errors): inconsistent, lessons generated but wrong attribution
- The system never showed a learning curve — either works immediately or never works

## What Changed (Code)
1. **gridtool.py**: New `SEMI_HELPFUL_MODE` + `_SEMI_HELPFUL_OVERRIDES` dict — hints at fix category without full syntax. Also added distinct "missing alias" error for TALLY.
2. **learning_cli.py**: `generate_lessons()` no longer short-circuits on success — creates "what worked" lessons with gridtool-specific critic prompts
3. **learning_cli.py**: `_lesson_quality_score()` increased domain keyword weight (0.15→0.2), added syntax-pattern bonus for quotes/arrows/function-calls
4. **learning_cli.py**: Added `_KNOWN_WRONG_PATTERNS` filter to reject poisonous lessons (e.g., "TALLY only supports one aggregation" which is FALSE, or `read_skill` noise from bootstrap mode)
5. **learning_cli.py**: `load_relevant_lessons()` now also filters known-wrong lessons at load time (defense in depth)
6. **agent_cli.py**: `max_lessons` 8→12, `max_sessions` 5→8, new `semi_helpful_errors` param
7. **gridtool_adapter.py**: Passes `--semi-helpful` flag to gridtool subprocess
8. **run_learning_curve.py** + **run_cli_agent.py**: New `--semi-helpful-errors` CLI flag

## Key Discovery: Poisonous Lessons
Analyzed historical lessons from bak2 file — found that the critic was generating **factually incorrect lessons** like "TALLY supports only one aggregation per call" (TALLY actually supports comma-separated multiple aggregations). These wrong lessons actively hurt performance when loaded into future runs. Added a regex-based filter to catch and reject known-incorrect claims.

## Blocked
- **No ANTHROPIC_API_KEY** in .env — can't run the actual experiment
- Next run should create .env with an API key and then run the experiment

## Next Up (for next autonomous run)
1. Set up .env with ANTHROPIC_API_KEY
2. Clear lessons: `echo -n "" > tracks/cli_sqlite/learning/lessons.jsonl`
3. Clear escalation state: `rm -f tracks/cli_sqlite/learning/critic_escalation_state.json`
4. Run experiment:
   ```bash
   python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
     --task-id aggregate_report --domain gridtool \
     --sessions 10 --start-session 9501 \
     --bootstrap --semi-helpful-errors --max-steps 6 \
     --posttask-mode direct --verbose
   ```
5. If no learning curve appears, try `--max-steps 4` (even tighter budget)
6. If semi-helpful errors are too easy (agent passes run 1), make hints more vague
7. If learning curve appears but lessons plateau, increase `max_lessons` further

## Decisions Made
- Combined approaches A+B+C — they address orthogonal failure modes
- Semi-helpful errors hint at the category of fix without giving syntax (e.g., "double quotes" not `LOAD "file.csv"`)
- Success lessons use categories `shortcut` and `domain_detail` (not `mistake`)
- Quality filter bonus for syntax-containing lessons (quotes, arrows, function calls)
- Kept max_lessons=12 to ensure enough room for both positive and negative lessons
- Added known-wrong lesson filter as critical safeguard against lesson poisoning
- max-steps=6 chosen: requires 4 commands minimum, leaving only ~2 error-correction attempts
