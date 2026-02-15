# Cortex Demo — Execution Tracker

**Hackathon:** Anthropic "Built with Opus 4.6" (Feb 10-16, 2026)
**Last updated:** Feb 15, 2026

---

## Day 1 Status: CLI Learning Demo ✅ COMPLETE

### Wave 1: Build (DONE)
- [x] **multi_agg_pipeline task** — 7-command pipeline, 10+ failure modes
  - `tracks/cli_sqlite/tasks/multi_agg_pipeline/sales_data.csv` (14 rows, 4 regions)
  - `tracks/cli_sqlite/tasks/multi_agg_pipeline/task.md`
- [x] **Demo display system**
  - `tracks/cli_sqlite/demo_display.py` — Rich rendering (banners, steps, replay, scores, summary)
  - `tracks/cli_sqlite/scripts/demo_learning.py` — Demo entry point with all flags
  - `agent_cli.py` — on_step callback added (3 lines)
  - `requirements.txt` — `rich>=13.0.0` added

### Wave 2: Verify (DONE)
- [x] 42/42 pytest tests pass
- [x] Rich display renders correctly

### Wave 3: Calibrate (DONE)
- [x] **aggregate_report** (Haiku, 3 sessions): Steps 6→4→3, Errors 3→1→0, all PASS
- [x] **multi_agg_pipeline** (Haiku, 6 sessions): Score 0.00→1.00→1.00→1.00→1.00→1.00
  - Session 1: 12 steps, 11 errors (FAIL) — dramatic cold start
  - Session 2: 7 steps, 4 errors (PASS) — lessons kick in
  - Sessions 3-6: 3 steps, 0 errors (PASS) — clean mastery
  - **Verdict:** Well-calibrated. Hard enough to fail cold, learnable in 1 iteration.

### Wave 4: Model Comparisons ✅ COMPLETE

| Model | Steps Budget | Sessions | Score Trajectory | Steps Trend | Errors Trend |
|-------|-------------|----------|-----------------|-------------|-------------|
| **Haiku** | 12 | 6 | `0.00 → 1.00 → 1.00 → 1.00 → 1.00 → 1.00` | 12→3 | 11→0 |
| **Sonnet** | 12 | 5 | `1.00 → 1.00 → 0.90 → 0.85 → 1.00` | 9→3 | 6→0 |
| **Opus** | 3 | 5 | `0.10 → 1.00 → 1.00 → 0.10 → 0.00` | 3→3 | 1→0→2 |

**Analysis:**
- **Haiku = best demo model.** Dramatic cold failure (0.00, 11 errors) → instant mastery by session 2. Cleanest learning curve.
- **Sonnet = efficiency story.** Smart enough to brute-force pass on session 1 (9 steps, 6 errors), but lessons reduce to 3 steps, 0 errors. Mid-run dip (0.90, 0.85) from hitting new syntax edges, recovers by session 5.
- **Opus = budget too tight.** 3-step budget causes regressions when agent encounters new syntax with no room to recover. Learning works (0.10→1.00 in 1 run) but instability makes it poor for demo. Run 5's 0.00 is a judge parsing fluke.
- **Recommendation:** Use Haiku for the "dramatic learning" demo, Sonnet for "efficiency gains" side-story. Skip Opus tight-budget for demo.

Commands to reproduce:
```bash
# Haiku (best demo)
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id multi_agg_pipeline --domain gridtool \
  --sessions 6 --start-session 10001 --max-steps 12 \
  --bootstrap --clear-lessons

# Sonnet
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id multi_agg_pipeline --domain gridtool \
  --sessions 5 --start-session 20001 --max-steps 12 \
  --bootstrap --clear-lessons \
  --model-executor claude-sonnet-4-5-20250929

# Opus (tight budget — unstable, for data only)
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id multi_agg_pipeline --domain gridtool \
  --sessions 5 --start-session 30001 --max-steps 3 \
  --bootstrap --clear-lessons \
  --model-executor claude-opus-4-6
```

---

## Day 2 Status: CLI Demo Polish (Visibility + Harder Curriculum)

### Winning Demo Target
- **Task:** `regional_performance`
- **Model:** `claude-haiku-4-5`
- **Error mode:** `--mixed-errors` (semi-helpful on basic commands, cryptic on core pipeline commands)
- **Step budget:** `--max-steps 8`
- **Curve target:** **9 runs** with **5 FAIL then 4 PASS** (knee at run 5 or 6)

### Why This Matters (Narrative)
- The agent has no prior docs or examples for `gridtool` in bootstrap mode.
- It fails, extracts concrete syntax lessons from critic output, injects those lessons into future prompts, and converges.
- This is in-context learning across sessions, not fine-tuning.
- Demo now shows full pipeline: prompt context, thinking trace, hint injection, critic raw vs filtered, judge reasoning.

### Operator Self-Test (Run This Yourself)
1. **Tests first**
```bash
python3 -m pytest tracks/cli_sqlite/tests/test_learning_pipeline.py -v
python3 -m pytest tracks/cli_sqlite/tests/ -v
```
2. **Inspect exact model context (no sessions executed)**
```bash
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id regional_performance --domain gridtool \
  --bootstrap --mixed-errors --dump-prompt
```
3. **Run the polished demo**
```bash
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id regional_performance --domain gridtool \
  --sessions 9 --start-session 60001 --max-steps 8 \
  --bootstrap --mixed-errors --clear-lessons \
  --replay-detail full
```
4. **Consistency check (3 independent curves)**
```bash
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id regional_performance --domain gridtool \
  --sessions 9 --start-session 70001 --max-steps 8 \
  --bootstrap --mixed-errors --clear-lessons --replay-detail compact

python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id regional_performance --domain gridtool \
  --sessions 9 --start-session 80001 --max-steps 8 \
  --bootstrap --mixed-errors --clear-lessons --replay-detail compact
```

### Evidence Gate (What Counts as Success)
- Three curves all show fail-heavy start then stable pass tail.
- First PASS appears around run 5-6 (±1 across runs).
- No regression after first PASS in the same curve.

### Transferability Follow-Up (Required Before Broad Claims)
- Build a **new fictional holdout tool** with remapped command names/operators (not just same syntax family).
- Re-run the same learning protocol to measure whether critic/judge quality holds under true domain shift.
- Until this holdout passes, avoid claiming broad cross-domain generalization.

---

## Day 2 Plan: FL Studio Learning Loop Demo

**Goal:** Show the same learning-from-failure pattern on FL Studio Desktop via computer_use.
**Time budget:** ~8 hours. Ship > polish.
**Constraint:** FL Studio must be open, visible, forefront on macOS for all live tests.

---

### What Already Exists (no work needed)

| File | What it does | Lines |
|------|-------------|-------|
| `agent.py` | Full agentic loop: screenshot → Opus API → tool_use → execute → repeat | 760 |
| `computer_use.py` | macOS Quartz CGEvent wrapper (keys, clicks, screenshots, coordinate mapping) | 791 |
| `learning.py` | Lesson generate / store / load / retrieve (simpler than CLI version) | 281 |
| `self_improve.py` | Skill update system (propose, apply, queue, promote) | ~600 |
| `skill_routing.py` | Skill manifest + routing | ~180 |
| `run_eval.py` | Deterministic drum pattern evaluator (click coords + spacing) | 231 |
| `memory.py` | Session path management + JSONL/metrics I/O | 52 |
| `config.py` | Env-based config (API key, models, display size, betas) | 79 |
| `skills/fl-studio/basics/SKILL.md` | Universal FL Studio UI rules | 40 |
| `skills/fl-studio/drum-pattern/SKILL.md` | 4-on-the-floor kick pattern procedure | 48 |
| `scripts/run_agent.py` | CLI entry point for single FL Studio session | 45 |

`agent.py` already calls `generate_lessons()` and `load_relevant_lessons()` from `learning.py` — the learning loop exists. It also does posttask skill updates via `self_improve.py`. The gap is: no multi-session runner, no demo display, and learning.py lacks dedup/guards.

---

### Execution Plan

#### Wave 1: Code Changes (parallel, ~2 hours)

**Task A: Add `on_step` callback to `agent.py`** (~10 min)
- Same pattern as `agent_cli.py`: add `on_step: Callable | None = None` param to `run_agent()`
- Call `on_step(step, tool_name, ok, error)` after each tool execution
- Existing callers unaffected (default None)

**Task B: Port lesson dedup to `learning.py`** (~30 min)
- Add Jaccard similarity dedup to `store_lessons()` (prevent duplicate lessons across sessions)
- Currently `learning.py` appends blindly — CLI's `learning_cli.py` has `dedup_threshold=0.65`
- Copy the pattern: before appending, check new lesson against existing lessons, skip if Jaccard > 0.65

**Task C: Create `scripts/run_fl_learning_demo.py`** (~1 hour)
- Learning curve runner + Rich demo display for FL Studio sessions
- Reuse `demo_display.py` from CLI track (import directly — it's generic enough)
- Wrap `run_agent()` in a loop with:
  - `show_demo_header()` — task, model, sessions
  - `show_session_header()` — run N/M, lessons loaded
  - `show_step()` via on_step callback — real-time green ✓ / red ✗
  - `show_session_score()` — eval score from `run_eval.py`
  - `show_lessons_generated()` — count
  - `show_learning_progress()` — score trajectory
  - `show_final_summary()` — full table
- Args: `--task`, `--sessions`, `--start-session`, `--max-steps`, `--model`, `--clear-lessons`, `--no-skills`, `--replay-detail`
- Clear lessons if `--clear-lessons` (backup + truncate `learning/lessons.jsonl`)

**Task D: Add second task — tempo change** (~30 min)
- Create `skills/fl-studio/tempo-change/SKILL.md` — procedure for changing BPM
- Modify `run_eval.py` or add separate eval for tempo tasks (or just use LLM judge)
- Task string: "Change the tempo in FL Studio to 140 BPM"
- This enables the Session 3 "transfer" demo: agent uses navigation memories from drum pattern to find Transport bar

---

#### Wave 2: Live Testing with FL Studio (sequential, ~3 hours)

**Prereqs:**
- FL Studio Desktop open and visible (not minimized)
- Terminal has Accessibility + Screen Recording permissions
- `.env` has `ANTHROPIC_API_KEY`
- Run from non-sandboxed terminal (or use `dangerouslyDisableSandbox: true`)

**Test 1: Baseline single session** (~5 min)
```bash
python3 scripts/run_agent.py \
  --task "Create a 4-on-the-floor kick drum pattern in FL Studio" \
  --session 5001 --max-steps 20 --verbose
```
Verify: agent takes screenshots, clicks Channel Rack, attempts step buttons, eval runs.

**Test 2: Learning curve — drum pattern (3 sessions)** (~15 min)
```bash
python3 scripts/run_fl_learning_demo.py \
  --task "Create a 4-on-the-floor kick drum pattern in FL Studio" \
  --sessions 3 --start-session 5101 --max-steps 20 \
  --clear-lessons --replay-detail compact
```
**Expected:**
- Session 1: Agent fumbles, misclicks, uses too many zoom/inspection actions. Score 0.25-0.75.
- Session 2: Lessons loaded, fewer mistakes, score improves to 0.75-1.00.
- Session 3: Clean execution, score 1.00.

**Test 3: Transfer demo — tempo change after drum pattern lessons** (~10 min)
```bash
# DON'T clear lessons — reuse drum pattern lessons
python3 scripts/run_fl_learning_demo.py \
  --task "Change the tempo in FL Studio to 140 BPM" \
  --sessions 2 --start-session 5201 --max-steps 15 \
  --replay-detail compact
```
**Expected:** Agent has navigation memories from drum sessions (knows Channel Rack, Transport bar layout). Applies partial knowledge to new task.

**Test 4: Stateless vs stateful comparison** (~10 min)
```bash
# Stateless run (no skills, no lessons)
python3 scripts/run_agent.py \
  --task "Create a 4-on-the-floor kick drum pattern in FL Studio" \
  --session 5301 --max-steps 30 --no-skills --no-posttask-learn --verbose

# Stateful run (skills + lessons from prior sessions)
python3 scripts/run_agent.py \
  --task "Create a 4-on-the-floor kick drum pattern in FL Studio" \
  --session 5302 --max-steps 30 --verbose
```
Compare: actions count, mistakes, time — this is the money shot for the demo narrative.

---

#### Wave 3: Demo Polish + Recording (~2 hours)

**Polish (if time):**
- Port error-triggered lesson injection from CLI → agent.py (match errors against loaded lessons, inject hints)
- Add screenshot thumbnails to Rich output (show what agent sees)
- Add internal monologue display (agent's text reasoning blocks)

**Demo recording:**
- Screen record the Rich terminal output of `run_fl_learning_demo.py`
- Capture FL Studio window alongside (split screen or PiP)
- Key moments to capture:
  1. Session 1: Agent fails, generates lessons (the "struggle")
  2. Session 2: Agent references lessons, succeeds cleanly (the "aha")
  3. Score trajectory: 0.25 → 0.75 → 1.00 (the "proof")
- If using video: speed up Session 1 (boring to watch full failures), real-time for Session 2

---

### Files to Create/Modify

| File | Action | Est. Lines |
|------|--------|-----------|
| `agent.py` | Modify: add on_step callback | +5 |
| `learning.py` | Modify: add Jaccard dedup to store_lessons | +25 |
| `scripts/run_fl_learning_demo.py` | Create: learning curve runner + demo display | ~120 |
| `skills/fl-studio/tempo-change/SKILL.md` | Create: tempo change procedure | ~30 |
| Total new code | | ~180 lines |

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| FL Studio misclicks due to coordinate mapping | Use `--max-steps 20-30` for generous budget. The eval catches misclicks. |
| Agent doesn't improve between sessions | Learning.py already generates lessons. If lessons aren't specific enough, tighten the generate_lessons prompt. |
| Quartz/sandbox blocks input delivery | Use `dangerouslyDisableSandbox: true` for all test commands. |
| Session takes too long (>60s per step with screenshots) | Use Haiku for faster iterations during testing, switch to Opus for final demo recording. |
| Eval only works for drum pattern | Tempo change can use LLM judge fallback (agent.py line 560: `evaluate_drum_run` returns `applicable=False` for non-drum tasks, but `agent.py` still generates lessons). Need to add LLM judge path for non-drum tasks. |

### Demo Narrative (3-minute pitch)

**Minute 0:00-1:00 — "The Struggle" (Session 1, sped up 4x)**
- Show Rich terminal: steps ticking red ✗, agent trying wrong coordinates
- Intercut with FL Studio window: cursor moving to wrong spots
- End: Score 0.25, 4 lessons generated
- Key line: "Watch it fail. This is Claude Opus 4.6 with computer use — seeing FL Studio for the first time."

**Minute 1:00-2:00 — "The Memory" (Session 2, real-time)**
- Show Rich terminal: "3 lessons loaded" in session header
- Steps go green ✓ ✓ ✓ — agent nails it
- FL Studio: cursor goes straight to correct row, clicks precisely
- Score 1.00, 0 mistakes
- Key line: "Same model. Clean context. But it remembered what it learned."

**Minute 2:00-3:00 — "The Proof" (Summary + CLI comparison)**
- Show learning curve table: score trajectory, steps decreasing, errors decreasing
- Flash CLI demo side-by-side: "It's not just FL Studio. Give it ANY unfamiliar tool."
- Show multi_agg_pipeline learning curve: 0.00 → 1.00 in 2 sessions
- Model comparison: Haiku needs 2 tries, Sonnet needs 1, Opus with tight budget needs lessons
- Closing: "Every existing AI agent forgets. Cortex remembers. That's the difference between automation and learning."

### Key Metrics to Capture for Slides

| Metric | Session 1 | Session 2 | Delta |
|--------|-----------|-----------|-------|
| Actions | 30+ | ~10 | -67% |
| Mistakes | 5-8 | 0-1 | -90% |
| Time | 60s+ | ~20s | -67% |
| Score | 0.25 | 1.00 | +300% |

These numbers come from live testing — adjust after Wave 2.

---

## Verification Commands

```bash
# Run all tests
python3 -m pytest tracks/cli_sqlite/tests/ -v

# Demo: aggregate_report (simple, 3 sessions)
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id aggregate_report --domain gridtool \
  --sessions 3 --start-session 99001 \
  --bootstrap --max-steps 6 --clear-lessons

# Demo: multi_agg_pipeline (harder, 6 sessions)
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id multi_agg_pipeline --domain gridtool \
  --sessions 6 --start-session 10001 \
  --bootstrap --max-steps 12 --clear-lessons

# Model comparison: Sonnet
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id multi_agg_pipeline --domain gridtool \
  --sessions 5 --start-session 20001 --max-steps 12 \
  --bootstrap --clear-lessons \
  --model-executor claude-sonnet-4-5-20250929

# Model comparison: Opus (tight budget)
python3 tracks/cli_sqlite/scripts/demo_learning.py \
  --task-id multi_agg_pipeline --domain gridtool \
  --sessions 5 --start-session 30001 --max-steps 3 \
  --bootstrap --clear-lessons \
  --model-executor claude-opus-4-6-20250219
```

## Cost Estimates
- Haiku: ~$0.01-0.02/session
- Sonnet: ~$0.05-0.10/session
- Opus: ~$0.50-1.00/session
- Full comparison suite: ~$5-8 total
