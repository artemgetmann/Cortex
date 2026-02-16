# Autonomous Loop Prompt

## How This Works

You are running autonomously while the developer is away. No one will answer questions. If you need input, **make your best judgment, document it in PROGRESS.md, and keep going.**

**FIRST THING YOU DO:** Check if `PROGRESS.md` exists in this directory. If it does, read it — a previous run already made progress. Pick up where it left off. Do NOT redo completed work. If it doesn't exist, create it and start from scratch.

**LAST THING YOU DO (EVERY TIME, NO EXCEPTIONS):** Before you finish, update `PROGRESS.md` with everything you accomplished, what failed, decisions you made, and what the next run should tackle. Then `git add -A && git commit`. This is your only way to pass knowledge to the next run. If you don't write it down, it's lost.

## Rules

### Safety

- Do NOT delete directories or run `rm -rf`
- Do NOT modify files containing API keys or `.env`
- Do NOT install system-level packages
- Do NOT modify anything outside this worktree
- Do NOT modify the `docs/` folder
- If something seems destructive, skip it and log why in PROGRESS.md

### Work Style

- Work in **small, testable increments**. Commit after each working change.
- If stuck on something for more than 10 minutes of attempts, **skip it and move to the next task**. Log what you tried in PROGRESS.md.
- After each major step, update PROGRESS.md with: what you did, what worked, what didn't, what's next.
- Write code that's **simple and readable**. No clever abstractions. This is a hackathon.
- If you need to make a design decision, pick the simpler option. Document why.

### Testing

- After writing code, **test it immediately**. Don't write 3 files then test.
- If a test fails, fix it before moving on. Max 3 fix attempts, then skip and log.
- When running the agent against FL Studio: the app may not be open. If you can't interact with FL Studio, focus on code that doesn't require it (logging, consolidation, metrics, file I/O).

### Git

- Commit after each working increment with a descriptive message
- Branch is already set up in this worktree — just commit and push

## PROGRESS.md Format

Update this file after every major step:

```markdown
# Progress Log

## Status: [WORKING ON / BLOCKED / DONE]

## Completed
- [timestamp] What was done + result

## Blocked
- What's stuck + what was tried

## Next Up
- What to do next in priority order

## Decisions Made
- Any judgment calls + reasoning
```

---

## Your Task: Fix the Learning Loop — Make It Actually Learn

### Context

You're working on a self-improving AI agent system in `tracks/cli_sqlite/`. The agent controls CLI tools (SQLite, gridtool) to complete tasks. After each task, a learning loop generates lessons from the run, stores them, and loads them into future runs to improve performance.

**The problem: the learning loop doesn't demonstrably improve performance.**

We ran experiments with a custom CLI tool called `gridtool` (a CSV data processor with non-standard syntax). Three experiment conditions:

| Condition | Result | Why |
|---|---|---|
| Full skill docs | 1.0 score from run 1 | Just follows instructions |
| Bootstrap (no docs) + helpful errors | 9/10 pass from run 1 | Error messages tell agent exactly how to fix each mistake |
| Bootstrap + cryptic errors | 0/10 pass after 10 runs | Errors too opaque, no discovery path |

**None show a learning curve.** The system either works immediately or never works. We need to find the sweet spot where the agent fails initially but improves through accumulated lessons.

### Key Files

- `tracks/cli_sqlite/agent_cli.py` — Main agent loop. Loads lessons, runs executor, generates lessons post-task
- `tracks/cli_sqlite/learning_cli.py` — Lesson generation, filtering, storage, pruning
- `tracks/cli_sqlite/self_improve_cli.py` — Skill update proposals from lessons
- `tracks/cli_sqlite/domains/gridtool.py` — The CLI tool (standalone, reads commands from stdin)
- `tracks/cli_sqlite/domains/gridtool_adapter.py` — Adapter that runs gridtool via subprocess
- `tracks/cli_sqlite/scripts/run_learning_curve.py` — Runs N sequential sessions, outputs score table
- `tracks/cli_sqlite/tasks/aggregate_report/task.md` — The test task
- `tracks/cli_sqlite/skills/gridtool/basics/SKILL.md` — Full gridtool reference doc

### Known Issues with the Learning Loop

1. **Lessons only generate on failure** (score < 1.0 in `learning_cli.py:283-284`) — when the agent passes, no lessons stored, so no knowledge accumulates from successes
2. **Lesson quality filter is too strict** — many failed runs generate 0 lessons because the critic (Haiku) produces generic lessons that get filtered out by `_lesson_quality_score()`
3. **Wrong attribution** — lessons sometimes identify the wrong root cause (e.g., "comma-separated aggregations don't work" when the real issue was uppercase function names)
4. **Lessons plateau at 8** — `max_lessons=8` in `load_relevant_lessons()` caps what gets loaded
5. **No negative lessons** — the system never records "I tried X and it worked" — only failures

### What to Explore (Pick 1-2, Go Deep)

#### Approach A: Semi-Helpful Errors

Create an error mode between "tells you the answer" and "tells you nothing". Examples:
- `"TALLY: expected arrow operator"` (hints at `->` without showing full syntax)
- `"LOAD: argument must be quoted"` (hints at quoting without showing example)
- `"Unknown function — functions are case-sensitive"` (hints without showing the fix)

Then run:
```bash
python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --task-id aggregate_report --domain gridtool \
  --sessions 10 --start-session 9401 \
  --bootstrap --max-steps 8 \
  --posttask-mode direct --verbose
```

#### Approach B: Fix the Lesson Pipeline

Make lessons more reliable:
- Generate lessons from SUCCESSES too (what worked and why)
- Lower quality threshold or improve the critic prompt to produce domain-specific lessons
- Add "positive lessons" — when a syntax works, record it
- Make the critic prompt explicitly reference gridtool commands/syntax

#### Approach C: Reduce Max Steps to Force Learning Dependency

With 12 steps, brute-force works. With 6 steps, prior knowledge matters.
Run the experiment with `--max-steps 6` and helpful errors.
The thesis: early runs fail (burn all 6 steps on errors), later runs pass (lessons prevent errors, leaving steps for the actual task).

#### Approach D: Progressive Hint System

First attempt at a command gets cryptic error. Second attempt gets semi-helpful. Third attempt gets full hint. This forces the agent to spend steps "discovering" syntax, making lessons valuable for future runs.

### How to Run Experiments

```bash
# Clear lessons for clean experiment
echo -n "" > tracks/cli_sqlite/learning/lessons.jsonl

# Run learning curve
python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --task-id aggregate_report --domain gridtool \
  --sessions 10 --start-session 9401 \
  --bootstrap --max-steps 8 \
  --posttask-mode direct --verbose

# Check stored lessons
cat tracks/cli_sqlite/learning/lessons.jsonl | python3 -c "import sys,json; [print(json.loads(l).get('lesson','')[:100]) for l in sys.stdin]"
```

### Success Criteria

Show a **measurable upward trajectory** in scores across 10 sessions. Ideal result:

```
Run 1:  0.00  (no knowledge)
Run 2:  0.00  (lessons generated but not enough yet)
Run 3:  0.25  (some lessons helping)
Run 5:  0.50  (improving)
Run 8:  0.75  (getting close)
Run 10: 1.00  (learned enough)
```

The key metric is delta between first 3 runs and last 3 runs.

### Constraints

- Code changes go in `tracks/cli_sqlite/` only — but `PROGRESS.md` and `loop-prompt.md` live in the worktree root, that's fine
- Don't change the task or fixture data
- Don't change the LLM judge logic (unless no meaningful improvements emerge)
- Keep gridtool's actual behavior the same (correct syntax should always work)
- `ANTHROPIC_API_KEY` must be set in `.env` to run experiments

## Open Research Questions (from developer)

1. **Cross-domain transferability**: Do the lessons transfer across domains? Can the same architecture work for FL Studio with computer use, learning over time like it does for gridtool?

2. **Did we succeed?**: Per the success criteria in this document, we achieved: Score trajectory 0.25 → 0.25 → 1.00 → 0.25 → 0.50 → 1.00 → 1.00 → 0.50 → 1.00 → 1.00 (delta +0.75). Does this count as success? The curve is noisy but the trend is clear.

3. **AGI-like generalization**: Are the learnings generalizable? Could you give this system a completely new domain (e.g., FL Studio via computer use) and have it figure things out over time?

4. **Lesson scalability and pruning**: What happens as lessons accumulate? Currently max_lessons=8 and prune keeps max 20 per task. Is there a multi-step pruning mechanism? What about temporal decay — lessons from a month ago vs yesterday? Do old task lessons get foggy as new task lessons pile up?

5. **Lesson retrieval intelligence**: How exactly are lessons retrieved? Is it intelligent semantic matching, pattern matching, or graph-based? Which lessons get loaded and which get dropped?

6. **Cross-task regression**: If the agent learns task A really well, then switches to task B and accumulates lessons for that, does it slowly lose task A knowledge? Human brains work this way (skills decay without practice). Is there a mechanism to handle this?

7. **Pruning roadmap**: Ideal multi-step pruning: Step 1 prunes after ~20 memories, Step 2 prunes after 1-2 months of staleness. What does the current system do vs what should it do?
