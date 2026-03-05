# Hard Transfer Benchmark ON/OFF (10 runs, step cap 3, post-contract guidance)

- Task: `shell_git_transfer_hotfix_hard`
- Domain: `shell`
- Sessions per arm: `10`
- Max steps: `3`
- Backend: `anthropic`
- Executor/Judge model: `claude-haiku-4-5`
- Docs: on (`lossy`, retrieval `auto`, `tracks/cli_sqlite/domains/docs/shell-git-reference.md`)
- Posttask mode: `candidate`

## Summary Metrics

- ON pass_rate: `0.90`
- ON last5_pass_rate: `0.80`
- ON median_steps_to_success: `3`
- OFF pass_rate: `0.90`
- OFF last5_pass_rate: `0.80`
- OFF median_steps_to_success: `3`
- ON-OFF pass delta (pp): `0.0`
- mean_lesson_activations ON/OFF: `0.00 / 0.00`
- mean_retrieval_help_ratio ON/OFF: `0.00 / 0.00`

## Per-Run Table

| arm | session | pass | score | steps | tool_errors | lesson_activations | retrieval_help_ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| ON | 192000 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| ON | 192001 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| ON | 192002 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| ON | 192003 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| ON | 192004 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| ON | 192005 | 0 | 0.944 | 3 | 0 | 0.0 | 0.0 |
| ON | 192006 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| ON | 192007 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| ON | 192008 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| ON | 192009 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192200 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192201 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192202 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192203 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192204 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192205 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192206 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192207 | 0 | 0.944 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192208 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |
| OFF | 192209 | 1 | 1.000 | 3 | 0 | 0.0 | 0.0 |

## Failure Taxonomy (from `contract_gap_postretry.json`)

### ON

- reason_code counts:
  - `matched_forbidden_event_pattern`: 1
- gap_type counts:
  - `forbidden_event_pattern`: 1
- top signatures:
  - `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 1

### OFF

- reason_code counts:
  - `matched_forbidden_event_pattern`: 1
- gap_type counts:
  - `forbidden_event_pattern`: 1
- top signatures:
  - `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 1
