# shell_excel_openpyxl_summary (10-run on/off, max_steps=6)

## Summary

- Off: pass_rate=0.6 mean_eval_score=0.85 probe_status={'not_run': 5}
- On: pass_rate=0.4 mean_eval_score=0.88 probe_status={'not_run': 2, 'pass': 3}
- Delta: pass_rate=-0.2 mean_eval_score=0.03

## Observation

- Verifier stack engaged only on low-confidence runs (3/5 in on-arm).
- In those runs probes resolved to `pass` (not inconclusive), so deterministic anchors were detected.
- Current runtime policy raises score on probe-pass but does not flip `eval_passed` to true when judge says fail.
