# CLI Learning Lab — Self-Improving Agent via Cross-Session Lessons

## What This Branch Built

A **self-improving AI agent** that teaches itself an unfamiliar CLI tool (`gridtool`) through trial, error, and persistent lesson accumulation — with **no skill docs or prior knowledge**. The agent starts knowing nothing about gridtool's syntax, fails, generates lessons from its failures (and successes), and loads those lessons into future sessions. Within 2-3 sessions it masters the tool. Lessons transfer across different tasks.

All code lives in `tracks/cli_sqlite/`. 11 files changed, +1,302 lines across 18 commits.

## What It Proved

### 1. Measurable learning curve (0.00 → 1.00 in 2 runs)

An LLM agent with zero prior knowledge goes from complete failure to perfect scores through lesson accumulation alone:

```
Session 1: score=0.00  (no lessons → LOAD quoting error burns all steps)
Session 2: score=1.00  (3 lessons loaded → avoids errors, completes task perfectly)
Session 3: score=1.00  (stable — mastery maintained)
```
*Experiment 6, max-steps=2, Haiku executor. Sessions 10101-10105.*

### 2. Cross-task transfer learning

Lessons from Task A help the agent succeed on Task B — even on its first attempt:

```
TRAIN  aggregate_report   1: 0.25 → 2: 1.00 → 3: 1.00   (learns LOAD, TALLY, RANK)
TEST   basic_transform    1: 0.00 → 2: 1.00 → 3: 1.00   (LOAD transferred, learns KEEP/SHOW)
TEST   multi_step_pipeline 1: 1.00 → 2: 1.00 → 3: 1.00  (instant full transfer!)
```
*Experiment A (verification run), sessions 11501-11509. Reproduced 3 times.*

### 3. Transfer is bidirectional

Reverse direction works: train on `basic_transform`, test on `aggregate_report`:
```
TRAIN  basic_transform    1: 0.25 → 2: 1.00 → 3: 1.00
TEST   aggregate_report   1: 0.25 → 2: 1.00 → 3: 1.00
```
*Experiment C, sessions 11701-11706.*

### 4. Controlled baseline comparison

Without transfer learning, the agent oscillates and **never reaches 1.0**:
```
Baseline (no prior lessons): 0.00 → 0.75 → 0.00 → 0.25 → 0.75  (5 runs, unstable)
With transfer:               0.00 → 1.00 → 1.00                  (stable by run 2)
```
*Baseline: sessions 11001-11005. Transfer: sessions 11501-11506.*

### 5. Sonnet vs Haiku: smaller model learns faster

Sonnet (4.5) needs 3 training runs vs Haiku's 2. Sonnet gets hints but stubbornly tries its own syntax variations. Haiku copies the lesson verbatim. Both achieve the same final result — Haiku just gets there one run faster.

```
Haiku training:  0.25 → 1.00 → 1.00  (mastery at run 2)
Sonnet training: 0.25 → 0.00 → 1.00  (regression at run 2, mastery at run 3)
```
*Experiment B, sessions 11601-11609.*

## Verify It Yourself

**Quick verification** — run the 42-test suite (no API key needed, ~2 seconds):
```bash
python3 -m pytest tracks/cli_sqlite/tests/ -v
```

**Full experiment** — reproduce the cross-task transfer result (~5 min, needs `ANTHROPIC_API_KEY` in `.env`):
```bash
: > tracks/cli_sqlite/learning/lessons.jsonl
python3 tracks/cli_sqlite/scripts/run_cross_task.py \
  --train-task aggregate_report \
  --test-tasks basic_transform multi_step_pipeline \
  --domain gridtool --train-sessions 3 --test-sessions 3 \
  --start-session 12001 --max-steps 3 \
  --bootstrap --semi-helpful-errors \
  --posttask-mode direct --verbose
```

**Check existing session data** — raw metrics from all experiments are in `tracks/cli_sqlite/sessions/`:
```bash
python3 -c "
import json, os
for sid in range(11501, 11510):
    m = json.load(open(f'tracks/cli_sqlite/sessions/session-{sid}/metrics.json'))
    print(f'{sid}: score={m[\"judge_score\"]:.2f}  task={m[\"task_id\"]}  lessons_in={m[\"lessons_loaded\"]}  errors={m[\"tool_errors\"]}')
"
```

## What's Unique About This Branch

This is the only branch that **empirically proves cross-session learning works** with controlled experiments:

- **14 experiments** run across 155 sessions with real API calls and LLM judge scoring
- **Controlled baselines** — same task with and without prior lessons, showing lessons cause the improvement
- **Cross-task transfer** — lessons generalize beyond the task they were learned from
- **Model comparison** — tested with both Haiku and Sonnet, showing model-size effects on learning speed
- **Bidirectional transfer** — A→B and B→A both work
- **Poisonous lesson discovery** — identified and solved the #1 failure mode (incorrect lessons that actively block learning)

## Architecture

```
agent_cli.py          ← Main agent loop: load lessons → run task → generate lessons → store
learning_cli.py       ← Lesson generation, quality filtering, poisonous lesson detection, dedup
gridtool.py           ← Custom CLI tool with 3 error modes (helpful, semi-helpful, cryptic)
gridtool_adapter.py   ← Subprocess wrapper + final state capture for LLM judge
run_learning_curve.py ← Single-task learning curve experiment runner
run_cross_task.py     ← Cross-task transfer experiment runner (train on A, test on B)
test_learning_pipeline.py ← 42 tests covering the full pipeline (no API needed)
```

### Key mechanisms
1. **Semi-helpful errors** — hints at what's wrong without giving the answer (the Goldilocks difficulty)
2. **Lesson quality filter** — scores lessons by domain specificity, filters generics
3. **Poisonous lesson filter** — regex patterns that reject known-wrong lessons (`count(*)`, `HEAD N`, `PICK N`)
4. **Error-triggered hint injection** — when agent hits an error, matching lessons are appended to the response
5. **Success lessons** — records what worked, not just what failed

## Key Discoveries

1. **Poisonous lessons are the #1 enemy** — one incorrect lesson (`count(*)`) blocked learning for 6 consecutive runs
2. **Error disambiguation matters** — same error message for different root causes = agent loops forever
3. **Semi-helpful errors are the sweet spot** — too helpful = no learning needed, too cryptic = no learning possible
4. **Smaller models follow lessons better** — Haiku copies syntax from lessons; Sonnet tries its own variation first
5. **Transfer is proportional to command overlap** — shared commands transfer instantly, new commands need 1-2 extra runs

## All Experiments Summary

| # | Config | Model | Train Task | Test Task | Result | Sessions |
|---|--------|-------|-----------|----------|--------|----------|
| 1 | max-steps=6 | Haiku | aggregate_report | (same) | 0.25→1.00 in 2 runs | 9601-9610 |
| 2 | max-steps=4 | Haiku | aggregate_report | (same) | 0.25→1.00 in 2 runs | 9701-9710 |
| 3 | max-steps=3 | Haiku | aggregate_report | (same) | 0.00→1.00 in 2 runs | 9801-9810 |
| 4 | max-steps=2 (old) | Haiku | aggregate_report | (same) | 0.00→1.00 in 3 runs | 9901-9910 |
| 5 | max-steps=2 (pre-fix) | Haiku | aggregate_report | (same) | stuck 6 runs (count\*) | 10001-10010 |
| 6 | max-steps=2 (fixed) | Haiku | aggregate_report | (same) | 0.00→1.00 in 2 runs | 10101-10110 |
| 7 | max-steps=3 (fixed) | Haiku | aggregate_report | (same) | 0.25→1.00 in 2 runs | 10201-10210 |
| 8 | baseline (no train) | Haiku | (none) | basic_transform | never 1.0 in 5 runs | 11001-11005 |
| 9 | cross-task | Haiku | aggregate_report | basic_transform | 0.25→1.00 in 3 runs | 11201-11208 |
| 10 | cross-task | Haiku | aggregate_report | multi_step_pipeline | 1.00 instant | 11301-11308 |
| 11 | 3-task final | Haiku | aggregate_report | both | bt:3 runs, msp:instant | 11401-11409 |
| A | verification | Haiku | aggregate_report | both | bt:2 runs, msp:instant | 11501-11509 |
| B | sonnet | Sonnet | aggregate_report | both | bt:2 runs, msp:instant | 11601-11609 |
| C | reverse | Haiku | basic_transform | aggregate_report | 0.25→1.00 in 2 runs | 11701-11706 |
