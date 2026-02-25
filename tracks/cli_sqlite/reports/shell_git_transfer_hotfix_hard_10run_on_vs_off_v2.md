# Shell Git Transfer Hotfix Hard 10-Run ON vs OFF (strict, docs on/lossy, v2 contract)

## Summary

- lessons_on pass_rate: `50%` (5/10)
- lessons_off pass_rate: `30%` (3/10)
- pass_rate_delta (on-off): `+20%`
- lessons_on last_5_pass_rate: `60%`
- lessons_off last_5_pass_rate: `40%`
- last_5_pass_rate_delta (on-off): `+20%`
- lessons_on mean_lesson_activations: `0.60`
- lessons_off mean_lesson_activations: `0.00`
- lessons_on mean_retrieval_help_ratio: `0.40`
- lessons_off mean_retrieval_help_ratio: `0.00`

## Failure Taxonomy

| arm | reason_code | count |
|---|---|---:|
| lessons_on | missing_required_file_content_pattern | 12 |
| lessons_on | missing_required_file | 4 |
| lessons_on | missing_required_event_pattern | 3 |
| lessons_on | matched_forbidden_event_pattern | 2 |
| lessons_off | matched_forbidden_event_pattern | 5 |
| lessons_off | missing_required_event_pattern | 3 |

Top unresolved gap signatures (lessons_on):
- `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_alpha.patch`: 2
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_BRANCH\s+main$`: 2
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCHES\s+1$`: 2
- `missing_required_file|required_file|target_repo/transfer_summary.txt`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_gamma.patch`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_alpha.txt::(?is)Retry profile alpha`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_alpha.txt::(?is)Set initial delay to 275ms`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_beta.txt::(?is)Retry profile beta`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_beta.txt::(?is)Set initial delay to 300ms`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCH_FILE\s+hotfix_alpha.patch$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCH_FILE\s+hotfix_beta.patch$`: 1

Top unresolved gap signatures (lessons_off):
- `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 5
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_gamma.patch`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_beta.patch`: 1
