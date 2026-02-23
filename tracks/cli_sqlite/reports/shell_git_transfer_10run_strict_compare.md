# Shell Git Transfer 10-Run Strict Comparison

## Setup
- task: `shell_git_transfer_hotfix`
- domain: `shell`
- sessions per arm: `10`
- max_steps: `4`
- model: executor/judge `claude-haiku-4-5` via API
- docs: `on`, `lossy`, retrieval `auto`
- retry: contract-gap retry `on` (1)
- structured lessons: `required`

## Results
| arm | pass_rate | last5_pass_rate | median_steps_success | mean_lesson_activations | mean_retrieval_help_ratio | activation_nonzero_runs | retrieval_positive_runs |
|---|---:|---:|---:|---:|---:|---:|---:|
| lessons_on | 90.00% | 100.00% | 4 | 0.4000 | 0.2000 | 2 | 2 |
| lessons_off | 90.00% | 100.00% | 4 | 0.0000 | 0.0000 | 0 | 0 |

## Per-step Lesson Activations (mean per run)
- lessons_on: `{"3": 0.4}`
- lessons_off: `{}`

## Gap Taxonomy (post-retry unresolved)
- lessons_on reason_codes: `{"missing_required_event_pattern": 1}`
- lessons_off reason_codes: `{"missing_required_event_pattern": 1}`

## Strict Gate
- criterion: `{"activation_nonzero_required": true, "last5_pass_rate_min": 0.8, "retrieval_trend_positive_required": true}`
- verdict: `NO-GO`
- rationale: lessons_on(last5=100.00%, activation_nonzero_runs=2, retrieval_delta=0.0000, pass_rate_delta_vs_off=+0.00%)
