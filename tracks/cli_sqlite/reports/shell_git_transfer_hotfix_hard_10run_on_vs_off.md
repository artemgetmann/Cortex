# Shell Git Transfer Hotfix Hard 10-Run ON vs OFF (strict, docs on/lossy)

## Summary

- lessons_on pass_rate: `40%` (4/10)
- lessons_off pass_rate: `0%` (0/10)
- pass_rate_delta (on-off): `+40%`
- lessons_on last_5_pass_rate: `60%`
- lessons_off last_5_pass_rate: `0%`
- last_5_pass_rate_delta (on-off): `+60%`
- lessons_on mean_lesson_activations: `2.60`
- lessons_off mean_lesson_activations: `0.00`
- lessons_on mean_retrieval_help_ratio: `0.90`
- lessons_off mean_retrieval_help_ratio: `0.00`

## Failure Taxonomy

| arm | reason_code | count |
|---|---|---:|
| lessons_on | missing_required_event_pattern | 18 |
| lessons_off | missing_required_event_pattern | 20 |
| lessons_off | missing_required_file_content_pattern | 6 |
| lessons_off | matched_forbidden_event_pattern | 4 |
| lessons_off | missing_required_file | 3 |

Top unresolved gap signatures (lessons_on):
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+checkout\s+-B\s+main`: 6
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+format-patch\s+-1\s+HEAD\s+--stdout`: 6
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_alpha.patch`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_beta.patch`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_gamma.patch`: 2

Top unresolved gap signatures (lessons_off):
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+format-patch\s+-1\s+HEAD\s+--stdout`: 7
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+checkout\s+-B\s+main`: 5
- `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 4
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_alpha.patch`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_beta.patch`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_gamma.patch`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+init\s+source_repo`: 1
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+init\s+target_repo`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_gamma.txt::(?is)Retry profile gamma`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_gamma.txt::(?is)Set initial delay to 325ms`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_BRANCH\s+main$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCHES\s+1$`: 1
