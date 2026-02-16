# Architecture A/B Findings (Full vs Simplified)

This document is the canonical evidence log for `architecture_mode` benchmarks in `tracks/cli_sqlite`.

## Question

Does the current 3-role architecture (`full`) beat a simplified path (`simplified`) where post-task reflection is collapsed and post-task skill patching is disabled?

## Benchmark Protocol

- Runner: `tracks/cli_sqlite/scripts/run_architecture_ab.py`
- Arms:
  - `full`: existing architecture path.
  - `simplified`: executor reused for judge/lesson generation path and skill-patch stage skipped by mode.
- Mode: `--learning-mode strict --bootstrap --mixed-errors`
- Comparison hygiene:
  - `--clear-lessons-between-arms` to avoid cross-arm leakage.
  - Same task, model, and step budget per arm.

## Latest Large Run (2026-02-15)

Command used:

```bash
SESSIONS_PER_ARM=10 START_GRID=36000 START_FLUX=37000 MAX_STEPS=8 LEARNING_MODE=strict \
  tracks/cli_sqlite/scripts/run_demo_ab_pack.sh
```

Artifacts:
- `tracks/cli_sqlite/artifacts/ab/20260215-210050/gridtool_ab.json`
- `tracks/cli_sqlite/artifacts/ab/20260215-210050/fluxtool_ab.json`

### Results

| domain | full pass_rate | simplified pass_rate | delta (simp-full) | winner |
|---|---:|---:|---:|---|
| gridtool (`aggregate_report`) | 80.00% | 90.00% | +10.00% | simplified |
| fluxtool (`aggregate_report_holdout`) | 100.00% | 60.00% | -40.00% | full |

Supporting metrics snapshot:
- Gridtool:
  - full: `mean_score=0.800`, `mean_steps=4.00`, `mean_tool_errors=1.20`
  - simplified: `mean_score=0.900`, `mean_steps=3.60`, `mean_tool_errors=0.80`
- Fluxtool:
  - full: `mean_score=1.000`, `mean_steps=3.80`, `mean_tool_errors=0.80`
  - simplified: `mean_score=0.615`, `mean_steps=5.60`, `mean_tool_errors=3.50`

## Earlier Small-Sample A/B (2026-02-15, corrected runner)

These are the earlier `sessions=3` runs used during implementation checks:

- Gridtool:
  - full: `pass_rate=0.667`
  - simplified: `pass_rate=0.000`
- Fluxtool:
  - full: `pass_rate=1.000`
  - simplified: `pass_rate=0.000`

These runs were noisy/small but directionally suggested full > simplified before the larger run.

## Interpretation

- The result is domain-dependent, not a single global winner.
- For simpler in-domain syntax recovery (`gridtool`), simplified can match or exceed full in this sample.
- For holdout/remapped syntax (`fluxtool`), full architecture provided a major reliability advantage.

## Demo-Safe Claim

Use this claim in demos:

> We built and benchmarked two architectures, and the tradeoff is measurable:
> simplified is faster/leaner and can win on easier domains, while the fuller architecture is more robust on harder holdout domains.

Avoid this claim:

> “One architecture is universally best.”

## Reproduce

Single domain:

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
