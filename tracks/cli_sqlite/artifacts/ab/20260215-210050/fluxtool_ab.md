# Architecture A/B Summary

## Config

- domain: `fluxtool`
- task_id: `aggregate_report_holdout`
- learning_mode: `strict`
- sessions_per_arm: `10`
- max_steps: `8`
- bootstrap: `True`
- mixed_errors: `True`
- cryptic_errors: `False`
- semi_helpful_errors: `False`

## Arm Metrics

| arm | pass_rate | mean_score | mean_steps | mean_tool_errors | total_tokens_est | total_elapsed_s |
|---|---:|---:|---:|---:|---:|---:|
| full | 100.00% | 1.000 | 3.80 | 0.80 | 66636 | 202.12 |
| simplified | 60.00% | 0.615 | 5.60 | 3.50 | 90062 | 156.71 |

## Delta (simplified - full)

- pass_rate: `-40.00%`
- mean_score: `-0.385`
- mean_steps: `+1.80`
- mean_tool_errors: `+2.70`
- total_tokens_est: `+23426`
- total_elapsed_s: `-45.41`
