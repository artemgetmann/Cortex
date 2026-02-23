# Transfer-Only 10-Run Check (Step-Cap Retry Fix)

## What changed
- Contract-gap retry now triggers in two cases:
  - model stops with no tool call (`trigger=no_tool_call`)
  - step budget is reached with unresolved contract gaps (`trigger=step_cap`)
- This prevents silent failures where no deterministic retry was attempted before final evaluation.

## Setup
- Task: `shell_git_transfer_hotfix`
- Domain: `shell`
- Sessions per arm: `10`
- Max steps: `4`
- Model: executor/judge = `claude-haiku-4-5` (API backend)
- Retry: `contract-gap-retry=on`, `contract-gap-retry-steps=1`
- Structured lessons: `required`
- Judge diagnostic: `on`

## Arm comparison
| arm_id | pass_rate | runs_6_10_pass_rate | median_steps_to_success | retry_used_runs | transfer_pass_delta | activation_delta | retrieval_help_ratio_delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| `docs_on__mode_lossy__lessons_on` | 90.00% | 100.00% | 3 | 5 | 0.0000 | 0.0000 | 0.0000 |
| `docs_off__mode_none__lessons_on` | 90.00% | 100.00% | 4 | 3 | 0.0000 | 0.0000 | 0.0000 |

## Failure gap taxonomy
- `docs_on__mode_lossy__lessons_on`:
  - reason_codes: `missing_required_event_pattern=1`
  - top unresolved signature:
    - `missing_required_event_pattern|required_event_pattern|(?is)git\\s+am\\s+\\.\\./hotfix\\.patch`
- `docs_off__mode_none__lessons_on`:
  - reason_codes: `missing_required_event_pattern=1`, `missing_required_file=2`
  - top unresolved signatures:
    - `missing_required_event_pattern|required_event_pattern|(?is)git\\s+am\\s+\\.\\./hotfix\\.patch`
    - `missing_required_file|required_file|target_repo/hotfix.txt`
    - `missing_required_file|required_file|target_repo/transfer_summary.txt`

## Decision
- Core issue fixed: retry is no longer skipped at step cap.
- Docs-on degradation claim is no longer supported on this task: docs-on and docs-off both reached 90% pass with the same strict budget.
- Strict learning proof is still not met because mechanism trend metrics are flat:
  - `activation_delta=0`
  - `retrieval_help_ratio_delta=0`
