# shell_excel_openpyxl_summary (10-run on/off, max_steps=1)

## Summary

- Off: pass_rate=0.0 mean_eval_score=0.0 probe_status={'not_run': 5}
- On: pass_rate=0.0 mean_eval_score=0.0 probe_status={'fail': 5}
- Delta: pass_rate=0.0 mean_eval_score=0.0

## Key Observation

- With verifier stack on, low-confidence fired on all 5 runs and probes resolved to hard `fail` (not `inconclusive`).
- Deterministic failure reasons were appended (e.g., `deterministic_probe_failed:missing_required_file`).
