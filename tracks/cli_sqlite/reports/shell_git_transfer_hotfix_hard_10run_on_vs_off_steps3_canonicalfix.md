# Shell Git Transfer Hotfix Hard: 10-run ON/OFF (step=3, canonicalfix)

## Setup
- Task: `shell_git_transfer_hotfix_hard`
- Executor/Judge: `claude-haiku-4-5` (API backend)
- Docs: on/lossy + retrieval auto (`tracks/cli_sqlite/domains/docs/shell-git-reference.md`)
- Contract gap retry: on (1 retry)
- Structured lessons required: on
- ON sessions: `149100-149109`
- OFF sessions: `149200-149209` (`--no-posttask-learn`)

## Key Results
- ON pass rate: `90%` (9/10)
- OFF pass rate: `100%` (10/10)
- ON last-5 pass rate: `100%`
- OFF last-5 pass rate: `100%`
- ON median steps (successes): `3.00`
- OFF median steps (successes): `3.00`
- ON mean lesson activations: `0.40`
- OFF mean lesson activations: `0.00`

## Per-run Pass/Fail
| Arm | Run | Session | Pass | Steps | Tool Errors | Lesson Activations |
|---|---:|---:|:---:|---:|---:|---:|
| lessons_on | 1 | 149100 | N | 3 | 1 | 0 |
| lessons_on | 2 | 149101 | Y | 3 | 0 | 0 |
| lessons_on | 3 | 149102 | Y | 3 | 0 | 0 |
| lessons_on | 4 | 149103 | Y | 3 | 0 | 0 |
| lessons_on | 5 | 149104 | Y | 3 | 1 | 2 |
| lessons_on | 6 | 149105 | Y | 3 | 0 | 0 |
| lessons_on | 7 | 149106 | Y | 3 | 0 | 0 |
| lessons_on | 8 | 149107 | Y | 3 | 0 | 0 |
| lessons_on | 9 | 149108 | Y | 3 | 0 | 0 |
| lessons_on | 10 | 149109 | Y | 3 | 1 | 2 |
| lessons_off | 1 | 149200 | Y | 3 | 0 | 0 |
| lessons_off | 2 | 149201 | Y | 3 | 0 | 0 |
| lessons_off | 3 | 149202 | Y | 3 | 2 | 0 |
| lessons_off | 4 | 149203 | Y | 3 | 1 | 0 |
| lessons_off | 5 | 149204 | Y | 3 | 0 | 0 |
| lessons_off | 6 | 149205 | Y | 3 | 0 | 0 |
| lessons_off | 7 | 149206 | Y | 3 | 1 | 0 |
| lessons_off | 8 | 149207 | Y | 3 | 0 | 0 |
| lessons_off | 9 | 149208 | Y | 3 | 1 | 0 |
| lessons_off | 10 | 149209 | Y | 3 | 0 | 0 |

## Failure Gap Taxonomy (failed runs only)
### lessons_on
| reason_code | gap_type | count |
|---|---|---:|
| missing_required_file_content_pattern | required_file_content_pattern | 6 |
| missing_required_file | required_file | 2 |
- Top unresolved signatures:
  - `missing_required_file|required_file|target_repo/hotfix_alpha.txt` x1
  - `missing_required_file|required_file|target_repo/transfer_summary.txt` x1
  - `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_alpha.txt::(?is)Retry profile alpha` x1
  - `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_alpha.txt::(?is)Set initial delay to 275ms` x1
  - `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_BRANCH\s+main$` x1

### lessons_off
- No failed runs -> no unresolved post-retry gaps.

## Metric Glossary + How to Read This
- `pass_rate`: percent of runs that fully passed contract checks. High = more reliable task completion.
- `last-5 pass rate`: pass rate on runs 6-10. High = late-curve stability (learning/convergence).
- `median_steps_to_success`: middle step count among passing runs. Low = faster completion.
- `mean lesson activations`: average number of lessons actually used in a run. High = learning memory is being applied.
- `failure gap taxonomy`: grouped unresolved contract gaps after retry in failed runs. Concentration in one gap = specific fix target.

## Readout
- The canonicalization fix removed the prior command-shape validator mismatch bottleneck.
- This task is now saturated: OFF already hits 100%, so it is no longer a good test of learning lift.
- Next: move to a harder transfer task/stricter contract where OFF < ON and late-curve ON can prove >=80% without saturation.
