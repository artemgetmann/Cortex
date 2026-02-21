# CLI Memory V2 Benchmark Report (SQLite Focus)

Date: 2026-02-21
Scope: CLI Memory V2 only (no FL/VM), `claude_print` backend, Haiku executor/judge, strict learning mode.

## Setup

- Ablation matrix: docs on/off, lossy/full docs, lessons on/off.
- Suite: `sqlite` (train=`import_aggregate`, transfer=`incremental_reconcile`).
- Transport: `claude_print` with `CORTEX_CLAUDE_PRINT_EFFORT=low`.
- Runtime controls: `--auto-escalate-critic off`, `--model-judge claude-haiku-4-5`.

Artifacts:
- `/Users/user/Programming_Projects/Cortex/tracks/cli_sqlite/reports/realworld_ablation_sqlite_2run.json`
- `/Users/user/Programming_Projects/Cortex/tracks/cli_sqlite/reports/realworld_ablation_sqlite_2run.md`
- `/Users/user/Programming_Projects/Cortex/tracks/cli_sqlite/reports/realworld_curve_sqlite_5run_docs_lossy_lessons_on.json`
- `/Users/user/Programming_Projects/Cortex/tracks/cli_sqlite/reports/realworld_curve_sqlite_5run_docs_lossy_lessons_on.md`

## Ablation Snapshot (2 runs per arm)

| arm_id | docs | mode | lessons | pass_rate | transfer_pass_rate | median_steps |
|---|---|---|---|---:|---:|---:|
| docs_off__mode_lossy__lessons_off | off | none (effective) | off | 100% | 100% | 4.0 |
| docs_off__mode_lossy__lessons_on | off | none (effective) | on | 100% | 100% | 4.0 |
| docs_on__mode_lossy__lessons_on | on | lossy | on | 100% | 100% | 4.0 |
| docs_on__mode_full__lessons_on | on | full | on | 100% | 100% | 4.5 |

Interpretation:
- This slice is saturated (all arms pass), so it verifies plumbing but does not separate learning quality.

## 5-Run Learning Curve (docs_on + lossy + lessons_on)

| run | phase | task | result | steps | tool_errors | lessons_loaded | lesson_activations | retrieval_help_ratio |
|---:|---|---|---|---:|---:|---:|---:|---:|
| 1 | train | import_aggregate | PASS | 3 | 1 | 0 | 0 | 0.0 |
| 2 | transfer | incremental_reconcile | FAIL | 4 | 1 | 0 | 0 | 0.0 |
| 3 | train | import_aggregate | PASS | 3 | 0 | 4 | 0 | 0.0 |
| 4 | transfer | incremental_reconcile | PASS | 5 | 1 | 6 | 2 | 1.0 |
| 5 | train | import_aggregate | PASS | 4 | 0 | 6 | 0 | 0.0 |

Key signals:
- Transfer recovery happened: transfer failed on run 2, then passed on run 4.
- Persistent memory engaged: `lessons_loaded` increased from `0` to `6`.
- At least one run shows useful retrieval activation: run 4 had `lesson_activations=2` and `retrieval_help_ratio=1.0`.

Limits in this sample:
- `did_learning_improve` flag remains `false` because the metric compares first vs last session success and run 1 + run 5 are both pass.
- `median_repeated_error_delta` remained `0.0`; repeated-error recurrence is currently not the differentiator in this dataset.

## Conclusion

Did learning improve? **Partially, yes**.

- Strong evidence:
  - Transfer task recovered from fail to pass with higher lesson load.
  - Lesson retrieval/activation became non-zero and helpful in a later run.
- Missing evidence:
  - No broad ablation separation yet (easy benchmark slice is saturated).
  - Repeated-error delta did not move.

Next benchmark move:
- Increase pressure on transfer tasks (harder constraints or tighter step cap) while keeping same executor prompt and model.
- Run 10-session curves for two domains (`sqlite` + `shell git`) using this same report format to validate stability of gains.
