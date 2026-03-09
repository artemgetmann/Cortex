# Replay-Safe SQLite 10-Run ON/OFF (No-Promoted-Only)

Date: 2026-03-09  
Task: `incremental_reconcile_replay_safe`  
Domain: `sqlite`  
Mode: `--curriculum-mode fixed --learning-mode strict`  
Steps: `6`  
Model: `gpt-5-nano` via `--llm-backend openai`  
Deterministic flags: `--benchmark-deterministic`, `--doc-mode none`, `--doc-retrieval off`,  
`--judge-diagnostic`, `--contract-gap-retry --contract-gap-retry-steps 1`, `--contract-gap-deterministic-recipes`,  
`--structured-lessons-required`, `--no-benchmark-promoted-only`.

This report is based on:
- ON log: `/tmp/replay_safe_on_10run_step6_nopromo.log`
- OFF log: `/tmp/replay_safe_off_10run_step6_nopromo.log`
- ON sessions: `63101–63110`
- OFF sessions: `63201–63210`

## ON Summary (lessons enabled)

- Pass rate: **10/10 = 100%**
- Last-5 pass rate: **5/5 = 100%**
- Median steps on success: **6**
- Mean score: **1.000**
- Mean `lesson_activations`: **2.6**
- Mean `retrieval_help_ratio`: **0.900**
- Mean errors: **0.2**
- Pass/fail sequence: `YYYYYYYYYY`

Run table:

| Run | Session | Pass | Score | Steps | Errors | LessonsIn | LessonsOut | Activations | Help | Time |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 63101 | Y | 1.00 | 6 | 1 | 0 | 3 | 0.00 | 77.7s |
| 2 | 63102 | Y | 1.00 | 6 | 0 | 0 | 3 | 1.00 | 55.3s |
| 3 | 63103 | Y | 1.00 | 6 | 0 | 0 | 2 | 1.00 | 70.1s |
| 4 | 63104 | Y | 1.00 | 6 | 0 | 0 | 3 | 1.00 | 77.1s |
| 5 | 63105 | Y | 1.00 | 6 | 0 | 0 | 3 | 1.00 | 88.5s |
| 6 | 63106 | Y | 1.00 | 6 | 0 | 0 | 3 | 1.00 | 72.3s |
| 7 | 63107 | Y | 1.00 | 6 | 0 | 0 | 3 | 1.00 | 88.4s |
| 8 | 63108 | Y | 1.00 | 6 | 0 | 0 | 3 | 1.00 | 86.4s |
| 9 | 63109 | Y | 1.00 | 6 | 1 | 0 | 6 | 1.00 | 94.4s |
| 10 | 63110 | Y | 1.00 | 6 | 0 | 0 | 1 | 1.00 | 88.1s |

## OFF Summary (lessons disabled)

- Pass rate: **6/10 = 60%**
- Last-5 pass rate: **4/5 = 80%**
- Median steps on success: **6**
- Mean score: **0.862**
- Mean `lesson_activations`: **0.0**
- Mean `retrieval_help_ratio`: **0.00**
- Mean errors: **0.3**
- Pass/fail sequence: `NNNYYYNYY`

Run table:

| Run | Session | Pass | Score | Steps | Errors | LessonsIn | LessonsOut | Activations | Help | Time |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 63201 | N | 0.94 | 6 | 0 | 0 | 0 | 0 | 0.00 | 46.7s |
| 2 | 63202 | N | 0.89 | 6 | 2 | 0 | 0 | 0 | 0.00 | 60.1s |
| 3 | 63203 | N | 0.83 | 6 | 0 | 0 | 0 | 0 | 0.00 | 59.8s |
| 4 | 63204 | Y | 1.00 | 6 | 0 | 0 | 0 | 0 | 0.00 | 69.3s |
| 5 | 63205 | Y | 1.00 | 6 | 0 | 0 | 0 | 0 | 0.00 | 69.0s |
| 6 | 63206 | Y | 1.00 | 6 | 0 | 0 | 0 | 0 | 0.00 | 61.7s |
| 7 | 63207 | Y | 1.00 | 6 | 0 | 0 | 0 | 0 | 0.00 | 67.9s |
| 8 | 63208 | N | 0.33 | 6 | 0 | 0 | 0 | 0 | 0.00 | 79.9s |
| 9 | 63209 | Y | 1.00 | 6 | 1 | 0 | 0 | 0 | 0.00 | 55.5s |
| 10 | 63210 | Y | 1.00 | 6 | 0 | 0 | 0 | 0 | 0.00 | 75.9s |

## Comparison (ON - OFF)

- Pass rate delta: **+40%** (1.00 vs 0.60)
- Last-5 pass rate delta: **+20%** (1.00 vs 0.80)
- Median steps to success delta: **0**
- Mean `lesson_activations` delta: **+2.6**
- Mean `retrieval_help_ratio` delta: **+0.900**
- Mean error count delta: **-0.1**

## Interpretation

This run shows a strong lift in strict pass rate and explicit lesson-use signal on the same task:
ON is 100% vs OFF 60%.  
The delta comes with non-zero `lesson_activations` and `retrieval_help_ratio` on ON only, while OFF remains zero.

## Recommendation

Use this as a valid ON/OFF checkpoint that memory helped under this strict configuration.  
Next, keep this protocol and add a transfer-family hard slice to test cross-task generalization.
