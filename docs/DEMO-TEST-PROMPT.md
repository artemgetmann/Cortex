# Cortex Learning Demo — Test & Build Prompt

You're working in `/Users/user/Programming_Projects/Cortex/.worktrees/dev/` — a self-learning AI system. Your job is to **verify the learning loop works**, then **build a visually striking demo**.

## Context (Read This First)

Cortex is a hackathon project. The core idea: an AI agent that teaches itself unfamiliar CLI tools through **cross-session lesson accumulation**. No pre-written docs, no human help — just error messages and lessons from its own failures.

The learning loop:
1. Agent tries a task using a fictional CLI tool called **gridtool** (non-standard syntax: LOAD, TALLY, RANK, SHOW — models can't rely on training data)
2. Agent fails (wrong syntax, case errors, missing arrows, etc.)
3. System generates **lessons** from the failure (specific: "TALLY requires arrow separator `->` between group column and aggregation")
4. Next session loads those lessons → agent avoids previous mistakes → completes task
5. With a tight step budget (6 steps), lessons are the difference between pass and fail

Key files:
- `tracks/cli_sqlite/scripts/run_learning_curve.py` — runs N sequential sessions, shows score trajectory
- `tracks/cli_sqlite/scripts/run_cli_agent.py` — runs a single session
- `tracks/cli_sqlite/agent_cli.py` — main agent loop
- `tracks/cli_sqlite/learning_cli.py` — lesson generation, filtering, retrieval
- `tracks/cli_sqlite/domains/gridtool.py` — the fictional CLI tool
- `tracks/cli_sqlite/tests/` — unit tests (42 tests, should all pass)

## Phase 1: Verify Everything Works

### Step 1: Run the tests
```bash
cd /Users/user/Programming_Projects/Cortex/.worktrees/dev
python3 -m pytest tracks/cli_sqlite/tests/ -v
```
**Expected:** 42 passed. If any fail, investigate and fix before proceeding.

### Step 2: Run a basic learning curve (Haiku, 5 sessions)
```bash
# Clear lessons for clean baseline
cp tracks/cli_sqlite/learning/lessons.jsonl tracks/cli_sqlite/learning/lessons.jsonl.bak
: > tracks/cli_sqlite/learning/lessons.jsonl

python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --task-id aggregate_report \
  --domain gridtool \
  --sessions 5 \
  --start-session 8001 \
  --max-steps 6 \
  --bootstrap \
  --verbose \
  --posttask-mode direct
```

**Expected outcome:**
- Session 1: score ~0.00-0.25 (agent fails, doesn't know gridtool syntax)
- Session 2-3: score jumps to ~0.75-1.00 (lessons loaded, avoids errors)
- Sessions 4-5: score holds at 1.00 (stable mastery)

**How to read the output:**
- `tool=run_gridtool ok=False error='...'` = agent tried a command and it failed
- `tool=run_gridtool ok=True` = command succeeded
- `tool=show_fixture ok=True` = agent looked at the CSV data
- Score comes from CONTRACT.json evaluation OR LLM judge
- Lessons generated are printed after each session
- Score trajectory table printed at the end

**How we measure success:**
- Score 0.00 = task not completed at all
- Score 0.25-0.75 = partial completion (some steps right, some wrong)
- Score 1.00 = perfect execution
- The LEARNING is proven by: early scores low → later scores high → delta > 0.25

### Step 3: Run Sonnet comparison
```bash
: > tracks/cli_sqlite/learning/lessons.jsonl

python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --task-id aggregate_report \
  --domain gridtool \
  --sessions 5 \
  --start-session 8101 \
  --max-steps 6 \
  --bootstrap \
  --verbose \
  --posttask-mode direct \
  --model claude-sonnet-4-5-20250929
```

**Expected:** Sonnet should learn faster — often 0.10 → 1.00 in 2 runs, then stay perfect.

### Step 4: Run Opus comparison
```bash
: > tracks/cli_sqlite/learning/lessons.jsonl

python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --task-id aggregate_report \
  --domain gridtool \
  --sessions 5 \
  --start-session 8201 \
  --max-steps 6 \
  --bootstrap \
  --verbose \
  --posttask-mode direct \
  --model claude-opus-4-6-20250219
```

**Expected:** Opus may pass on run 1 with 6 steps (it's smart enough to brute-force). If so, that's actually interesting data — it shows Opus doesn't *need* lessons for simple tasks. Try with `--max-steps 3` to force learning dependency.

## Phase 2: Build Harder Tasks for Demo Dramatics

The current `aggregate_report` task is too easy — Sonnet solves it in 2 runs. We need something where even Sonnet struggles for 3-5 runs before mastering it.

### Create a new harder task

Create `tracks/cli_sqlite/tasks/multi_agg_pipeline/` with:
- A task that requires **4+ gridtool commands** in sequence
- Multiple non-obvious syntax rules that must all be learned
- Enough complexity that even with lessons, you need ~4 steps minimum

Ideas for difficulty:
- Task requires LOAD → TALLY with multiple aggregations → RANK with custom sort → SHOW with specific formatting
- Use gridtool features that have tricky syntax (KEEP for column filtering, MERGE for joins if gridtool supports it)
- Require specific column names that are case-sensitive
- Require specific output format that's easy to get wrong

Look at the existing tasks in `tracks/cli_sqlite/tasks/` and `tracks/cli_sqlite/domains/gridtool.py` to understand what gridtool commands exist and how they work. Then design a task that takes MORE steps and has MORE failure modes.

**Target:** With `--max-steps 12`, the task should take Sonnet 3-5 runs to master, and Haiku 6-8 runs. That's the chart that looks impressive on a slide.

## Phase 3: Visual Demo Mode (THE BIG ONE)

The current output is just log lines. For the hackathon demo, we need people to **see the AI thinking, failing, and learning** without reading code.

### Build a rich terminal demo view

Create `tracks/cli_sqlite/scripts/demo_learning.py` that wraps `run_learning_curve.py` with a beautiful terminal output. Requirements:

1. **Clear session header** with run number, model name, lessons loaded count
2. **Show what the agent is thinking** — print the agent's text responses (not just tool calls). The agent often says things like "Let me try LOAD..." or "The error says I need quotes, let me fix that..."
3. **Color-coded output:**
   - Red for failed commands + error messages
   - Green for successful commands
   - Yellow for lessons being generated
   - Cyan for lessons being loaded into the next session
   - Bold white for scores
4. **Show the actual commands** the agent tried (the SQL/gridtool input), not just "tool=run_gridtool"
5. **After each session, show:**
   - Score (big, bold)
   - Lessons generated (with the actual lesson text)
   - Delta from previous session
6. **At the end, show:**
   - Score trajectory chart (ASCII art or just a clean table)
   - Total lessons accumulated
   - Model comparison table (if multiple models ran)
   - Learning speed: "Mastered in N sessions"
7. **Progress bar** between sessions

### The "aha moment" for the audience

The demo should make it viscerally obvious that:
- Run 1: Agent is CLUELESS. Tries wrong syntax, gets cryptic errors, burns all steps
- Run 2: Agent REMEMBERS. Says "Based on previous lessons, I should use quotes around the path..." and executes correctly
- The lessons are SPECIFIC, not generic: "TALLY requires arrow separator `->` between group column and aggregation" (not "always be careful")

The text output from the agent IS the demo. People need to see the agent's reasoning change from "let me try LOAD data.csv" (wrong) to "I know from lessons that LOAD requires quoted paths: LOAD \"data.csv\"" (right).

### Technical notes for the demo script

- The agent's text responses are in the events.jsonl files under each session
- Look at `agent_cli.py` — the model returns text blocks alongside tool_use blocks
- You can capture these during the run or replay from events.jsonl after
- Use Python's `rich` library for terminal formatting (install with `pip install rich`)
- Or use plain ANSI escape codes if you want zero dependencies

## Phase 4: Cross-Task Transfer Demo (Bonus)

After the basic learning demo, show that lessons TRANSFER:

```bash
# Already have run_cross_task.py — check what it does:
python3 tracks/cli_sqlite/scripts/run_cross_task.py --help
```

The story: "Agent learned gridtool syntax on Task A. Now watch it apply that knowledge to Task B — a completely different task it's never seen before."

## Summary of Deliverables

1. ✅ All 42 tests passing
2. ✅ Learning curve verified for Haiku, Sonnet, AND Opus
3. A harder task that takes 3-5 runs to master (not just 2)
4. `demo_learning.py` with rich visual output showing AI thinking + learning
5. Model comparison data (Haiku vs Sonnet vs Opus learning speed)
6. Cross-task transfer demo

**Priority order:** 1 → 2 → 4 → 3 → 5 → 6

## Important Notes

- All commands run from `/Users/user/Programming_Projects/Cortex/.worktrees/dev/`
- Needs `ANTHROPIC_API_KEY` set in `.env` file
- Haiku runs cost ~$0.01-0.02 per session, Sonnet ~$0.05-0.10, Opus ~$0.50-1.00
- Always clear lessons between experiments: `: > tracks/cli_sqlite/learning/lessons.jsonl`
- The `--bootstrap` flag means "no pre-written skill docs" — agent learns from scratch
- Semi-helpful error mode is the default (Goldilocks zone: hints without answers)
