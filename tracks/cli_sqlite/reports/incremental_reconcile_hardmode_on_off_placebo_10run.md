# Incremental Reconcile Hard-Mode ON/OFF/Placebo (10-run)

## Setup

- task: `incremental_reconcile` (sqlite)
- mode: `bootstrap + cryptic-errors`, docs OFF, deterministic ON, promoted-only ON
- goal: test whether lessons improve performance vs OFF and placebo control

## Metric Glossary

- `pass_rate`: percent of runs that passed the contract. Higher is better.
- `last5_pass_rate`: pass rate on runs 6-10. Higher means better late-curve reliability.
- `median_steps_success`: typical steps among successful runs. Lower means faster success.
- `lesson_activations_effective`: non-placebo lesson injections actually used in-run. Higher means learning mechanism engaged.
- `retrieval_help_ratio_effective`: share of effective activations that reduced repeat failures. Higher means retrieved lessons helped.

## Results

| Arm | Pass Rate | Last5 Pass | Series | Median Steps (success) | Mean Activations (effective) | Mean Retrieval Help |
|---|---:|---:|---|---:|---:|---:|
| Lessons ON | 50.0% | 80.0% | `NNNYNNYYYY` | 4.0 | 0.00 | 0.00 |
| Lessons OFF | 100.0% | 100.0% | `YYYYYYYYYY` | 4.0 | 0.00 | 0.00 |
| Placebo Control | 30.0% | 0.0% | `YYYNNNNNNN` | 4.0 | 0.00 | 0.00 |

## Decision (Strict Gate)

- strict_success: `False`
- last5_pass_rate_at_least_80pct: `True`
- on_beats_off: `False`
- on_beats_placebo: `True`
- nonzero_activation: `False`
- nonzero_retrieval_help: `False`

## Interpretation

- Learning mechanism did not activate (`effective activations=0`, `retrieval_help=0`) in all arms.
- In this hard mode slice, lessons ON did not beat OFF; OFF performed better.
- Placebo also underperformed OFF, which indicates current lesson stream can be noisy/fragile in this regime.
- Conclusion: this run is **not** proof of robust learning lift; it is evidence of unresolved learning-path quality issues.
