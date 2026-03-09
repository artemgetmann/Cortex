# Hotfix Hard A/B Sprint (2026-03-09)

Status: active
Owner: Cortex CLI SQLite
Goal: verify whether memory ON gives real lift on `shell_git_transfer_hotfix_hard` after structured-lesson consistency fix.

## Scope lock

1. Task: `shell_git_transfer_hotfix_hard`
2. Backend/model: `openai` + `gpt-5-nano`
3. Determinism: ON
4. Step cap: `4`
5. Retry policy: `--no-contract-gap-retry`
6. Structured lessons: required for ON arm
7. OFF arm writes no lessons

## Current known state

1. OFF baseline (pre-latest consistency patch): `0/10` pass with strict cap 4
2. ON (pre-latest consistency patch): `2/10` pass
3. Root bug found: some structured lessons had mismatched action vs gap and were still being injected.
4. Patch landed:
   - commit: `b2c7bb5`
   - effect: reject unanchored structured action templates for event-pattern gaps.

## Execution checklist

1. `DONE` Run fresh OFF arm after patch (10 runs).
2. `DONE` Run fresh ON arm after patch (10 runs, structured required).
3. `DONE` Compare:
   - pass rate
   - mean score
   - mean errors
   - lesson activations
   - retrieval help ratio
4. `DONE` Decide go/no-go:
   - go = ON pass rate materially above OFF with non-harmful activations
   - no-go = activations rise but errors also rise / no pass lift

## Canonical commands

OFF arm:

```bash
cd /Users/user/Programming_Projects/Cortex
: > tracks/cli_sqlite/learning/lessons_v2.jsonl
PYTHONUNBUFFERED=1 OPENAI_TIMEOUT_S=120 \
python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --domain shell \
  --task-id shell_git_transfer_hotfix_hard \
  --sessions 10 \
  --start-session 1760 \
  --max-steps 4 \
  --llm-backend openai \
  --learning-mode strict \
  --benchmark-deterministic \
  --no-contract-gap-retry \
  --no-posttask-learn \
  --verbose | tee tracks/cli_sqlite/reports/curve_off_shell_hotfixhard_s10_step4_noretry_consistencyfix.log
```

ON arm:

```bash
cd /Users/user/Programming_Projects/Cortex
: > tracks/cli_sqlite/learning/lessons_v2.jsonl
PYTHONUNBUFFERED=1 OPENAI_TIMEOUT_S=120 \
python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
  --domain shell \
  --task-id shell_git_transfer_hotfix_hard \
  --sessions 10 \
  --start-session 1770 \
  --max-steps 4 \
  --llm-backend openai \
  --learning-mode strict \
  --benchmark-deterministic \
  --no-contract-gap-retry \
  --structured-lessons-required \
  --verbose | tee tracks/cli_sqlite/reports/curve_on_shell_hotfixhard_s10_step4_noretry_consistencyfix.log
```

## Output artifacts

1. `tracks/cli_sqlite/reports/curve_off_shell_hotfixhard_s10_step4_noretry_consistencyfix.log`
2. `tracks/cli_sqlite/reports/curve_on_shell_hotfixhard_s10_step4_noretry_consistencyfix.log`
3. Short final summary note in this file with final decision.

## Final summary (this sprint)

Result: `NO-GO` on this lane after consistency-fix rerun.

Fresh OFF (`1760-1769`):
1. pass rate `4/10 = 0.40`
2. mean score `0.765`
3. mean errors `0.70`
4. mean activations `0.00`

Fresh ON (`1770-1779`, structured required):
1. pass rate `2/10 = 0.20`
2. mean score `0.621`
3. mean errors `1.10`
4. mean activations `0.90`
5. mean help ratio `0.40`

Interpretation:
1. Memory mechanism clearly fired (activations rose from `0.00` to `0.90`).
2. But activation quality is still negative on this slice (ON underperformed OFF).
3. The latest semantic consistency patch removed the prior obvious mismatch class (`git init` gap receiving `git am` repair), but structured lessons are still too broad/noisy in some cases and can harm execution under tight step cap.

Next patch target:
1. Add retrieval-time action specificity gate for shell:
   - prefer one focused command per lesson
   - reject multi-command "kitchen sink" action templates
   - require action tokens to include both operation + target anchor from current gap
2. Re-run this exact OFF/ON protocol after that patch.

## Gate 2 update (same day)

Patch:
1. retrieval-time shell specificity filter added in lesson selection
2. over-broad multi-command shell action templates are skipped during same-task structured fallback

Smoke (`1780-1784`, ON only):
1. pass rate `0/5`
2. mean score `0.688`
3. mean errors `1.6`
4. mean activations `1.4`
5. mean help ratio `0.53`

Interpretation:
1. hint shape improved (focused `git am` action, not kitchen-sink bundles)
2. but memory signal is still net harmful in this lane under cap=4
3. likely issue is dependency ordering (lessons suggest later-step fixes before prerequisite setup is complete)

Next patch target after Gate 2:
1. add prerequisite-aware activation for shell lessons
2. example: do not inject `git am ../patch` lesson unless patch artifact exists in current run state

## Gate 3 update (same day)

Patch:
1. on-error lesson selection now suppresses patch-apply (`git am`) hints when current error indicates missing prerequisites (`source_repo`, missing patch/spec files, pathspec/could-not-open class failures)

Smoke (`1800-1804`, ON only):
1. pass rate `3/5`
2. mean score `0.934`
3. mean errors `0.0`
4. mean activations `0.0`
5. mean help ratio `0.0`

Interpretation:
1. harmful activation class was removed in this smoke
2. but memory mechanism did not fire at all (`activations=0`), so this is not learning proof
3. this lane currently behaves like plain execution variance, not memory-driven lift

Decision after Gate 3:
1. keep this suppression (it prevents obvious bad hints)
2. for proof, move to a lane where OFF baseline is hard and structured lessons activate meaningfully
