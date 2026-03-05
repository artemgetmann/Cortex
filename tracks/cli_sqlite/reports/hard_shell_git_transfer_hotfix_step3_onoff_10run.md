# Hard Transfer Benchmark ON/OFF (10 runs, step cap 3)

- Task: `shell_git_transfer_hotfix_hard`
- Domain: `shell`
- Sessions per arm: `10`
- Max steps: `3`
- Backend: `anthropic`
- Executor/Judge model: `claude-haiku-4-5`
- Docs: on (`lossy`, retrieval `auto`, `tracks/cli_sqlite/domains/docs/shell-git-reference.md`)
- Posttask mode: `candidate`

## Summary Metrics

- ON pass_rate: `0.50`
- ON last5_pass_rate: `0.40`
- ON median_steps_to_success: `3`
- OFF pass_rate: `0.70`
- OFF last5_pass_rate: `0.40`
- OFF median_steps_to_success: `3`
- Delta ON-OFF pass_rate (pp): `-20.0`
- mean_lesson_activations ON/OFF: `0.20 / 0.00`
- mean_retrieval_help_ratio ON/OFF: `0.10 / 0.00`

## ON Per-Run

| session | pass | score | steps | tool_errors | lesson_activations | retrieval_help_ratio |
|---|---:|---:|---:|---:|---:|---:|
| 191000 | 0 | 0.778 | 3 | 0 | 0.0 | 0.0 |
| 191001 | 1 | 1.000 | 3 | 0 | 2.0 | 1.0 |
| 191002 | 0 | 0.778 | 3 | 0 | 0.0 | 0.0 |
| 191003 | 1 | 1.000 | 3 | 1 | 0.0 | 0.0 |
| 191004 | 1 | 1.000 | 3 | 1 | 0.0 | 0.0 |
| 191005 | 0 | 0.778 | 3 | 0 | 0.0 | 0.0 |
| 191006 | 1 | 1.000 | 3 | 1 | 0.0 | 0.0 |
| 191007 | 0 | 0.778 | 3 | 0 | 0.0 | 0.0 |
| 191008 | 0 | 0.778 | 3 | 0 | 0.0 | 0.0 |
| 191009 | 1 | 1.000 | 3 | 1 | 0.0 | 0.0 |

## OFF Per-Run

| session | pass | score | steps | tool_errors | lesson_activations | retrieval_help_ratio |
|---|---:|---:|---:|---:|---:|---:|
| 191200 | 1 | 1.000 | 3 | 1 | 0.0 | 0.0 |
| 191201 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| 191202 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| 191203 | 1 | 1.000 | 3 | 1 | 0.0 | 0.0 |
| 191204 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| 191205 | 0 | 0.778 | 3 | 0 | 0.0 | 0.0 |
| 191206 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| 191207 | 1 | 1.000 | 3 | 1 | 0.0 | 0.0 |
| 191208 | 0 | 0.778 | 3 | 0 | 0.0 | 0.0 |
| 191209 | 0 | 0.778 | 3 | 0 | 0.0 | 0.0 |

## Failure Taxonomy (from `contract_gap_postretry.json` when present)

### ON

- reason_code counts:
  - `missing_required_event_pattern`: 15
  - `matched_forbidden_event_pattern`: 5
- gap_type counts:
  - `required_event_pattern`: 15
  - `forbidden_event_pattern`: 5
- top gap_signature counts (top 5):
  - `missing_required_event_pattern|required_event_pattern|(?is)git\s+init\s+source_repo`: 5
  - `missing_required_event_pattern|required_event_pattern|(?is)git\s+init\s+target_repo`: 5
  - `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_gamma.patch`: 5
  - `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 5

### OFF

- reason_code counts:
  - `missing_required_event_pattern`: 9
  - `matched_forbidden_event_pattern`: 3
- gap_type counts:
  - `required_event_pattern`: 9
  - `forbidden_event_pattern`: 3
- top gap_signature counts (top 5):
  - `missing_required_event_pattern|required_event_pattern|(?is)git\s+init\s+source_repo`: 3
  - `missing_required_event_pattern|required_event_pattern|(?is)git\s+init\s+target_repo`: 3
  - `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_gamma.patch`: 3
  - `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 3
