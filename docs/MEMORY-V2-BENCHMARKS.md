# Memory V2 Benchmarks

## Canonical References
- Current architecture map: `docs/MEMORY-V2-CURRENT-FLOW.html`
- Legacy FL Studio map: `docs/archive/fl-studio-legacy/cortex-architecture.html`
- Diagram comparison: `docs/MEMORY-V2-ARCHITECTURE-COMPARE.md`

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
Run stability protocol (strict lane default):

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

Run the mixed 5-phase protocol in one command (`grid -> fluxtool -> shell(excel) -> sqlite -> grid retention`):

```bash
python3 tracks/cli_sqlite/scripts/run_mixed_benchmark.py \
  --grid-task-id aggregate_report \
  --fluxtool-task-id aggregate_report_holdout \
  --shell-task-id shell_excel_build_report \
  --sqlite-task-id import_aggregate \
  --retention-runs 1 \
  --start-session 52001 \
  --max-steps 8 \
  --learning-mode strict \
  --posttask-mode candidate \
  --output-json tracks/cli_sqlite/sessions/memory_mixed_52001.json
```

Run strict-only vs auto-transfer pressure benchmark (same seed, cloned learning state):

```bash
python3 tracks/cli_sqlite/scripts/run_transfer_pressure.py \
  --seed-domain gridtool \
  --seed-task-id aggregate_report \
  --pressure-domain fluxtool \
  --pressure-task-id aggregate_report_holdout \
  --seed-sessions 3 \
  --pressure-sessions 5 \
  --start-session 53001 \
  --max-steps 8 \
  --learning-mode strict \
  --bootstrap \
  --mixed-errors \
  --cryptic-errors \
  --output-json tracks/cli_sqlite/sessions/transfer_pressure_53001.json \
  --output-md tracks/cli_sqlite/sessions/transfer_pressure_53001.md
```

Inspect one session as a visual timeline:

```bash
python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py \
  --session 16001 \
  --show-ok-steps \
  --show-all-tools \
  --show-tool-output \
  --show-lessons 8
```

Check strict-vs-transfer behavior on the same task (no script-level aggregate yet):

```bash
# strict (default, transfer off)
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id shell_excel_build_report \
  --domain shell \
  --session 17001 \
  --max-steps 5 \
  --bootstrap \
  --learning-mode strict \
  --posttask-mode candidate

# transfer lane enabled
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id shell_excel_build_report \
  --domain shell \
  --session 17002 \
  --max-steps 5 \
  --bootstrap \
  --learning-mode strict \
  --posttask-mode candidate \
  --enable-transfer-retrieval
```

Compare `metrics.json` fields:
- `v2_transfer_retrieval_enabled`
- `v2_transfer_lane_activations`
- `v2_prerun_lesson_ids`
- `v2_lesson_activations`
- `v2_retrieval_help_ratio`

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
