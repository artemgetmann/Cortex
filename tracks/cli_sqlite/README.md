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

Run tests:

```bash
python3 -m pytest tracks/cli_sqlite/tests -q
```

Run demo (clean output):

```bash
AUTO_TIMELINE=1 AUTO_TOKEN_REPORT=1 \
bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh --pretty
```

## Notes

- Runtime artifacts are under `tracks/cli_sqlite/sessions/` and `tracks/cli_sqlite/learning/`.
- `--learning-mode strict` is the default benchmark mode.
- For transfer/holdout protocol details, see `docs/MEMORY-V2-BENCHMARKS.md`.
