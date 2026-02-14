# Progress Log

## Status: READY TO RUN EXPERIMENT (blocked on ANTHROPIC_API_KEY)

## Completed
- [2026-02-14] Read and analyzed all key files: agent_cli.py, learning_cli.py, gridtool.py, gridtool_adapter.py, run_learning_curve.py, judge_llm.py, task.md, SKILL.md, fixture.csv
- [2026-02-14] Root cause analysis complete — identified 5 compounding issues preventing learning curves
- [2026-02-14] Analyzed historical experiment data (sessions 6001-9210) confirming the diagnosis
- [2026-02-14] Implemented semi-helpful error mode in gridtool.py (--semi-helpful flag)
- [2026-02-14] Wired semi-helpful mode through gridtool_adapter.py, agent_cli.py, run_cli_agent.py, run_learning_curve.py
- [2026-02-14] Fixed lesson pipeline: generate_lessons now creates positive lessons from successful runs
- [2026-02-14] Improved critic prompt with gridtool-specific examples for both success and failure cases
- [2026-02-14] Tuned quality filter: boosted domain keyword weight (0.15->0.2), added syntax pattern bonus for quotes/arrows/function-calls, increased max_lessons from 8 to 12
- [2026-02-14] All semi-helpful error integration tests pass (verified manually with gridtool CLI)
- [2026-02-14] Quality filter tests pass: good gridtool lessons score 0.37-1.0, generic advice scores 0.0
- [2026-02-14] Fixed _KNOWN_WRONG_PATTERNS regex to catch "TALLY only supports one aggregation" variant
- [2026-02-14] Optimized bootstrap mode: strip read_skill instructions from system prompt + remove read_skill from tool list
- [2026-02-14] Improved gridtool_adapter.capture_final_state() to extract last successful output from events
- [2026-02-14] Fixed column-not-found pattern in cryptic/semi-helpful modes to match MERGE variant
- [2026-02-14] Verified full system prompt construction for bootstrap mode (no read_skill leakage)
- [2026-02-14] Verified lesson dedup doesn't over-aggressively merge distinct TALLY lessons
- [2026-02-14] End-to-end verification: all imports pass, regex works, prompt construction correct, tools correct
- [2026-02-14 run 4] Created comprehensive test suite: tracks/cli_sqlite/tests/test_learning_pipeline.py (61 tests)
- [2026-02-14 run 4] Improved lesson relevance ranking: quality score now factors into lesson ordering (0.2 * quality_score boost)
- [2026-02-14 run 4] Cleaned up lesson display format: removed noisy metadata (session_id, score, steps), kept only category + lesson text
- [2026-02-14 run 4] Made lesson header more forceful: "CRITICAL lessons — follow these rules to avoid wasting steps"
- [2026-02-14 run 4] Improved bootstrap skills_text to explicitly tell agent to ignore task instructions about reading skills
- [2026-02-14 run 4] Enhanced critic prompt for failures: "extract CORRECT syntax from error hint", anti-pattern for TALLY multi-agg myth
- [2026-02-14 run 4] Bumped success lesson count from 3 to 5, failure from 4 to 5, parsed limit from 4 to 6
- [2026-02-14 run 4] Added domain_keywords passthrough to load_relevant_lessons for quality-boosted ranking
- [2026-02-14 run 4] Verified Jaccard dedup thresholds: similar TALLY lessons kept separate (0.22), identical LOAD variants merged (0.77)
- [2026-02-14 run 5] Refactored test_learning_pipeline.py for pytest compatibility (was script-only, now works as both pytest and standalone)
- [2026-02-14 run 5] Full test suite: 37 pytest tests pass (29 existing + 8 new), 65 script-mode checks pass
- [2026-02-14 run 5] Stress-tested semi-helpful errors with 11 realistic LLM mistake patterns — all produce correct hints
- [2026-02-14 run 5] Added bootstrap task text cleanup: strips "read_skill" references and "Read the skill document" instructions from task text at runtime
- [2026-02-14 run 5] Added escalation state cleanup at start of learning curve experiments for clean baselines
- [2026-02-14 run 5] Full import/path verification: all modules load, lessons.jsonl is empty, adapter creates correctly

## Root Cause Analysis
1. **Helpful errors = no learning needed** — error messages literally contain the fix, agent passes run 1
2. **Cryptic errors = no learning possible** — stripped errors give zero info to build lessons from
3. **Lessons only from failures** — `generate_lessons()` returned `[]` when score >= 1.0 (FIXED)
4. **Quality filter too strict for gridtool** — keyword weights too low (FIXED)
5. **Wasted steps on read_skill** — bootstrap mode offered read_skill tool + encouraged reading skills (FIXED)

## Historical Data Analysis
- Sessions 9201-9210 (bootstrap + helpful errors): 9/10 scored 1.0 from run 1, 0 lessons generated
- Sessions 9001-9005 (bootstrap + helpful errors): inconsistent, lessons generated but wrong attribution
- Session 9201 deep dive: agent wasted steps 1-2 trying read_skill with invented refs ("gridtool", "aggregate"). Then needed 5 more steps for LOAD+TALLY errors. Total: 7 steps to pass.
- The system never showed a learning curve — either works immediately or never works

## What Changed (Code) — All Runs Combined
1. **gridtool.py**: New `SEMI_HELPFUL_MODE` + `_SEMI_HELPFUL_OVERRIDES` dict — hints at fix category without full syntax. Distinct "missing alias" error for TALLY. Fixed column-not-found pattern for MERGE variant.
2. **learning_cli.py**: `generate_lessons()` no longer short-circuits on success — creates "what worked" lessons with gridtool-specific critic prompts
3. **learning_cli.py**: `_lesson_quality_score()` increased domain keyword weight (0.15→0.2), added syntax-pattern bonus for quotes/arrows/function-calls
4. **learning_cli.py**: Added `_KNOWN_WRONG_PATTERNS` filter to reject poisonous lessons. Fixed regex to catch all "TALLY only one aggregation" variants.
5. **learning_cli.py**: `load_relevant_lessons()` filters known-wrong lessons at load time (defense in depth). Quality score now factors into relevance ranking. Accepts domain_keywords param.
6. **learning_cli.py**: Cleaner lesson display format — removed noisy metadata, stronger "CRITICAL" header. Bumped max parsed lessons from 4 to 6. Failure prompt explicitly asks to extract correct syntax from error hints and includes anti-pattern for TALLY multi-agg myth.
7. **agent_cli.py**: `max_lessons` 8→12, `max_sessions` 5→8, new `semi_helpful_errors` param, added `import re`
8. **agent_cli.py**: Bootstrap mode strips read_skill instructions from system prompt + removes read_skill from API tool list. Skills text tells agent to ignore task instructions about reading skills.
9. **agent_cli.py**: Passes domain_keywords to load_relevant_lessons for quality-boosted ranking.
10. **agent_cli.py**: Bootstrap mode strips read_skill references from task text at runtime (task.md untouched on disk).
11. **gridtool_adapter.py**: Passes `--semi-helpful` flag to gridtool subprocess. `capture_final_state()` extracts last successful output from events for judge.
12. **run_learning_curve.py** + **run_cli_agent.py**: New `--semi-helpful-errors` CLI flag
13. **run_learning_curve.py**: Clears escalation state at experiment start for clean baselines.
14. **tests/test_learning_pipeline.py**: 8 pytest functions + 65 script-mode checks covering error modes, quality filter, known-wrong filter, storage/dedup/loading, bootstrap prompt, task text cleanup, lesson accumulation, capture_final_state

## Key Discovery: Poisonous Lessons
Critic generates **factually incorrect lessons** like "TALLY supports only one aggregation per call" (TALLY actually supports comma-separated multiple aggregations). These wrong lessons actively hurt performance. Added regex-based filter + explicit anti-pattern in critic prompt.

## Key Discovery: Wasted Bootstrap Steps
Session 9201: agent wasted steps 1-2 on `read_skill` with invented refs ("gridtool", "aggregate"). With max_steps=6, that's 33% of the budget gone. Fixed by removing read_skill tool, instructions, and references from bootstrap mode.

## Semi-Helpful Error Gradient (verified end-to-end)
```
Helpful:      "TALLY syntax: TALLY group_col -> alias=func(agg_col). Got invalid format."
Semi-helpful: "TALLY: expected arrow operator '->' after group column."
Cryptic:      "TALLY: syntax error."
```

## Stress Test Results (run 5 — 11 realistic LLM mistakes in semi-helpful mode)
All produce correct, useful hints:
- SQL GROUP BY → "not SQL — gridtool has its own command names"
- Unquoted LOAD → "file path must be in double quotes"
- SQL SELECT/WHERE/ORDER → "not SQL" hints
- TALLY without arrow → "expected arrow operator '->'"
- Uppercase SUM → "case-sensitive — use lowercase"
- Missing alias → "alias name before '='"
- Missing commas between aggs → "separate multiple aggregations with commas"
- Symbol operators → "operators must be words (like 'eq'), not symbols"
- Double TALLY (poisonous pattern) → "Column not found in current data" (correct!)

## Test Results (run 5)
- tracks/cli_sqlite/tests/test_learning_pipeline.py: 8 pytest tests PASS, 65 script-mode checks PASS
- tracks/cli_sqlite/tests/test_cli_track.py: 29/29 PASS
- Total: 37 pytest PASS, 65 script checks PASS

## Expected Learning Curve Mechanics
With semi-helpful errors + max_steps=6:
- Agent must discover: (1) LOAD quotes, (2) TALLY arrow ->, (3) alias=func format, (4) lowercase functions, (5) comma-separated aggregations
- Each discovery costs 1 step (error → learn → retry). Agent puts all cmds in one run_gridtool call, gridtool exits on first error.
- 4 minimum commands needed (LOAD, TALLY, RANK, SHOW) → 1 step if everything right, but usually 1 show_fixture + 1 run = 2 steps minimum
- With 6 steps: room for ~4 errors max. But 5 things to learn = can't learn all in run 1.
- Run 1: discovers 2-3 syntax rules, runs out of steps → score 0.0
- Run 2: lessons skip known errors, discovers 1-2 more → score 0.0-0.5
- Run 3-4: enough accumulated lessons to pass → score 1.0

## Blocked
- **No ANTHROPIC_API_KEY** in .env or environment — can't run the actual experiment
- Five autonomous runs have now hit this same blocker

## Next Up (for next autonomous run)
1. **SET UP .env with ANTHROPIC_API_KEY** — this is the ONLY blocker
2. Lessons already cleared (0 lines in lessons.jsonl), escalation state auto-cleared by experiment script
3. Run experiment:
   ```bash
   python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
     --task-id aggregate_report --domain gridtool \
     --sessions 10 --start-session 9501 \
     --bootstrap --semi-helpful-errors --max-steps 6 \
     --posttask-mode direct --verbose
   ```
4. Analyze results — look for:
   - Score trajectory (delta between first 3 and last 3 runs)
   - Lesson accumulation (lessons_in should grow across runs)
   - Error reduction (tool_errors should decrease across runs)
5. If no learning curve: try `--max-steps 4` (tighter budget)
6. If passes run 1: semi-helpful errors too easy → make hints more vague
7. If lessons plateau: check lesson quality, increase max_lessons
8. If lessons are wrong: improve critic prompt or add more known-wrong patterns

## Decisions Made
- Combined approaches A+B+C — they address orthogonal failure modes
- Semi-helpful errors hint at the category of fix without giving syntax
- Success lessons use categories `shortcut` and `domain_detail` (not `mistake`)
- Quality filter bonus for syntax-containing lessons (quotes, arrows, function calls)
- Quality score factors into lesson relevance ranking (0.2 * quality boost)
- max_lessons=12 to ensure room for both positive and negative lessons
- Known-wrong lesson filter as critical safeguard against lesson poisoning
- max-steps=6: requires 4 commands minimum, only ~4 error attempts available, forces learning dependency
- Removed read_skill tool from bootstrap mode to prevent wasting steps
- Strip read_skill references from task text at runtime (task.md untouched per constraints)
- Clear escalation state at experiment start for clean baselines
- Cleaner lesson format: stripped metadata noise, stronger CRITICAL header
- Critic prompt explicitly warns against "TALLY only one aggregation" myth
- Did NOT set temperature=0 on executor — stochastic runs test robustness
