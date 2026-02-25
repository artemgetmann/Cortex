# SICA Phase 2 API A/B Rerun Delta Report (Clean Arms)

Date: 2026-02-25

Setup:
- Script: `tracks/cli_sqlite/scripts/run_realworld_learning_benchmark.py`
- Sessions per arm: `10`
- Suite/arm: `sqlite` + `docs_off__mode_lossy__lessons_on`
- Backend: `anthropic` (API)
- Learning mode: `strict`
- Posttask mode: `direct`
- Max steps: `6`
- Controlled variable: `--self-edit-mode` OFF vs ON
- Arm isolation: ON arm rerun from clean baseline to avoid posttask skill-patch contamination from OFF arm.

Results:
- OFF overall pass rate: `80.00%`
- ON overall pass rate: `100.00%`
- Delta overall pass rate: `+20.0 pp`
- OFF transfer pass rate: `60.00%`
- ON transfer pass rate: `100.00%`
- Delta transfer pass rate: `+40.0 pp`
- OFF median steps to success: `4.0`
- ON median steps to success: `4.5`
- OFF mean lesson activations: `0.700`
- ON mean lesson activations: `0.300`
- OFF mean retrieval help ratio: `0.150`
- ON mean retrieval help ratio: `0.200`

Interpretation:
- On this clean rerun, enabling the guarded self-edit path improved both overall reliability and transfer reliability.
- `did_learning_improve` remains `False` in both arms because benchmark gate logic requires trend/lift criteria beyond single-point pass-rate lift.

Artifacts:
- `sica_phase2_ab_self_edit_off_10run_api_2026-02-25_rerun.json/.md`
- `sica_phase2_ab_self_edit_on_10run_api_2026-02-25_rerun_clean_on.json/.md`
