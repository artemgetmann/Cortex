# Shell Git Transfer Hotfix Hard 10-Run ON vs OFF (steps=3)

## Summary

- lessons_on pass_rate: `60%` (6/10)
- lessons_off pass_rate: `30%` (3/10)
- pass_rate_delta (on-off): `+30%`
- lessons_on last_5_pass_rate: `80%`
- lessons_off last_5_pass_rate: `20%`
- last_5_pass_rate_delta (on-off): `+60%`
- lessons_on median_steps_to_success: `3.0`
- lessons_off median_steps_to_success: `3.0`
- lessons_on mean_lesson_activations: `2.70`
- lessons_off mean_lesson_activations: `0.00`
- lessons_on mean_retrieval_help_ratio: `0.90`
- lessons_off mean_retrieval_help_ratio: `0.00`

## Per-run Table

| arm | run | session | passed | score | steps | lesson_activations | retrieval_help_ratio |
|---|---:|---:|---|---:|---:|---:|---:|
| on | 1 | 148200 | False | 0.944 | 3 | 0 | 0.00 |
| on | 2 | 148201 | False | 0.889 | 3 | 1 | 1.00 |
| on | 3 | 148202 | True | 1.000 | 3 | 4 | 1.00 |
| on | 4 | 148203 | True | 1.000 | 3 | 4 | 1.00 |
| on | 5 | 148204 | False | 0.889 | 3 | 2 | 1.00 |
| on | 6 | 148205 | True | 1.000 | 3 | 4 | 1.00 |
| on | 7 | 148206 | True | 1.000 | 3 | 4 | 1.00 |
| on | 8 | 148207 | False | 0.500 | 3 | 2 | 1.00 |
| on | 9 | 148208 | True | 1.000 | 3 | 4 | 1.00 |
| on | 10 | 148209 | True | 1.000 | 3 | 2 | 1.00 |
| off | 1 | 148300 | False | 0.944 | 3 | 0 | 0.00 |
| off | 2 | 148301 | True | 1.000 | 3 | 0 | 0.00 |
| off | 3 | 148302 | False | 0.889 | 3 | 0 | 0.00 |
| off | 4 | 148303 | False | 0.944 | 3 | 0 | 0.00 |
| off | 5 | 148304 | True | 1.000 | 3 | 0 | 0.00 |
| off | 6 | 148305 | True | 1.000 | 3 | 0 | 0.00 |
| off | 7 | 148306 | False | 0.778 | 3 | 0 | 0.00 |
| off | 8 | 148307 | False | 0.778 | 3 | 0 | 0.00 |
| off | 9 | 148308 | False | 0.889 | 3 | 0 | 0.00 |
| off | 10 | 148309 | False | 0.889 | 3 | 0 | 0.00 |

## Failure Taxonomy

| arm | reason_code | gap_type | count |
|---|---|---|---:|
| lessons_on | missing_required_file_content_pattern | required_file_content_pattern | 6 |
| lessons_on | missing_required_event_pattern | required_event_pattern | 4 |
| lessons_on | matched_forbidden_event_pattern | forbidden_event_pattern | 2 |
| lessons_on | missing_required_file | required_file | 2 |
| lessons_off | missing_required_event_pattern | required_event_pattern | 11 |
| lessons_off | matched_forbidden_event_pattern | forbidden_event_pattern | 5 |

Top unresolved gap signatures (lessons_on):
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_beta.patch`: 3
- `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_alpha.patch`: 1
- `missing_required_file|required_file|target_repo/hotfix_beta.txt`: 1
- `missing_required_file|required_file|target_repo/transfer_summary.txt`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_beta.txt::(?is)Retry profile beta`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/hotfix_beta.txt::(?is)Set initial delay to 300ms`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_BRANCH\s+main$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCHES\s+1$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_PATCH_FILE\s+hotfix_beta.patch$`: 1
- `missing_required_file_content_pattern|required_file_content_pattern|target_repo/transfer_summary.txt::(?m)^TRANSFER_VARIANT\s+beta$`: 1

Top unresolved gap signatures (lessons_off):
- `matched_forbidden_event_pattern|forbidden_event_pattern|(?is)\b/tmp\b`: 5
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_beta.patch`: 4
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_alpha.patch`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+init\s+source_repo`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+init\s+target_repo`: 2
- `missing_required_event_pattern|required_event_pattern|(?is)git\s+am\s+\.\./hotfix_gamma.patch`: 1
