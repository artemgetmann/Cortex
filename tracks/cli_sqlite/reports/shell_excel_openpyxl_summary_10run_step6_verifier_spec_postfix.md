# shell_excel_openpyxl_summary (10-run on/off, max_steps=6, post-fix)

## Summary

- Off: pass_rate=0.4 mean_eval_score=0.7 probe_status={'not_run': 5}
- On: pass_rate=1.0 mean_eval_score=0.88 probe_status={'pass': 3, 'not_run': 2}
- Delta: pass_rate=0.6 mean_eval_score=0.18

## Observation

- Probe-pass now upgrades no-contract outcomes to eval_passed=true.
- In this slice, 3 low-confidence runs were upgraded via deterministic probes.
