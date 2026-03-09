# Shell Hotfix Hard ON/OFF Slice (Step Cap 6, 10 Runs, 2026-03-09)

## Protocol

- Task: `shell_git_transfer_hotfix_hard`
- Backend: `openai`
- Executor/Judge: `gpt-5-nano`
- Runner: `tracks/cli_sqlite/scripts/run_learning_curve.py`
- Common flags:
  - `--benchmark-deterministic`
  - `--structured-lessons-required`
  - `--no-benchmark-promoted-only`
  - `--no-benchmark-placebo`
  - `--no-self-edit-mode`
  - `--doc-mode none --doc-retrieval off`
  - `--executor-docs off --judge-docs off --no-judge-diagnostic`
- ON lane:
  - `CORTEX_RUNTIME_LANE=ab_shell_hotfix_on_20260309_10x`
  - sessions `609300..609309`
  - `posttask_learn=True`
- OFF lane:
  - `CORTEX_RUNTIME_LANE=ab_shell_hotfix_off_20260309_10x`
  - sessions `609400..609409`
  - `--no-posttask-learn`

## Summary

- ON:
  - pass rate: `5/10` (`50%`)
  - mean score: `0.9277`
  - mean errors: `3.7`
  - mean lesson activations: `1.6`
  - mean retrieval help ratio: `0.7`
- OFF:
  - pass rate: `2/10` (`20%`)
  - mean score: `0.7777`
  - mean errors: `5.5`
  - mean lesson activations: `0.0`
  - mean retrieval help ratio: `0.0`

## Readout

- This slice shows a clear ON > OFF signal on reliability (`+30pp` pass rate) and score.
- ON also reduces errors and shows active retrieval mechanism (`activations/help > 0`).
- OFF confirms baseline remains materially weaker under identical step budget and task.
