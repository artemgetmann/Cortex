# SAGE Self-Edit ON/OFF Compare

## Verdict

- verdict: `no_improvement`
- reason: `self-edit ON did not beat OFF on transfer-first criteria`

## Transfer-First Metrics

| metric | self_edit_off | self_edit_on | delta_or_improvement |
|---|---:|---:|---:|
| transfer_pass_rate | 0.00% | 0.00% | +0.0000 |
| overall_pass_rate | 0.00% | 0.00% | +0.0000 |
| transfer_median_steps_to_success (improvement=off-on) | n/a | n/a | n/a |
| transfer_median_repeated_error_delta (improvement=off-on) | -0.5000 | -0.5000 | 0.0000 |
| transfer_mean_lesson_activations | 3.0000 | 0.0000 | -3.0000 |
| transfer_mean_retrieval_help_ratio | 0.3333 | 0.0000 | -0.3333 |
| did_learning_improve (runner-level) | 0 | 0 | +0 |

## Config

- sessions: `5`
- suite: `sqlite`
- arm: `docs_on__mode_lossy__lessons_on`
- benchmark_deterministic: `True`
- benchmark_promoted_only: `True`
- llm_backend: `anthropic`
- cost_profile: `cheap`

## Artifacts

- self_edit_off_json: `/Users/user/Programming_Projects/Cortex/.worktree/sage-experiment/tracks/cli_sqlite/reports/sage_self_edit_off.json`
- self_edit_on_json: `/Users/user/Programming_Projects/Cortex/.worktree/sage-experiment/tracks/cli_sqlite/reports/sage_self_edit_on.json`
