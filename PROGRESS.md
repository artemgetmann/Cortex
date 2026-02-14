# Progress Log

## Status: DONE — LEARNING CURVE + CROSS-TASK TRANSFER DEMONSTRATED

## Run 8: Cross-Task Transfer Learning (NEW)

### What was built
- **Cross-task lesson transfer**: Lessons learned from one task (aggregate_report) help the agent succeed on different tasks (basic_transform, multi_step_pipeline)
- **PICK→SHOW error fix**: When model tries `PICK 5` (SQL-like row limit), gridtool now gives a clear hint pointing to `SHOW N` instead of the generic "column not found"
- **Poisonous lesson filters for HEAD/PICK N**: Lessons suggesting `HEAD 5`, `PICK :5`, `PICK HEAD` are now filtered out (hallucinated solutions)
- **Cross-task experiment script** (`run_cross_task.py`): Train on task A, test on task B, with optional baseline control

### Experiment 8: Baseline — basic_transform with NO prior lessons (sessions 11001-11005)
```
 Run  Score  Steps  Errs  LessIn  LessOut
   1   0.00      3     2       0        3   ← fails on LOAD quoting + KEEP operators
   2   0.75      3     1       3        2   ← gets some right, stuck on SHOW 5
   3   0.00      3     2       5        3   ← regresses (SHOW 5 → PICK variants)
   4   0.25      3     2       8        3   ← HEAD 5 attempt (hallucinated command)
   5   0.75      3     1      11        3   ← partial recovery
```
**Score trajectory: 0.00 → 0.75 → 0.00 → 0.25 → 0.75 (unstable, never reaches 1.0)**

### Experiment 9: Cross-task transfer — train on aggregate_report, test on basic_transform (sessions 11201-11208)
```
 Phase  Task                 Run  Score  Errs  LessIn  LessOut  Hints
 TRAIN  aggregate_report       1   0.25     2       0        3      0  ← learns LOAD, TALLY
 TRAIN  aggregate_report       2   1.00     0       3        4      0  ← mastered
 TRAIN  aggregate_report       3   1.00     0       7        4      0  ← stable
 TEST   basic_transform        1   0.25     2      11        2      0  ← KEEP ops + PICK 5 new
 TEST   basic_transform        2   0.75     1      12        1      0  ← PICK hint fires, gets SHOW 5
 TEST   basic_transform        3   1.00     1      12        4      3  ← mastered!
 TEST   basic_transform        4   1.00     0      12        3      0  ← zero errors
 TEST   basic_transform        5   1.00     0      12        2      0  ← stable
```
**basic_transform: 0.25 → 0.75 → 1.00 (delta=+0.75, mastered in 3 runs)**
**vs baseline: never reached 1.00 in 5 runs!**

**What transferred:**
- LOAD quoting (✅ from run 1 of testing)
- RANK direction syntax (✅ from run 1)
- SHOW basic usage (✅ from run 1)

**What required new learning:**
- KEEP word operators (learned in test run 1)
- SHOW N for row limits (learned in test run 2-3 via PICK error hint)

### Experiment 10: Cross-task transfer — train on aggregate_report, test on multi_step_pipeline (sessions 11301-11308)
```
 Phase  Task                    Run  Score  Errs  LessIn  LessOut
 TRAIN  aggregate_report          1   0.25     2       0        3
 TRAIN  aggregate_report          2   1.00     0       3        4
 TRAIN  aggregate_report          3   1.00     0       7        4
 TEST   multi_step_pipeline       1   1.00     0      11        5  ← PERFECT from run 1!
 TEST   multi_step_pipeline       2   1.00     0      12        4
 TEST   multi_step_pipeline       3   1.00     0      12        4
 TEST   multi_step_pipeline       4   1.00     0      12        4
 TEST   multi_step_pipeline       5   1.00     0      12        3
```
**FULL POSITIVE TRANSFER: 1.00 from very first test run, zero errors!**
LOAD + TALLY + RANK lessons transferred. DERIVE (new command) worked without lessons.

### Experiment 11: Final 3-task experiment (sessions 11401-11409)
```
 Phase  Task                    Run  Score  Errs  LessIn
 TRAIN  aggregate_report          1   0.25     2       0
 TRAIN  aggregate_report          2   1.00     0       4
 TRAIN  aggregate_report          3   1.00     0       8
 TEST   basic_transform           1   0.25     2      11
 TEST   basic_transform           2   0.75     1      12
 TEST   basic_transform           3   1.00     0      12
 TEST   multi_step_pipeline       1   1.00     0      12
 TEST   multi_step_pipeline       2   1.00     0      12
 TEST   multi_step_pipeline       3   1.00     0      12
```
**aggregate_report → basic_transform: 0.25 → 0.75 → 1.00 (3-run ramp)**
**aggregate_report → multi_step_pipeline: 1.00 from run 1 (instant transfer)**

## Latest Experiment Results (Run 7 — with error-triggered hints + count(*) fix)

### Experiment 5: `--max-steps 2` with error-triggered hints (sessions 10001-10010) — BEFORE count(*) fix
```
 Run  Score  Steps  Errs  LessIn  LessOut  Activations
   1   0.00      2     1       0        3            0   ← fails (LOAD quoting)
   2   0.25      2     1       3        2            0   ← count(*) poisonous lesson stuck
   3   0.25      2     1       5        3            3   ← hints fire but contain count(*)
   4-7 0.25      2     1    8-10      0-3          3-3   ← stuck: poisonous count(*) loop
   8   1.00      2     0      12        4            0   ← finally breaks free
   9+ 1.00      2     0      12      2-4            0   ← stable
```
**Problem found: lessons contained count(*) which gridtool rejects. Agent stuck for 6 runs.**

### Experiment 6: `--max-steps 2` AFTER count(*) fix (sessions 10101-10110)
```
 Run  Score  Steps  Errs  LessIn  LessOut
   1   0.00      2     1       0        3   ← fails (LOAD quoting)
   2   1.00      2     0       3        4   ← passes on first retry!
   3+ 1.00      2     0    7-12      2-5   ← stable mastery
```
**Score trajectory: 0.00 → 1.00 (2-run ramp)**

### Experiment 7: `--max-steps 3` AFTER count(*) fix (sessions 10201-10210)
```
 Run  Score  Steps  Errs  LessIn  LessOut
   1   0.25      3     2       0        3   ← fails (LOAD + TALLY arrow)
   2   1.00      3     0       3        3   ← passes!
   3+ 1.00      3     0    6-12      2-4   ← stable mastery
```

## Previous Experiment Results (Runs 1-6)

### Experiment 1: `--max-steps 6 --semi-helpful-errors --bootstrap` (sessions 9601-9610)
```
 Run  Score  Steps  Errs  LessIn  LessOut
   1   0.25      6     5       0        4
   2   1.00      4     1       4        4
   3+  1.00      3     0      12      2-4
```
### Experiment 2: `--max-steps 4` (sessions 9701-9710)
```
   1   0.25      4     3       0        4
   2   1.00      4     2       4        5
   3+  1.00      3     0       9+     2-4
```
### Experiment 3: `--max-steps 3` (sessions 9801-9810)
```
   1   0.00      3     2       0        3
   2   1.00      3     1       3        4
   3+  1.00      3     0       7+     2-5
```
### Experiment 4: `--max-steps 2` — OLD (sessions 9901-9910)
```
   1   0.00      2     1       0        3
   2   0.25      2     1       3        2   ← count(*) poisonous lesson
   3   1.00      2     0       5        5
   4+  1.00      2     0      10+     2-4
```

## Run 8 Code Changes
1. **learning_cli.py**: `load_lesson_objects()` now returns all lessons (cross-task), new known-wrong patterns for HEAD/PICK N hallucinations
2. **gridtool.py**: PICK detects number/HEAD/LIMIT args and hints at SHOW N; new semi-helpful and cryptic overrides for the PICK error
3. **run_cross_task.py**: New experiment script — train on task A, test on task B, with baseline control mode
4. **test_learning_pipeline.py**: 3 new tests (cross-task loading, PICK error detection, HEAD lesson filter) — 42/42 pass

## Run 7 Critical Fixes

### Fix 1: count(*) wildcard — the hidden poisonous lesson
**Problem**: gridtool requires actual column names for aggregation functions (`count(region)`), but `count(*)` doesn't work. Lessons generated from failed runs contained `count(*)` as "correct syntax", which poisoned future runs.

**Fix**:
1. `gridtool.py`: Added specific wildcard detection — `"TALLY: wildcard '*' not supported. Use an actual column name: alias=func(column_name)"`
2. `learning_cli.py`: Added `count(*)` and `COUNT(*)` to `_KNOWN_WRONG_PATTERNS`
3. `learning_cli.py`: Added explicit warnings in critic prompts

**Result**: Agent goes from stuck-for-6-runs to passing-in-2-runs at max-steps=2.

### Fix 2: Error-triggered lesson injection
When the agent hits an error during a run, the system checks loaded lessons for matches and appends relevant hints to the tool_result.

### Fix 3: PICK→SHOW row limit detection (Run 8)
When the model tries `PICK 5` or `PICK HEAD`, gridtool now says "PICK selects columns by name, not row counts. To limit output rows, use SHOW N." This prevents the agent from getting stuck in a PICK/HEAD loop.

## Completed (all runs)
- [run 1-5] Root cause analysis, semi-helpful errors, lesson pipeline fixes, bootstrap optimization, test suite
- [run 6] TALLY error disambiguation, 4 experiments, .env fix
- [run 7] Error-triggered lesson injection, count(*) wildcard fix, 2 experiments (max-steps=2)
- [run 8] Cross-task transfer experiments (4 experiments across 3 tasks)
- [run 8] PICK→SHOW error detection + HEAD/PICK N poisonous lesson filter
- [run 8] 42/42 pytest tests pass (3 new: cross-task, PICK error, HEAD filter)

## All Code Changes (Runs 1-8 Combined)
1. **gridtool.py**: Semi-helpful error mode, distinct TALLY error messages, column-not-found MERGE pattern fix, wildcard count(*) detection, **PICK number/HEAD→SHOW hint**
2. **learning_cli.py**: Success lessons, improved critic prompts, quality filter tuning, known-wrong filters (TALLY multi-agg + no-arrow + count(*) + **HEAD/PICK N**), lesson display cleanup, find_lessons_for_error(), **cross-task load_lesson_objects()**
3. **agent_cli.py**: Bootstrap optimization, semi-helpful param, domain_keywords, max_lessons=12, error-triggered lesson injection, lesson_activations metric
4. **gridtool_adapter.py**: Semi-helpful flag passthrough, capture_final_state improvement
5. **run_learning_curve.py + run_cli_agent.py**: --semi-helpful-errors CLI flag, escalation state cleanup
6. **run_cross_task.py**: NEW — cross-task transfer experiment script
7. **test_learning_pipeline.py**: 12 pytest functions (42/42 pass)

## Key Discoveries
1. **Poisonous lessons** are the #1 enemy — count(*) and HEAD in lessons actively block learning
2. **Error disambiguation matters** — same error message for different failures = model loops
3. **Semi-helpful errors are the sweet spot** — hints point in the right direction without giving the answer
4. **Cross-task transfer works** — LOAD quoting, TALLY syntax, RANK direction lessons transfer across different tasks
5. **Transfer is proportional to command overlap** — multi_step_pipeline (LOAD+TALLY+RANK) gets instant transfer; basic_transform (needs KEEP+SHOW N) needs 2-3 runs to learn new syntax
6. **Learning happens fast** with clean lessons — 1-3 runs to go from 0→1.0

## Decisions Made
- Combined approaches A+B+C from the task spec (semi-helpful errors + lesson pipeline fixes + tight step budgets)
- Added error-triggered lesson injection (Approach D lite — hints on error, not progressive)
- count(*) filter is aggressive: blocks any lesson text containing `count(*)`, even if "don't use it"
- Cross-task lessons loaded for error hints — error patterns are domain-level, not task-specific
- HEAD/PICK N lessons filtered aggressively — model hallucinates these as valid commands

## Next Up (if more iterations desired)
1. Try with Sonnet instead of Haiku to see if stronger model learns differently
2. Try cryptic errors + lessons from semi-helpful runs to see if pre-learned lessons work across error modes
3. Consider adaptive step budgets: start tight, increase if agent is struggling
4. Test lesson transfer in reverse: train on basic_transform, test on aggregate_report
5. Add a task requiring MERGE to test transfer of cross-table concepts
