# Architecture A/B Summary

## Config

- domain: `gridtool`
- task_id: `aggregate_report`
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
| full | 80.00% | 0.800 | 4.00 | 1.20 | 65237 | 217.30 |
| simplified | 90.00% | 0.900 | 3.60 | 0.80 | 60109 | 128.63 |

## Delta (simplified - full)

- pass_rate: `+10.00%`
- mean_score: `+0.100`
- mean_steps: `-0.40`
- mean_tool_errors: `-0.40`
- total_tokens_est: `-5128`
- total_elapsed_s: `-88.67`
