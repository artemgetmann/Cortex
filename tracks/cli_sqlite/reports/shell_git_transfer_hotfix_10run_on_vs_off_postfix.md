# Shell Git Transfer Hotfix 10-Run ON vs OFF (strict, docs on/lossy)

## Summary

- lessons_on pass_rate: `90%` (9/10)
- lessons_off pass_rate: `70%` (7/10)
- pass_rate_delta (on-off): `+20%`
- lessons_on last_5_pass_rate: `100%`
- lessons_off last_5_pass_rate: `80%`
- last_5_pass_rate_delta (on-off): `+20%`
- lessons_on mean_lesson_activations: `0.40`
- lessons_off mean_lesson_activations: `0.00`
- lessons_on mean_retrieval_help_ratio: `0.30`
- lessons_off mean_retrieval_help_ratio: `0.00`

## Failure Taxonomy

| arm | reason_code | count |
|---|---|---:|
| lessons_on | missing_required_event_pattern | 1 |
| lessons_off | missing_required_file_content_pattern | 4 |
| lessons_off | missing_required_file | 3 |
| lessons_off | missing_required_event_pattern | 2 |

Top unresolved gap signatures (lessons_on):
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix\.patch`: 1

Top unresolved gap signatures (lessons_off):
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix\.patch`: 2
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix.txt::(?is)Increase\s+initial\s+delay\s+to\s+250ms\.`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix.txt::(?is)Retry\s+backoff\s+tune:`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_BRANCH\s+main$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCHES\s+1$`: 1
- `missing_required_file|required_file|target_repo/.git`: 1
- `missing_required_file|required_file|target_repo/hotfix.txt`: 1
- `missing_required_file|required_file|target_repo/transfer_summary.txt`: 1
