# Shell Transfer Strict 10-Run Compare (Post-Patch)

Task: `shell_git_transfer_hotfix`

## Headline
- lessons_on: pass_rate=100.0% (10/10), last5=100.0%, median_steps_to_success=4.0
- lessons_off: pass_rate=70.0% (7/10), last5=60.0%, median_steps_to_success=4
- delta(pass_rate): +30.0 pp

## Mechanism Signal
- lessons_on: mean_lesson_activations=1.30, mean_retrieval_help_ratio=0.40, activation_delta=+0.00, retrieval_help_ratio_delta=+0.00
- lessons_off: mean_lesson_activations=0.00, mean_retrieval_help_ratio=0.00, activation_delta=+0.00, retrieval_help_ratio_delta=+0.00

## Gap Taxonomy (failures)
### lessons_on
- reason counts: `{}`
- gap type counts: `{}`
- top signatures: `[]`

### lessons_off
- reason counts: `{"missing_required_event_pattern": 3}`
- gap type counts: `{"required_event_pattern": 3}`
- top signatures: `[{"gap_signature": "missing_required_event_pattern|required_event_pattern|(?is)git\\s+am\\s+\\.\\./hotfix\\.patch", "count": 3}]`

## Per-run
| arm | session | pass | score | steps | tool_errors | activations | help_ratio |
| --- | ---: | :---: | ---: | ---: | ---: | ---: | ---: |
| lessons_on | 143000 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_on | 143001 | Y | 1.000 | 4 | 0 | 1 | 1.00 |
| lessons_on | 143002 | Y | 1.000 | 4 | 1 | 4 | 1.00 |
| lessons_on | 143003 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_on | 143004 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_on | 143005 | Y | 1.000 | 3 | 0 | 0 | 0.00 |
| lessons_on | 143006 | Y | 1.000 | 4 | 1 | 4 | 1.00 |
| lessons_on | 143007 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_on | 143008 | Y | 1.000 | 4 | 1 | 4 | 1.00 |
| lessons_on | 143009 | Y | 1.000 | 3 | 0 | 0 | 0.00 |
| lessons_off | 143100 | Y | 1.000 | 4 | 1 | 0 | 0.00 |
| lessons_off | 143101 | Y | 1.000 | 4 | 2 | 0 | 0.00 |
| lessons_off | 143102 | Y | 1.000 | 4 | 1 | 0 | 0.00 |
| lessons_off | 143103 | N | 0.941 | 4 | 3 | 0 | 0.00 |
| lessons_off | 143104 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_off | 143105 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_off | 143106 | Y | 1.000 | 4 | 0 | 0 | 0.00 |
| lessons_off | 143107 | N | 0.941 | 4 | 3 | 0 | 0.00 |
| lessons_off | 143108 | N | 0.941 | 4 | 3 | 0 | 0.00 |
| lessons_off | 143109 | Y | 1.000 | 4 | 3 | 0 | 0.00 |
