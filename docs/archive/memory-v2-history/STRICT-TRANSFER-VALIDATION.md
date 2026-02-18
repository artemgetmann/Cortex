# Strict Transfer Validation

Use these commands to validate strict-transfer behavior end-to-end.

## Preconditions

- Set `ANTHROPIC_API_KEY` in your shell.
- Run from repo root.

## Test Suite (offline)

```bash
python3 -m pytest tracks/cli_sqlite/tests -q
```

Expected signature:
- All tests pass (current baseline evolves; re-check local output).

## Strict In-Domain Run (gridtool)

```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id aggregate_report \
  --domain gridtool \
  --learning-mode strict \
  --session 13001 \
  --max-steps 8 \
  --bootstrap \
  --mixed-errors
```

Expected signature:
- Metrics include `"learning_mode": "strict"`.
- Strict path runs without hardcoded critic examples.

## Strict Holdout Run (fluxtool)

```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id aggregate_report_holdout \
  --domain fluxtool \
  --learning-mode strict \
  --session 13002 \
  --max-steps 8 \
  --bootstrap \
  --mixed-errors
```

Expected signature:
- Metrics include `"domain": "fluxtool"` and `"learning_mode": "strict"`.
- Executor tool usage is `run_fluxtool` with remapped syntax.

## Cross-Domain Transfer Run

```bash
python3 tracks/cli_sqlite/scripts/run_cross_domain.py \
  --train-domain gridtool \
  --test-domain fluxtool \
  --train-task-id aggregate_report \
  --test-task-id aggregate_report_holdout \
  --learning-mode strict \
  --train-sessions 3 \
  --test-sessions 5 \
  --start-session 13100 \
  --max-steps 8 \
  --bootstrap \
  --mixed-errors \
  --clear-lessons
```

Expected signature:
- Output includes transfer metrics:
  - `first_pass_index`
  - `post_pass_regressions`
  - `delta`
- JSON summary block is printed at the end.

## Legacy Sanity Run

```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id aggregate_report \
  --domain gridtool \
  --learning-mode legacy \
  --session 13003 \
  --max-steps 8 \
  --bootstrap \
  --mixed-errors
```

Expected signature:
- Metrics include `"learning_mode": "legacy"`.
- Legacy critic behavior remains available.

## Offline Holdout Smoke Check (no API)

```bash
python3 tracks/cli_sqlite/domains/fluxtool.py \
  --workdir tracks/cli_sqlite/tasks/aggregate_report_holdout <<'EOF'
IMPORT "fixture.csv"
GROUP region => total=sum(amount), cnt=count(amount)
SORT total down
DISPLAY
EOF
```

Expected signature:
- CSV output headed by `region,total,cnt` with sorted totals.

## Architecture A/B Benchmark (Full vs Simplified)

Use this to compare the current 3-role architecture against the simplified mode.

```bash
python3 tracks/cli_sqlite/scripts/run_architecture_ab.py \
  --domain fluxtool \
  --task-id aggregate_report_holdout \
  --learning-mode strict \
  --sessions 10 \
  --start-session 37000 \
  --max-steps 8 \
  --bootstrap \
  --mixed-errors \
  --clear-lessons-between-arms \
  --output-json tracks/cli_sqlite/artifacts/ab/manual_fluxtool_ab.json \
  --output-md tracks/cli_sqlite/artifacts/ab/manual_fluxtool_ab.md
```

Expected signature:
- Output table includes `full` and `simplified` arms with pass-rate and error deltas.
- JSON payload includes `config`, `arms`, `deltas`, `runs`, and optional `caveats`.
- Canonical interpretation should be recorded in `docs/AB-FINDINGS.md`.
