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
- `tracks/cli_sqlite/lesson_promotion_v2.py`: utility-based promote/suppress logic.
- `tracks/cli_sqlite/scripts/run_cli_agent.py`: single-session runner.
- `tracks/cli_sqlite/scripts/run_mixed_benchmark.py`: mixed protocol benchmark runner.
- `tracks/cli_sqlite/scripts/run_hackathon_demo.sh`: 3-wave demo wrapper.

## Typical Tasks

- `import_aggregate`
- `incremental_reconcile`
- `aggregate_report`
- `aggregate_report_holdout`
- `shell_excel_build_report`
- `shell_git_train_release_flow`
- `shell_git_transfer_hotfix`

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
  --llm-backend claude_print \
  --model-judge claude-haiku-4-5 \
  --auto-escalate-critic off \
  --output-json tracks/cli_sqlite/reports/realworld_learning_benchmark.json \
  --output-md tracks/cli_sqlite/reports/realworld_learning_benchmark.md
```

Run a fast SQLite-only 5-run curve (docs on + lossy + lessons on):

```bash
python3 tracks/cli_sqlite/scripts/run_realworld_learning_benchmark.py \
  --sessions 5 \
  --start-session 78301 \
  --suite sqlite \
  --arm docs_on__mode_lossy__lessons_on \
  --llm-backend claude_print \
  --model-judge claude-haiku-4-5 \
  --auto-escalate-critic off \
  --output-json tracks/cli_sqlite/reports/realworld_curve_sqlite_5run_docs_lossy_lessons_on.json \
  --output-md tracks/cli_sqlite/reports/realworld_curve_sqlite_5run_docs_lossy_lessons_on.md
```

Run a deeper pass (10+ sessions per arm):

```bash
python3 tracks/cli_sqlite/scripts/run_realworld_learning_benchmark.py \
  --sessions 10 \
  --start-session 74001
```

## Notes

- Runtime artifacts are under `tracks/cli_sqlite/sessions/` and `tracks/cli_sqlite/learning/`.
- Each session now includes `docs_artifacts.json` and `learning_artifacts.json`.
- `--learning-mode strict` is the default benchmark mode.
- For transfer/holdout protocol details, see `docs/MEMORY-V2-BENCHMARKS.md`.
- Latest SQLite benchmark write-up: `tracks/cli_sqlite/reports/benchmark_report_sqlite_2026-02-21.md`.
