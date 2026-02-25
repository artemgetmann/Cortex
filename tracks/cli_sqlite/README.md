# CLI SQLite Track

Track-local guide for the Memory V2 CLI lab.

For project narrative and demo context, use root `README.md`.
For canonical docs index, use `docs/README.md`.

## Scope

- Fast multi-domain harness for Memory V2 (`gridtool`, `fluxtool`, `sqlite`, `shell`, `artic`).
- Runtime + retrieval + promotion behavior lives in this track.
- FL Studio computer-use path is separate and documented under `docs/archive/fl-studio-legacy/`.

## Key Files

- `tracks/cli_sqlite/agent_cli.py`: main CLI loop and Memory V2 integration.
- `tracks/cli_sqlite/adapter_registry.py`: centralized domain-adapter resolution.
- `tracks/cli_sqlite/error_capture.py`: universal failure signal capture.
- `tracks/cli_sqlite/lesson_store_v2.py`: lesson persistence/lifecycle store.
- `tracks/cli_sqlite/lesson_retrieval_v2.py`: pre-run and on-error retrieval.
- `tracks/cli_sqlite/semantic_index.py`: deterministic semantic similarity helper (feature-flagged use in retrieval).
- `tracks/cli_sqlite/lesson_promotion_v2.py`: utility-based promote/suppress logic.
- `tracks/cli_sqlite/curriculum_planner.py`: fixed/auto task scheduler for learning-curve runs.
- `tracks/cli_sqlite/scripts/run_cli_agent.py`: single-session runner.
- `tracks/cli_sqlite/scripts/run_mixed_benchmark.py`: mixed protocol benchmark runner.
- `tracks/cli_sqlite/scripts/report_run_health.py`: run-health summary with transfer and gap-resolution proxies.
- `tracks/cli_sqlite/scripts/run_hackathon_demo.sh`: 3-wave demo wrapper.

## Typical Tasks

- `import_aggregate`
- `incremental_reconcile`
- `aggregate_report`
- `aggregate_report_holdout`
- `shell_excel_build_report`
- `shell_git_train_release_flow`
- `shell_git_transfer_hotfix`
- `shell_git_transfer_hotfix_hard` (session-seeded runtime variant contract)

## Core Commands

Run one session:

```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id import_aggregate \
  --session 1001 \
  --verbose
```

Run executor turns through Claude subscription (`claude -p`) instead of API:

```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id import_aggregate \
  --session 1002 \
  --llm-backend claude_print \
  --no-posttask-learn \
  --verbose
```

Run with documentation-aware executor+judge (lossy retrieval mode):

```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id import_aggregate \
  --domain sqlite \
  --session 1003 \
  --llm-backend claude_print \
  --documentation tracks/cli_sqlite/domains/docs/sqlite-reference.md \
  --doc-mode lossy \
  --doc-retrieval auto \
  --doc-budget-tokens 900 \
  --executor-docs on \
  --judge-docs on
```

Run with deterministic low-confidence verifier stack (probe + clarify path):

```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id shell_git_transfer_hotfix \
  --domain shell \
  --session 1004 \
  --judge-diagnostic \
  --verifier-stack \
  --low-confidence-threshold 0.7 \
  --clarify-on-low-confidence \
  --max-low-confidence-probes 4
```

Run tests:

```bash
python3 -m pytest tracks/cli_sqlite/tests -q
```

Run demo (clean output):

```bash
AUTO_TIMELINE=1 AUTO_TOKEN_REPORT=1 \
bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh --pretty
```

Run real-world learning benchmark pack (ablations: docs on/off, lossy/full, lessons on/off):

```bash
python3 tracks/cli_sqlite/scripts/run_realworld_learning_benchmark.py \
  --sessions 5 \
  --start-session 73001 \
  --learning-mode strict \
  --llm-backend anthropic \
  --model-judge claude-haiku-4-5 \
  --judge-diagnostic \
  --output-json tracks/cli_sqlite/reports/realworld_learning_benchmark.json \
  --output-md tracks/cli_sqlite/reports/realworld_learning_benchmark.md
```

Run learning curve with adaptive curriculum planner (task selection from recent failures):

```bash
python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --domain sqlite \
  --task-id import_aggregate \
  --curriculum-mode auto \
  --sessions 10 \
  --start-session 79001
```

Run a fast SQLite-only 5-run curve (docs on + lossy + lessons on):

```bash
python3 tracks/cli_sqlite/scripts/run_realworld_learning_benchmark.py \
  --sessions 10 \
  --start-session 78301 \
  --suite sqlite --suite git \
  --arm docs_on__mode_lossy__lessons_on \
  --max-steps 6 \
  --llm-backend anthropic \
  --model-judge claude-haiku-4-5 \
  --judge-diagnostic \
  --output-json tracks/cli_sqlite/reports/realworld_curve_transfer_hard_10run.json \
  --output-md tracks/cli_sqlite/reports/realworld_curve_transfer_hard_10run.md
```

Run a deeper pass (10+ sessions per arm):

```bash
python3 tracks/cli_sqlite/scripts/run_realworld_learning_benchmark.py \
  --sessions 10 \
  --start-session 74001
```

## Notes

- Runtime artifacts are under `tracks/cli_sqlite/sessions/` and `tracks/cli_sqlite/learning/`.
- Each session now includes `docs_artifacts.json`, `learning_artifacts.json`, and `prompt_artifacts.json`.
- `prompt_artifacts.json` captures exact executor/judge input bundles (system prompt, task payload, docs, skill routing, and judge rationale context).
- `--learning-mode strict` is the default benchmark mode.
- `run_learning_curve.py` now supports `--curriculum-mode fixed|auto` (default `fixed` for backward compatibility).
- Retrieval now supports optional semantic scoring in `lesson_retrieval_v2` (default off; lexical baseline remains unchanged unless enabled).
- `lesson_store_v2` writes are hardened with sidecar file-locking + atomic replace to avoid concurrent writer clobber.
- Benchmark default backend is API (`anthropic`) with Haiku 4.5.
- Critic tuning flags are intentionally hidden in benchmark runners; critic stays locked to executor-equivalent behavior.
- `--judge-diagnostic` forces judge rationale capture even on contract-pass runs while keeping contract pass/fail authoritative.
- `--benchmark-deterministic` forces `temperature=0` for executor/judge/lesson-generation calls (API path) for repeatable benchmark runs.
- `--benchmark-promoted-only` restricts retrieval to promoted lessons only (candidates excluded) during benchmark runs.
- `--verifier-stack` adds deterministic post-eval checks for low-confidence outcomes. Probe sources:
  - `CONTRACT.json` (when present)
  - `task.md` inferred anchors (exact verification lines + obvious output files)
  - optional `VERIFICATION.json` per task (`exact_output_lines`, `required_files`, `required_file_content_patterns`, optional `required_queries`)
- If low-confidence probes are still inconclusive, runtime emits a deterministic clarifying question (`metrics.verifier_clarifying_question` + `verifier_clarify` event).
- Learning is credited only when transfer pass lifts and mechanism metrics engage (`lesson_activations > 0`, `retrieval_help_ratio` lift).
- For transfer/holdout protocol details, see `docs/MEMORY-V2-BENCHMARKS.md`.
- Latest SQLite benchmark write-up: `tracks/cli_sqlite/reports/benchmark_report_sqlite_2026-02-21.md`.
