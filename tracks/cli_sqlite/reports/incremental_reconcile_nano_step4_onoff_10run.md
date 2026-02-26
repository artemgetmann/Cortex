# Incremental Reconcile Nano: ON vs OFF (10 runs)

- Task: `incremental_reconcile_nano`
- Domain: `sqlite`
- Model/backend: `gpt-5-nano` via `openai`
- Settings: docs on (lossy), deterministic on, promoted-only on, step cap=4

## Results
- ON: pass_rate=60% (6/10), last5_pass_rate=60% (3/5), median_steps_on_pass=4.0, mean_v2_lesson_activations_effective=2.50, mean_v2_retrieval_help_ratio_effective=0.70
- OFF: pass_rate=40% (4/10), last5_pass_rate=20% (1/5), median_steps_on_pass=4.0, mean_v2_lesson_activations_effective=0.00, mean_v2_retrieval_help_ratio_effective=0.00

## Delta (ON - OFF)
- pass_rate_delta: +0.20
- last5_pass_rate_delta: +0.40
- activation_effective_delta: +2.50
- retrieval_help_effective_delta: +0.70

## Per-run

| arm | run | session | pass | score | steps | errors | reasons |
|---|---:|---:|---|---:|---:|---:|---|
| on | 1 | 142600 | Y | 1.00 | 4 | 1 |  |
| on | 2 | 142601 | N | 0.67 | 4 | 3 | required_query_mismatch, too_many_errors |
| on | 3 | 142602 | N | 0.50 | 3 | 0 | required_query_mismatch |
| on | 4 | 142603 | Y | 1.00 | 4 | 0 |  |
| on | 5 | 142604 | Y | 1.00 | 4 | 0 |  |
| on | 6 | 142605 | N | 0.83 | 4 | 2 | required_query_mismatch |
| on | 7 | 142606 | Y | 1.00 | 4 | 0 |  |
| on | 8 | 142607 | Y | 1.00 | 4 | 2 |  |
| on | 9 | 142608 | N | 0.83 | 4 | 2 | required_query_mismatch |
| on | 10 | 142609 | Y | 1.00 | 4 | 1 |  |
| off | 1 | 142700 | Y | 1.00 | 4 | 1 |  |
| off | 2 | 142701 | N | 0.50 | 4 | 2 | required_query_mismatch |
| off | 3 | 142702 | Y | 1.00 | 4 | 0 |  |
| off | 4 | 142703 | N | 0.83 | 4 | 1 | required_query_mismatch |
| off | 5 | 142704 | Y | 1.00 | 4 | 1 |  |
| off | 6 | 142705 | Y | 1.00 | 4 | 0 |  |
| off | 7 | 142706 | N | 0.83 | 4 | 2 | required_query_mismatch |
| off | 8 | 142707 | N | 0.83 | 4 | 2 | required_query_mismatch |
| off | 9 | 142708 | N | 0.83 | 4 | 2 | required_query_mismatch |
| off | 10 | 142709 | N | 0.83 | 4 | 3 | too_many_errors |
