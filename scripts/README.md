# Scripts Index

This folder contains both canonical runtime entrypoints and one-off diagnostics.

## Canonical Entry Points

- `run_agent.py`: primary FL Studio runtime entrypoint.
- `run_fl_benchmark.py`: repeated FL session benchmark runner.
- `run_fl_live_demo.sh`: convenience wrapper for a single FL demo run.
- `score_session.py`: evaluate one FL run from artifacts.
- `render_fl_timeline.py`: timeline-style render for FL run artifacts.
- `validate_skills.py`: skill manifest/format validation.

## VM Control

- `vm/prl_start.sh`
- `vm/prl_status.sh`
- `vm/prl_stop.sh`
- `vm/prl_terminal_run.sh`
- `vm/prl_install_fl.sh`

Use these for Parallels-based isolated runs.

## Diagnostic Scripts (Debug-Only)

These are useful while debugging input/focus/permissions but are not part of normal workflows:

- `diag_*`
- `gate_*`
- `click_test.py`
- `screenshot_fullscreen.py`
- `opus_thinking_test.py`

Keep new diagnostics here only if they are reusable. If a script becomes part of regular workflow, promote it to a canonical entrypoint and document it in root `README.md`.

