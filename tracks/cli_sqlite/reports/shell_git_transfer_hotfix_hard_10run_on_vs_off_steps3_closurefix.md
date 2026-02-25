# Shell Git Transfer Hotfix Hard 10-Run ON vs OFF (steps=3, closure-fix)

## Summary

- lessons_on pass_rate: `40%` (4/10)
- lessons_off pass_rate: `40%` (4/10)
- pass_rate_delta (on-off): `+0%`
- lessons_on last_5_pass_rate: `60%`
- lessons_off last_5_pass_rate: `20%`
- last_5_pass_rate_delta (on-off): `+40%`
- lessons_on median_steps_to_success: `3.0`
- lessons_off median_steps_to_success: `3.0`
- lessons_on mean_lesson_activations: `2.30`
- lessons_off mean_lesson_activations: `0.00`
- lessons_on mean_retrieval_help_ratio: `0.90`
- lessons_off mean_retrieval_help_ratio: `0.00`

## Per-run Table

| arm | run | session | passed | score | steps | tool_errors | lesson_activations | retrieval_help_ratio | closure_status |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| on | 1 | 148500 | False | 0.889 | 3 | 0 | 0 | 0.00 | pass |
| on | 2 | 148501 | False | 0.944 | 3 | 2 | 1 | 1.00 | pass |
| on | 3 | 148502 | False | 0.889 | 3 | 1 | 2 | 1.00 | pass |
| on | 4 | 148503 | True | 1.000 | 3 | 0 | 2 | 1.00 | pass |
| on | 5 | 148504 | False | 0.944 | 3 | 1 | 4 | 1.00 | pass |
| on | 6 | 148505 | False | 0.944 | 3 | 0 | 2 | 1.00 | pass |
| on | 7 | 148506 | True | 1.000 | 3 | 0 | 2 | 1.00 | pass |
| on | 8 | 148507 | True | 1.000 | 3 | 0 | 2 | 1.00 | pass |
| on | 9 | 148508 | False | 0.389 | 3 | 1 | 4 | 1.00 | fail |
| on | 10 | 148509 | True | 1.000 | 3 | 1 | 4 | 1.00 | pass |
| off | 1 | 148600 | True | 1.000 | 3 | 0 | 0 | 0.00 | fail |
| off | 2 | 148601 | True | 1.000 | 3 | 0 | 0 | 0.00 | fail |
| off | 3 | 148602 | False | 0.944 | 3 | 0 | 0 | 0.00 | pass |
| off | 4 | 148603 | True | 1.000 | 3 | 1 | 0 | 0.00 | pass |
| off | 5 | 148604 | False | 0.889 | 3 | 0 | 0 | 0.00 | pass |
| off | 6 | 148605 | False | 0.944 | 3 | 0 | 0 | 0.00 | pass |
| off | 7 | 148606 | False | 0.556 | 3 | 1 | 0 | 0.00 | pass |
| off | 8 | 148607 | False | 0.778 | 3 | 0 | 0 | 0.00 | pass |
| off | 9 | 148608 | False | 0.944 | 3 | 2 | 0 | 0.00 | pass |
| off | 10 | 148609 | True | 1.000 | 3 | 1 | 0 | 0.00 | pass |

## Failure Taxonomy

| arm | reason_code | gap_type | count |
|---|---|---|---:|
| lessons_on | missing_required_event_pattern | required_event_pattern | 6 |
| lessons_on | missing_required_file_content_pattern | required_file_content_pattern | 6 |
| lessons_on | missing_required_file | required_file | 4 |
| lessons_on | matched_forbidden_event_pattern | forbidden_event_pattern | 2 |
| lessons_off | missing_required_event_pattern | required_event_pattern | 7 |
| lessons_off | missing_required_file_content_pattern | required_file_content_pattern | 6 |
| lessons_off | matched_forbidden_event_pattern | forbidden_event_pattern | 2 |
| lessons_off | missing_required_file | required_file | 2 |

Top unresolved gap signatures (lessons_on):
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_gamma.patch`: 3
- `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_beta.patch`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_alpha.patch`: 1
- `missing_required_file|required_file|target_repo/.git`: 1
- `missing_required_file|required_file|hotfix_gamma.patch`: 1
- `missing_required_file|required_file|target_repo/hotfix_gamma.txt`: 1
- `missing_required_file|required_file|target_repo/transfer_summary.txt`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_gamma.txt::(?is)Retry profile gamma`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_gamma.txt::(?is)Set initial delay to 325ms`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_BRANCH\s+main$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCHES\s+1$`: 1

Top unresolved gap signatures (lessons_off):
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_alpha.patch`: 3
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_gamma.patch`: 2
- `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 2
- `missing_required_file|required_file|target_repo/hotfix_beta.txt`: 1
- `missing_required_file|required_file|target_repo/transfer_summary.txt`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_beta.txt::(?is)Retry profile beta`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_beta.txt::(?is)Set initial delay to 300ms`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_BRANCH\s+main$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCHES\s+1$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCH_FILE\s+hotfix_beta.patch$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_VARIANT\s+beta$`: 1
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+init\s+source_repo`: 1
