# Memory V2 Benchmarks

## Purpose
This document defines how to run and read the Memory V2 stability benchmarks for task/domain-agnostic memory.

## Protocol
Run phases in order:
1. `gridtool` warmup runs
2. `fluxtool` interference runs
3. `gridtool` retention runs

The protocol validates:
- unseen-tool adaptation (Phase 2),
- retention when switching back (Phase 3),
- whether lesson utility remains positive.

## Commands
Run stability protocol:

```bash
python3 tracks/cli_sqlite/scripts/run_memory_stability.py \
  --grid-task-id aggregate_report \
  --fluxtool-task-id aggregate_report_holdout \
  --retention-runs 3 \
  --grid-runs 3 \
  --fluxtool-runs 3 \
  --start-session 16001 \
  --max-steps 8 \
  --learning-mode strict \
  --posttask-mode candidate \
  --output-json tracks/cli_sqlite/sessions/memory_stability_16001.json
```

Summarize one or more benchmark payloads:

```bash
python3 tracks/cli_sqlite/scripts/report_memory_health.py \
  --input-json tracks/cli_sqlite/sessions/memory_stability_16001.json \
  --output-json tracks/cli_sqlite/sessions/memory_health_16001.json
```

Summarize directly from session metrics (no benchmark JSON):

```bash
python3 tracks/cli_sqlite/scripts/report_memory_health.py \
  --start-session 16001 \
  --end-session 16030
```

## Required Per-Run Metrics
- `passed` / `score`
- `steps`
- `tool_errors`
- `fingerprint_recurrence_before`
- `fingerprint_recurrence_after`
- `lesson_activations`
- `promoted_count`
- `suppressed_count`
- `retrieval_help_ratio`

## Result Format
`run_memory_stability.py` emits:
- tabular console output per run and per phase
- JSON payload with:
  - `config`
  - `protocol`
  - `phase_summary`
  - `overall_summary`
  - `retention_delta`
  - `runs`

`report_memory_health.py` emits:
- compact text summary
- JSON payload with:
  - `summary`
  - `rows`

## Interpretation
- Healthy trend:
  - `pass_rate` up or stable after warmup
  - `mean_tool_errors` down
  - `fingerprint_recurrence_after` below `fingerprint_recurrence_before`
  - `retrieval_help_ratio` above `0.5`
  - `promoted_count` increasing while `suppressed_count` remains bounded
- Warning trend:
  - retention phase regresses heavily versus warmup
  - suppression dominates promotion
  - retrieval help ratio near zero or negative utility patterns
