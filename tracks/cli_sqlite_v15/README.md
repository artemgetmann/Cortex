# CLI SQLite v1.5 Smoke ON/OFF Wrapper

Minimal wrapper package for running isolated ON/OFF smoke checks against the existing `tracks/cli_sqlite` runner with locked v1.5 policy.

Also includes a locked single-run wrapper used by dispatch/transport layers:
- `tracks/cli_sqlite_v15/run_cli_agent_v15.py`

## Locked Flags

- `llm-backend=openai`
- `model-executor=gpt-5-nano`
- `model-judge=gpt-5-nano`
- `self-edit-mode=off`
- `benchmark-deterministic=on`
- `structured-lessons-required=on`
- `contract-gap-retry=on`
- `contract-gap-deterministic-recipes=on` (enables deterministic structured fallback when model lesson output is invalid)
- `doc-retrieval=auto`
- `doc-mode=lossy`
- `benchmark-promoted-only=off` (candidate + promoted lessons allowed in smoke)
- `judge-diagnostic=on`
- `watchdog-allow-posttask-in-safe-mode=on` (preserve learning writes under safe-mode stress)

## Exact Command Examples

Single run (locked v1.5 profile):

```bash
python3 tracks/cli_sqlite_v15/run_cli_agent_v15.py \
  --task-id shell_git_transfer_hotfix \
  --domain shell \
  --session 260001 \
  --max-steps 6 \
  --verbose
```

```bash
python3 tracks/cli_sqlite_v15/run_smoke_onoff.py \
  --task-id incremental_reconcile \
  --domain sqlite \
  --runs 5 \
  --max-steps 4 \
  --fresh-learning-state \
  --start-session-off 240001 \
  --start-session-on 241001
```

```bash
python3 tracks/cli_sqlite_v15/run_smoke_onoff.py \
  --task-id aggregate_report \
  --domain gridtool \
  --start-session-off 242001 \
  --start-session-on 243001
```

Notes:
- `--runs` defaults to `5`.
- `--max-steps` defaults to `4`.
- `--fresh-learning-state` defaults to `true` (both arms start from empty lessons files).
- OFF arm runs with `--no-posttask-learn` behavior and `--benchmark-placebo`.
- The wrapper snapshots/restores `tracks/cli_sqlite/learning/` so ON/OFF are isolated and repeatable.
- The wrapper fails fast if runtime drifts from locked v1.5 policy (`backend/model/deterministic/gate flags`).

## Output

The script prints one compact JSON line with:

- `off.pass_rate`
- `off.last5_pass_rate`
- `off.activation_mean`
- `off.retrieval_help_mean`
- `on.pass_rate`
- `on.last5_pass_rate`
- `on.activation_mean`
- `on.retrieval_help_mean`
- `delta_on_minus_off.*`

## Artifacts To Inspect

For each session in both arms, inspect:

- `tracks/cli_sqlite/sessions/session-<ID>/metrics.json`
- `tracks/cli_sqlite/sessions/session-<ID>/events.jsonl`

Useful `metrics.json` fields:

- `eval_passed`, `eval_score`
- `v2_lesson_activations`, `v2_lesson_activations_effective`
- `v2_retrieval_help_ratio`, `v2_retrieval_help_ratio_effective`
- `benchmark_placebo`, `benchmark_deterministic`, `benchmark_promoted_only`
- `contract_gap_retry_triggered`, `contract_gap_unresolved_count_final`
- `judge_invoked`, `judge_score`, `judge_reasons`
