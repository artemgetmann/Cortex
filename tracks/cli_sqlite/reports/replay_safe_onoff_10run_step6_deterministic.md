# Replay-Safe SQLite 10-Run Slice (Deterministic ON/OFF)

Date: 2026-03-09  
Task: `incremental_reconcile_replay_safe`  
Domain: `sqlite`  
Mode: `--curriculum-mode fixed --learning-mode strict`  
Steps: `6`  
Model: `gpt-5-nano` via `--llm-backend openai`  
Deterministic flags: `--benchmark-deterministic`, `--doc-mode none`, `--doc-retrieval off`,  
`--judge-diagnostic`, `--contract-gap-retry --contract-gap-retry-steps 1`, `--contract-gap-deterministic-recipes`,  
`--structured-lessons-required`, `--benchmark-promoted-only`.

## ON Summary (lessons enabled)

- Log: `/tmp/replay_safe_on_10run_step6.log`
- Sessions: 10 (61001–61010)
- Pass rate: **7/10 = 70%**
- Last-5 pass rate: **3/5 = 60%**
- Median steps on success: **6**
- Mean score: **0.966**
- Mean `lessons_in` (lesson activations): **0.0**
- Mean `lessons_out` (generated lessons): **2.2**
- Mean errors: **0.1**

Pass/fail sequence: `N Y Y Y Y Y Y Y Y N N`

## OFF Summary (lessons disabled)

- Log: `/tmp/replay_safe_off_10run_step6.log`
- Sessions: 10 (62001–62010)
- Pass rate: **8/10 = 80%**
- Last-5 pass rate: **4/5 = 80%**
- Median steps on success: **6**
- Mean score: **0.972**
- Mean `lessons_in`: **0.0**
- Mean `lessons_out`: **0.0**
- Mean errors: **0.2**

Pass/fail sequence: `Y Y Y Y N Y Y Y N Y`

## Interpretation

- ON does **not** beat OFF under this exact configuration.
- Lesson activations are effectively zero (`lessons_in=0`) because `--benchmark-promoted-only` blocks candidate lessons and no prior promoted lessons were available in this fresh slice.
- This run is not a valid proof of memory-lift in the current setup due lack of usable lesson retrieval signal.
- It does confirm that the strict deterministic path is stable and reproducible, but not that it learns over repeated attempts on this task in this configuration.

## Metric Glossary

- **pass_rate**: fraction of sessions with contract pass (`Y`).
- **transfer_pass_rate**: pass fraction for transfer set only (not used in this artifact).
- **mean_X**: arithmetic mean of value `X` across sessions.
- **median_steps_to_success**: median `steps` among sessions where pass=`Y`.
- **repeated_error_delta**: mean error count change trend across sessions (not computed here).
- **median_repeated_error_delta**: median error delta across sessions (not computed here).
- **transfer_pass_delta**: difference in pass rate between transfer and train slices (not computed here).
- **activation_delta**: change in `lessons_in` between ON and OFF.
- **retrieval_help_ratio_delta**: change in retrieval-help ratio between ON and OFF (not available in this output).

## Next Step

If we want a real lesson-effect test, rerun this slice without `--benchmark-promoted-only` so candidate lessons can be applied in ON mode, or pin a known candidate policy that can be activated from earlier lessons.
