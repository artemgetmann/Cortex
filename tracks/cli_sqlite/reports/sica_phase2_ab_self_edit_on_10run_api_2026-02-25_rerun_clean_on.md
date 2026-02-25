# Real-World CLI Learning Benchmark

## Metric Glossary

- `pass_rate`: fraction of runs that passed deterministic contract checks. High = reliable execution; low = unstable execution.
- `transfer_pass_rate`: pass rate on transfer-phase runs only (unseen/harder tasks). High = better generalization; low = overfitting to train tasks.
- `mean_X`: arithmetic average of metric X across selected runs. High/low depends on metric semantics, but it smooths run-to-run noise.
- `median_X`: middle value of metric X across selected runs. High/low depends on metric semantics; more robust than mean against outliers.
- `median_steps_to_success`: median step count among successful runs only. Low = faster convergence; high = slower/less efficient.
- `repeated_error_delta`: `fingerprint_recurrence_after - fingerprint_recurrence_before` within a run. Negative = fewer repeated mistakes; positive = more repeated mistakes.
- `median_repeated_error_delta`: median of `repeated_error_delta` across runs. Negative is good; positive is bad.
- `transfer_pass_delta`: `last_transfer_pass - first_transfer_pass` over run index. Positive = transfer pass trend improved.
- `activation_delta`: `last_transfer_lesson_activations - first_transfer_lesson_activations`. Positive = lesson mechanism engaged more over time.
- `retrieval_help_ratio_delta`: `last_transfer_retrieval_help_ratio - first_transfer_retrieval_help_ratio`. Positive = retrieved lessons helped more over time.

## How To Read This Report

- Primary signal: `transfer_pass_rate` and `transfer_pass_delta`.
- Mechanism signal: `activation_delta` and `retrieval_help_ratio_delta` should be positive, not just pass/fail changes.
- Error hygiene signal: `median_repeated_error_delta` should move negative over stronger runs.
- Gate: claim learning only when transfer improves and mechanism signals are non-zero/positive.

## Conclusion

- did_learning_improve: `False`
- learning_gate: `transfer_pass_lift=False, activation_nonzero=True, activation_trend=True, retrieval_help_ratio_lift=True`
- transfer_pass_delta: `0.0000`
- activation_delta: `1.0000`
- retrieval_help_ratio_delta: `1.0000`
- success_rate_by_session: `{"1": 1.0, "10": 1.0, "2": 1.0, "3": 1.0, "4": 1.0, "5": 1.0, "6": 1.0, "7": 1.0, "8": 1.0, "9": 1.0}`
- median_steps_to_success: `4.500`
- median_repeated_error_delta: `0.000`
- mean_lesson_activations: `0.300`
- mean_retrieval_help_ratio: `0.200`
- mean_lesson_activations_by_step: `{"2": 0.3}`
- activation_nonzero_run_count: `2`

## Transfer (Unseen Tasks)

- overall_transfer_pass_rate: `100.00%`
- overall_transfer_median_steps_to_success: `6.000`
- overall_transfer_median_repeated_error_delta: `0.000`
- overall_transfer_mean_lesson_activations: `0.600`
- overall_transfer_mean_retrieval_help_ratio: `0.400`
- overall_transfer_mean_lesson_activations_by_step: `{"2": 0.6}`

## Arm Results

| arm_id | docs | doc_mode | lessons | pass_rate | median_steps_to_success | median_repeated_error_delta | mean_lesson_activations | retrieval_help_ratio_delta | transfer_pass_rate |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| docs_off__mode_lossy__lessons_on | off | lossy | on | 100.00% | 4.500 | 0.000 | 0.300 | 1.0000 | 100.00% |

## Artifact Notes

- `contract_gap_postretry.json`: deterministic final gap check after retry; unresolved rows are the exact blockers that still failed contract.
- `target_repo/hotfix.txt` (git transfer tasks): verifies patch content actually landed in target repo.
- `target_repo/transfer_summary.txt` (git transfer tasks): verifies expected transfer metadata (`TRANSFER_BRANCH`, `TRANSFER_PATCHES`) was produced.
