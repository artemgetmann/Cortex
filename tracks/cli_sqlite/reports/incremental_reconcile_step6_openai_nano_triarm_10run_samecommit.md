# Incremental Reconcile (Step 6) - GPT-5 Nano - Tri-Arm 10-Run (Same Commit)

Date: 2026-02-26

## Setup
- Task: `incremental_reconcile`
- Domain: `sqlite`
- Sessions per arm: `10`
- Step cap: `6`
- Backend: `openai`
- Models: `gpt-5-nano` executor + judge
- Docs: `on` (`lossy`, retrieval `auto`)
- Contract-gap retry: `on` (1 retry)
- Deterministic benchmark mode: `on`
- Promoted-only retrieval: `on`
- Structured lessons: `required`
- All arms run on the same commit baseline.
- Lesson stores were reset before each arm and restored after experiment.

## Arms
1. `ON` (lessons enabled, deterministic recipes enabled)
2. `OFF` (lessons disabled, deterministic recipes enabled)
3. `ON_NO_DET_RECIPE` (lessons enabled, deterministic recipes disabled)

## Artifacts
- ON log: `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_on_10run_samecommit.log`
- OFF log: `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_off_10run_samecommit.log`
- ON_NO_DET_RECIPE log: `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_on_nodetrecipe_10run_samecommit.log`
- JSON summary: `tracks/cli_sqlite/reports/incremental_reconcile_step6_openai_nano_triarm_10run_samecommit_summary.json`

## Results

| Arm | Pass rate | Last-5 pass rate | Median steps on success |
|---|---:|---:|---:|
| ON | 60% (6/10) | 60% (3/5) | 6 |
| OFF | 60% (6/10) | 60% (3/5) | 6 |
| ON_NO_DET_RECIPE | 10% (1/10) | 0% (0/5) | 6 |

## Mechanism metrics

| Arm | Mean v2 lesson activations | Mean retrieval help ratio | Mean deterministic hints |
|---|---:|---:|---:|
| ON | 1.6 | 0.9 | 2.9 |
| OFF | 0.0 | 0.0 | 2.7 |
| ON_NO_DET_RECIPE | 3.4 | 0.822 | 0.0 |

## Interpretation
- Deterministic repair recipes are the dominant success mechanism in this slice.
  - When recipes are disabled, performance collapses (`10%`).
- ON vs OFF parity (`60%` vs `60%`) means lessons did not produce measurable additional lift here.
- Lessons were active in ON and ON_NO_DET_RECIPE (non-zero activations/help ratios), but that activation did not translate into reliable pass lift under this task/step budget.

## Decision
- Reliability mechanism (deterministic closure policy): **validated**.
- Lesson-only lift claim on this slice: **not validated**.
