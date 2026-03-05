# CLI Learning Lab Architecture Audit — v1.5 Simplification

**Date:** 2026-02-27
**Scope:** `tracks/cli_sqlite/` only
**Verdict:** ❌ **Needs simplification first.** Architecture has outpaced evidence. Ship proof before shipping features.

---

## 1. What This System Currently Does (Plain Language)

An LLM agent (GPT-5-nano or Claude) gets a task like "import this CSV into SQLite and compute aggregates." It has a tool (`run_sqlite`, `run_bash`, etc.) to execute commands. It loops: think → act → observe result → repeat, up to N steps.

After each run, a critic LLM extracts "lessons" from failures: small rules like "always CREATE TABLE before INSERT." These lessons are stored in a JSONL file. On the next run, if the agent hits a similar error, matching lessons are retrieved and injected into context to help it self-correct.

**The core hypothesis:** Lessons accumulated across runs should make the agent succeed more often and in fewer steps over time.

**What the data actually shows:** In recent ON/OFF benchmarks, enabling lessons frequently produces *equal or worse* outcomes compared to the no-lessons baseline. The system is retrieving lessons but they aren't translating to measurable lift — and sometimes actively hurt.

---

## 2. Top 5 Complexity Sources That Don't Improve Evidence Quality

### 2.1. `agent_cli.py` is a 5,824-line God Object

Every concern lives here: prompt assembly, tool dispatch, lesson retrieval, contract evaluation, skill patching, benchmark flags, observability, watchdog logic, three LLM backends. This file alone has **50+ configuration flags**. It's impossible to reason about what code path a given benchmark actually exercised.

**Evidence cost:** Zero. This is pure maintenance drag. You can't trust any A/B result when you can't trace the exact code path.

### 2.2. Two Lesson Systems Running in Parallel (V1 + V2)

Legacy `lessons.jsonl` (V1) coexists with `lessons_v2.jsonl` (V2). There's a migration path, dedup logic between them, and both get loaded/merged at runtime. This doubles the surface area for bugs without adding signal — V1 is a subset of V2.

**Evidence cost:** Confounds. When a benchmark says "lessons ON," which store contributed? Mixed provenance makes attribution impossible.

### 2.3. Skill Patching / Self-Improvement Pipeline

`self_improve_cli.py` (649 lines), `self_edit_gate.py` (222 lines), `skill_routing_cli.py` (196 lines), plus a manifest, patch queue, promoted patches, and safety gates. This is an entire code-modification pipeline that *proposes edits to skill docs*.

**Evidence cost:** Negative. Self-editing skills mid-experiment contaminates the independent variable. You can't measure "do lessons help?" if the skill docs themselves are changing between runs. This must be frozen during benchmarks.

### 2.4. Eight Benchmark Runner Scripts

| Script | Lines | Purpose |
|--------|-------|---------|
| `run_learning_curve.py` | 415 | Sequential N-run |
| `run_realworld_learning_benchmark.py` | 940 | 8-arm ablation |
| `run_mixed_benchmark.py` | 606 | Mixed domain |
| `run_memory_stability.py` | 630 | Stability test |
| `run_transfer_pressure.py` | 775 | Transfer test |
| `run_architecture_ab.py` | 375 | A/B comparison |
| `run_cross_domain.py` | 271 | Cross-domain |
| `run_cross_task.py` | 269 | Cross-task |
| **Total** | **4,281** | |

Each runner has its own metrics aggregation, its own report format, its own flag combinations. None share a common comparison framework. You're spending more energy building measurement tools than collecting measurements.

**Evidence cost:** Negative. Proliferating runners means no single runner gets enough repetitions to be statistically meaningful. You need one runner, used 100+ times, not eight runners used 10 times each.

### 2.5. Multi-Domain Expansion Before Core Loop is Proven

5 domain adapters (sqlite, shell, gridtool, fluxtool, artic), 23 tasks, custom tooling per domain. Transfer learning is a stretch goal, but you haven't proven *same-task* learning yet.

**Evidence cost:** Premature. Adding domains multiplies confounders (tool quirks, error surfaces, LLM aptitude per domain) without adding statistical power to the core claim.

---

## 3. Keep / Cut / Postpone Table

| Component | File(s) | Lines | Decision | Rationale |
|-----------|---------|-------|----------|-----------|
| Agent executor loop | `agent_cli.py` (core loop only) | ~800 | **KEEP + EXTRACT** | Core runtime, but extract into focused module |
| Domain adapter protocol | `domain_adapter.py`, `adapter_registry.py` | 168 | **KEEP** | Clean abstraction, low cost |
| SQLite adapter | `domains/sqlite_adapter.py` | 413 | **KEEP** | Primary benchmark domain |
| Shell adapter | `domains/shell_adapter.py` | 457 | **KEEP** | Second benchmark domain (git tasks) |
| Gridtool adapter | `domains/gridtool_adapter.py`, `gridtool.py` | 795 | **POSTPONE** | Useful for transfer proof later, not yet |
| Fluxtool adapter | `domains/fluxtool_adapter.py`, `fluxtool.py` | 453 | **POSTPONE** | Same |
| Artic adapter | `domains/artic_adapter.py` | 342 | **CUT** | Web scraping domain is noise for learning proof |
| Lesson Store V2 | `lesson_store_v2.py` | 575 | **KEEP + SIMPLIFY** | Core persistence, but strip conflict/archive fields |
| Lesson Retrieval V2 | `lesson_retrieval_v2.py` | 782 | **SIMPLIFY** | Two-lane system is overkill; collapse to single-lane |
| Lesson Promotion V2 | `lesson_promotion_v2.py` | 135 | **POSTPONE** | Promotion only matters after basic learning works |
| Legacy lessons (V1) | V1 code paths in `learning_cli.py` | ~200 | **CUT** | Dead weight, V2 is the path forward |
| Lesson generation (critic) | `learning_cli.py` (core) | ~400 | **KEEP + SIMPLIFY** | Core loop, but strip quality scoring complexity |
| Error capture + fingerprints | `error_capture.py` | 278 | **KEEP** | Solid, essential for matching |
| Contract evaluation | `eval_cli.py` | 536 | **KEEP** | Deterministic eval is the best part of this system |
| LLM Judge | `judge_llm.py` | 271 | **CUT for benchmarks** | Non-deterministic eval confounds learning signal |
| Skill routing + manifest | `skill_routing_cli.py`, manifest | 196 | **POSTPONE** | Irrelevant in bootstrap mode |
| Self-improvement pipeline | `self_improve_cli.py`, `self_edit_gate.py` | 871 | **CUT** | Confounds benchmarks, unproven, dangerous |
| Skill patching state | `pending/promoted_skill_patches.json` | — | **CUT** | Part of self-improvement |
| Loop watchdog | `loop_watchdog.py` | 171 | **POSTPONE** | Premature safety; doesn't help prove learning |
| Docs pipeline | `docs_pipeline.py` | 514 | **POSTPONE** | Adds variable to benchmarks without proven ROI |
| Knowledge provider | `knowledge_provider.py` | 125 | **POSTPONE** | Same |
| Semantic index | `semantic_index.py` | 156 | **CUT** | Optional, unused in production benchmarks |
| Variant scoreboard | `variant_scoreboard.py` | 311 | **CUT** | Unused multi-arm bandit, premature |
| Curriculum planner | `curriculum_planner.py` | 348 | **POSTPONE** | Fixed curriculum only until learning proven |
| Demo display | `demo_display.py` | 358 | **POSTPONE** | Presentation layer, not evidence |
| Run observability | `run_observability.py` | 183 | **KEEP** | Lightweight, useful |
| Run service | `run_service.py` | 545 | **POSTPONE** | Task lifecycle mgmt, not needed for batch benchmarks |
| Memory CLI | `memory_cli.py` | 79 | **KEEP** | Thin session I/O |
| Tool validation | `tool_validation.py` | 72 | **KEEP** | Cheap safety |
| Tool aliases | `tool_aliases.py` | 70 | **POSTPONE** | Bootstrap/opaque mode, not core |
| OpenAI transport | `openai_transport.py` | 736 | **KEEP** | Primary backend |
| Claude Print transport | `claude_print_client.py`, `claude_print_runtime.py` | ~300 | **POSTPONE** | Secondary backend; one backend for benchmarks |
| `run_learning_curve.py` | script | 415 | **KEEP** | One canonical runner |
| `run_realworld_learning_benchmark.py` | script | 940 | **CUT** | Merge useful bits into learning curve runner |
| `run_mixed_benchmark.py` | script | 606 | **CUT** | |
| `run_memory_stability.py` | script | 630 | **CUT** | |
| `run_transfer_pressure.py` | script | 775 | **POSTPONE** | After same-task learning proven |
| `run_architecture_ab.py` | script | 375 | **CUT** | |
| `run_cross_domain.py` | script | 271 | **CUT** | |
| `run_cross_task.py` | script | 269 | **CUT** | |
| `memory_timeline_demo.py` | script | 784 | **CUT** | Demo, not evidence |
| ~17 of 23 tasks | tasks/ | — | **FREEZE** | Keep 4 canonical tasks, freeze rest |

**Summary:**
- **CUT:** ~5,500 lines of code, 6 benchmark scripts, semantic index, self-improvement, variant scoreboard, V1 legacy, LLM judge (for benchmarks)
- **POSTPONE:** ~3,500 lines (gridtool, fluxtool, artic, docs pipeline, watchdog, curriculum, demos)
- **KEEP + SIMPLIFY:** ~4,000 lines (core loop, lesson store, retrieval, eval, error capture, transport)

---

## 4. Simplified Target Architecture (v1.5)

```
┌─────────────────────────────────────────────────┐
│                  run_benchmark.py                │
│  (one script: N sessions, ON/OFF toggle, JSON)  │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│                  agent_loop.py                   │
│  System prompt + task + [lessons] → LLM → tool  │
│  Loop until contract pass or step limit          │
│  ~300 lines                                      │
└──────┬──────────────────────────────┬───────────┘
       │                              │
       ▼                              ▼
┌──────────────┐            ┌─────────────────┐
│ domain_adapt │            │  eval_cli.py    │
│ sqlite/shell │            │  CONTRACT.json  │
│ (execute)    │            │  (deterministic │
└──────────────┘            │   pass/fail)    │
                            └─────────────────┘
                                    │
                    ┌───────────────┤
                    ▼               ▼
          ┌──────────────┐  ┌──────────────────┐
          │ error_capture│  │ lesson_store.py   │
          │ (fingerprint)│  │ (JSONL, simple    │
          └──────┬───────┘  │  read/write/match)│
                 │          └──────────────────┘
                 │                  ▲
                 ▼                  │
          ┌──────────────┐         │
          │ lesson_gen   │─────────┘
          │ (critic LLM, │
          │  post-task)   │
          └──────────────┘

Data flow:
1. Run task → collect events + errors
2. Evaluate via CONTRACT.json (deterministic)
3. Extract lessons from errors (critic LLM)
4. Store lessons in JSONL
5. Next run: retrieve matching lessons → inject into prompt
6. Measure: pass rate ON vs OFF across N runs
```

**What's gone:**
- No V1/V2 split (one store)
- No promotion/suppression pipeline (all lessons are equal until proven otherwise)
- No two-lane retrieval (single retrieval with fingerprint + text match)
- No skill routing/patching/self-editing
- No LLM judge (contract only)
- No docs pipeline
- No watchdog
- No multi-backend switching in benchmarks (one model, one path)
- No 8 runners (one runner, configurable)

---

## 5. Strict Success Criteria (Cannot Be Gamed)

### Primary Metric: Contract Pass Rate Lift

```
Δ = pass_rate(ON, last_5_runs) − pass_rate(OFF, last_5_runs)
```

**Requirements for "learning improved":**

| Criterion | Threshold | Why |
|-----------|-----------|-----|
| Same-task lift | Δ ≥ +20 pp (e.g., 60% → 80%) | Statistically meaningful on 10 runs |
| Minimum OFF baseline | OFF pass_rate ≥ 30% | Task must be learnable, not trivial or impossible |
| Maximum OFF ceiling | OFF pass_rate ≤ 80% | Room for improvement must exist |
| Consistency | ON ≥ OFF in ≥ 7/10 paired runs | Not a lucky streak |
| Steps efficiency | median_steps(ON) ≤ median_steps(OFF) | Learning should be faster, not just luckier |
| Reproducibility | Result holds across 2 independent 10-run batches | Not a fluke |

### Secondary Metric: Transfer Lift (Phase 2 only)

```
Δ_transfer = pass_rate(ON, unseen_task) − pass_rate(OFF, unseen_task)
```

Only measured after same-task learning passes all primary criteria.

### Anti-Gaming Rules

1. **No cherry-picking tasks.** Report all 4 canonical tasks, not just best performers.
2. **No tuning retrieval params between ON/OFF.** Same config for both arms.
3. **No accumulating lessons across benchmark batches.** Clean slate per experiment.
4. **No LLM judge as pass criterion.** Contract-only evaluation.
5. **Temperature = 0** for all benchmark runs (or document variance if non-zero).
6. **Same model, same token budget** for ON and OFF.
7. **Report raw numbers.** No "adjusted" or "weighted" scores.

---

## 6. Multi-Model Recommendation: Collapse to One Path

**Current state:** 3 backends (OpenAI, Anthropic API, Claude CLI), 4+ model options (nano, haiku, sonnet, opus), separate judge model.

**Recommendation: Collapse to OpenAI (gpt-5-nano) only for all benchmarks.**

Rationale:
- You need statistical power (many runs). Nano is cheapest and fastest.
- Multi-model adds confounders: each model responds differently to lesson injection.
- A learning system that only works on one specific model isn't proving learning — it's proving prompt engineering for that model.
- *After* proving learning on one model, test generalization to a second (Claude Haiku). That's Phase 2.

**Exception:** Keep Claude Print transport code alive (don't delete) for unattended overnight runs. Just don't use it in benchmarks.

---

## 7. Exact Benchmark Protocol

### Phase 1: Same-Task Learning (Weeks 1-2)

**4 canonical tasks:**

| Task | Domain | Steps | Why |
|------|--------|-------|-----|
| `import_aggregate` | sqlite | 6 | Baseline: simple, well-defined contract |
| `incremental_reconcile` | sqlite | 6 | Harder: multi-step, more error surface |
| `shell_git_transfer_hotfix` | shell | 6 | Different domain, git operations |
| `aggregate_report` | gridtool | 6 | Third domain for breadth |

**Protocol per task:**

```bash
# 1. Clear all lessons
: > tracks/cli_sqlite/learning/lessons_v2.jsonl
: > tracks/cli_sqlite/learning/lessons.jsonl

# 2. Run ON (lessons accumulate across sessions)
python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --task-id $TASK --domain $DOMAIN \
  --sessions 10 --start-session 8001 --max-steps 6 \
  --bootstrap --learning-mode strict \
  --llm-backend openai --benchmark-deterministic \
  --posttask-mode direct \
  --verbose 2>&1 | tee reports/${TASK}_ON.log

# 3. Clear lessons again
: > tracks/cli_sqlite/learning/lessons_v2.jsonl
: > tracks/cli_sqlite/learning/lessons.jsonl

# 4. Run OFF (no lesson retrieval/storage)
python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --task-id $TASK --domain $DOMAIN \
  --sessions 10 --start-session 9001 --max-steps 6 \
  --bootstrap --no-skills \
  --llm-backend openai --benchmark-deterministic \
  --verbose 2>&1 | tee reports/${TASK}_OFF.log
```

**Cost estimate:** 4 tasks × 20 runs × ~$0.02/run (nano) = ~$1.60 total. Run the whole thing 3 times for reproducibility = ~$5.

**Go/No-Go checkpoint:** If 0/4 tasks show Δ ≥ +20pp after 3 batches, stop and debug lesson quality before proceeding.

### Phase 2: Transfer Learning (Week 3, conditional)

Only if Phase 1 passes for ≥ 2/4 tasks.

- Train on `import_aggregate`, test on `incremental_reconcile` (same domain transfer)
- Train on `shell_git_transfer_hotfix`, test on `shell_git_transfer_hotfix_hard` (difficulty transfer)

---

## 8. Hidden Confounders in Current Benchmark Design

### 8.1. Ceiling/Floor Saturation

If OFF pass rate is already 80-90%, there's no room for lessons to help. If it's 0-10%, the task is too hard for the model regardless of lessons. Both produce null results that look like "learning doesn't work."

**Fix:** Calibrate step budget so OFF baseline is 30-70%. Adjust `--max-steps` per task.

### 8.2. Lesson Accumulation Across Experiments

If you run ON experiments without clearing lessons first, each experiment starts with baggage from prior experiments. Good lessons from one task may poison another.

**Fix:** Always clear lesson stores between experiments. Treat each experiment as independent.

### 8.3. LLM Non-Determinism at Temperature > 0

Even at temperature=0, some APIs have internal sampling noise. Two identical runs can diverge on step 1, making paired comparisons meaningless.

**Fix:** Use `--benchmark-deterministic` (temperature=0). Run enough samples (N≥10) to average out remaining noise. Use aggregate stats, not individual run comparisons.

### 8.4. Critic Model Quality ≈ Lesson Quality

The critic LLM that extracts lessons is the same cheap model (nano) running the tasks. If nano can't solve the task, its "lessons" about what went wrong may be wrong too. Garbage-in-garbage-out.

**Fix:** Consider using a stronger model (haiku or sonnet) for lesson extraction only. Cost is minimal (1 call per run). This isolates "can a good teacher help a weak student?" from "can a weak student teach itself?"

### 8.5. Lesson Context Pollution

Injecting 5-10 lessons into the system prompt adds ~500-1000 tokens of instructions. Even if lessons are correct, they compete with the task description for attention. On small models (nano), this can degrade performance by diluting the signal.

**Fix:** Cap lessons at 3 per run. Measure prompt length as a covariate. Test whether *any* additional system prompt text (even random) degrades nano performance.

### 8.6. ON/OFF Is Not Truly Controlled

"ON" runs both *retrieve* and *generate* lessons. "OFF" runs do neither. The ON arm has two extra LLM calls per run (retrieval scoring + critic extraction). This means ON runs use more tokens, take longer, and have more points of failure — even if lessons are neutral.

**Fix:** Separate retrieval from generation. Test: (a) retrieve only, (b) generate only, (c) both, (d) neither. Or at minimum, ensure OFF runs have identical token budgets by padding with inert text.

### 8.7. Watchdog State Leaks Between Runs

The `loop_watchdog_state.json` persists across experiments. If a prior experiment triggered safe mode, subsequent runs may be throttled without the experimenter knowing.

**Fix:** Clear `loop_watchdog_state.json` alongside lesson stores before each experiment.

### 8.8. No Statistical Significance Testing

Current reports show raw deltas (e.g., "-20 pp") without confidence intervals or p-values. With N=10, a 20pp difference is not necessarily significant.

**Fix:** Use Fisher's exact test for pass/fail proportions. Report p-value. Require p < 0.10 for any claim.

---

## 9. Two-Week Execution Plan

### Week 1: Simplify + Calibrate

| Day | Task | Checkpoint |
|-----|------|------------|
| 1 | Extract core agent loop from `agent_cli.py` into `agent_loop.py` (~300 lines). Keep `agent_cli.py` as backward-compat wrapper. | New module passes `pytest tests/test_cli_track.py` |
| 2 | Delete V1 lesson code paths. Single store: `lessons_v2.jsonl`. Remove `lessons.jsonl` migration code. | `grep -r "lessons\.jsonl" tracks/cli_sqlite/` returns only V2 references |
| 3 | Disable self-improvement pipeline for benchmarks (feature flag, default off). Remove skill patching from benchmark path. | No `self_improve_cli` imports in benchmark code path |
| 3 | Collapse `lesson_retrieval_v2.py` two-lane system to single-lane. Remove transfer lane. | Retrieval returns results from single scoring function |
| 4 | Create single `run_benchmark.py` script that replaces all 8 runners. Config via JSON file. | Can reproduce a 10-run ON/OFF experiment with one command |
| 5 | Calibrate OFF baselines: run each of 4 canonical tasks 10x with `--no-skills`, find step budget that gives 40-60% pass rate. | Documented baselines for each task |

### Week 2: Prove or Kill

| Day | Task | Checkpoint |
|-----|------|------------|
| 6-7 | Run Phase 1 protocol (all 4 tasks, 3 batches each). | Raw data in `reports/phase1/` |
| 8 | Analyze Phase 1: compute Δ, p-values, confidence intervals per task. | Summary table: which tasks show significant lift? |
| 9 | If ≥2 tasks pass: begin Phase 2 (transfer). If 0 tasks pass: debug lesson content. | Go/no-go decision documented |
| 10 | Write final report: "Learning works on X tasks with Y lift" or "Learning doesn't work, here's why." | Published to `docs/` |

### Hard Go/No-Go Decision Points

- **End of Day 5:** If baseline calibration shows all tasks are at 0% or 100% pass rate, the benchmark suite needs redesign. Stop and fix tasks.
- **End of Day 8:** If zero tasks show Δ > 0 across all 3 batches, pause Phase 2 and investigate lesson quality (read actual lesson text, check for poisoned rules, test stronger critic model).
- **End of Day 10:** If ≥2 tasks show Δ ≥ +20pp with p < 0.10, architecture is validated. Proceed to transfer experiments. Otherwise, the learning loop needs fundamental redesign before adding more features.

---

## 10. Final Verdict

**❌ Needs simplification first.**

The system has ~17,000 lines of production code and ~9,000 lines of tests for a hypothesis that hasn't been validated yet. The core question — "do lessons help?" — requires ~2,000 lines of code and 40 benchmark runs to answer definitively.

**The risk is not that the architecture is wrong. The risk is that the architecture is hiding the answer.** With this many moving parts, confounders, and code paths, a null result could mean "learning doesn't work" or "learning works but something else broke." You can't distinguish the two.

Simplify to the point where a null result is *informative*, then scale back up.
