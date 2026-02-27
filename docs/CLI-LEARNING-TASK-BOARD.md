# CLI Learning Task Board

Status: `reference board` (historical tracking artifact)
Use: task history and rationale only; active execution source is `docs/CLI-SQLITE-V15-PROOF-PLAN.md`.

Last updated: 2026-02-27
Scope: `tracks/cli_sqlite`
North star: prove real learning signal in hard transfer tasks (not prompt luck), while making the runtime maintainable.

## Program-level success criteria
1. `ON` outperforms `OFF` on hard transfer with deterministic settings.
2. Mechanism evidence is non-zero (`generated`, `activated`, `help_ratio`).
3. Result is statistically defensible (not 5-run noise).
4. Runtime architecture is split into safe modules (no monolith-only coupling).

## Ground truth (already done)
1. `1f47725` deterministic-recipe ablation switch exists.
2. `301dd41` strict structured lesson validation hardening landed.
3. `9b7e2de` strict V2 extraction unblocked and parser telemetry improved.

## Board overview

| ID | Task | Status | Priority | Depends on | Owner | Worktree |
|---|---|---|---|---|---|---|
| T0 | Responses-first transport module extraction | TODO | P0 | - | Codex | `wt-transport` |
| T1 | Lesson normalizer before strict schema gate | TODO | P0 | T0 | Codex | `wt-quality` |
| T2 | Evidence anchor normalizer + rejection taxonomy cleanup | TODO | P0 | T1 | Codex | `wt-quality` |
| T3 | Retrieval ranking: usefulness-weighted memory | TODO | P1 | T1 | Codex | `wt-retrieval` |
| T4 | Hard-slice benchmark runner: 25x25 ON/OFF | TODO | P1 | T2 | Codex | `wt-bench` |
| T5 | Stats/report upgrades (Fisher exact + CI + glossary) | TODO | P1 | T4 | Codex | `wt-bench` |
| T6 | Monolith minimum safe split (contract/lesson/posttask) | TODO | P1 | T2 | Codex | `wt-split` |
| T7 | Docs/runbook update + execution invariants | TODO | P2 | T5,T6 | Codex | `wt-docs` |
| T8 | Log retention + git hygiene policy | TODO | P2 | T4 | Codex | `wt-bench` |

## Task cards

### T0 — Responses-first transport module extraction
Status: TODO
Goal: ensure OpenAI path uses Responses API by default and isolate transport complexity.
Files:
`tracks/cli_sqlite/openai_transport.py`
`tracks/cli_sqlite/agent_cli.py`
`tracks/cli_sqlite/tests/test_openai_responses_migration.py`
Implementation:
1. Move `_openai_responses_request`.
2. Move `_openai_chat_completions_request` behind explicit fallback flag.
3. Move `_OpenAICompatMessagesAPI` and `_OpenAICompatClient`.
4. Move OpenAI conversion helpers currently coupled to these calls.
Acceptance:
1. Default path metric shows `responses`.
2. Chat-completions used only when `OPENAI_ALLOW_CHAT_COMPLETIONS_FALLBACK=1`.
3. `python3 -m pytest tracks/cli_sqlite/tests -q` passes.

### T1 — Lesson normalizer before strict schema gate
Status: TODO
Goal: convert near-valid model lessons into valid structured lessons before rejection.
Files:
`tracks/cli_sqlite/lesson_schema.py` (new)
`tracks/cli_sqlite/agent_cli.py`
`tracks/cli_sqlite/tests/test_agent_cli_validation_retry.py`
Implementation:
1. Add `normalize_structured_lesson()` that repairs common shape issues.
2. Keep strict validation after normalization.
3. Add reason-coded counters for normalize attempts/success/fail.
Acceptance:
1. Schema reject totals drop on same hard slice.
2. `v2_lessons_generated + v2_lessons_merged` increases vs pre-normalizer baseline.
3. Test coverage includes malformed-to-valid conversion cases.

### T2 — Evidence anchor normalizer + taxonomy cleanup
Status: TODO
Goal: reduce false rejects on `expected_evidence_unanchored` while keeping quality bar.
Files:
`tracks/cli_sqlite/lesson_schema.py`
`tracks/cli_sqlite/agent_cli.py`
`tracks/cli_sqlite/tests/test_agent_cli_validation_retry.py`
Implementation:
1. Tokenize unresolved gap details into canonical anchor tokens.
2. Accept evidence that references canonical tokens.
3. Keep exact-signature checks as stronger path.
Acceptance:
1. `expected_evidence_unanchored` rejection rate declines on benchmark.
2. No rise in invalid-tool or invalid-shape accepts.
3. Regression tests added for regex-like gap details.

### T3 — Retrieval ranking: usefulness-weighted memory
Status: TODO
Goal: load fewer, better lessons at runtime.
Files:
`tracks/cli_sqlite/learning_cli.py`
`tracks/cli_sqlite/agent_cli.py`
`tracks/cli_sqlite/tests/test_lesson_memory_v2.py`
Implementation:
1. Rank by promoted status, signature match, historical usefulness, then recency.
2. Cap injected lessons per run.
3. Preserve existing scoring/pruning/promotion behavior.
Acceptance:
1. Mean `v2_lesson_activations` increases on ON arm.
2. Mean `v2_retrieval_help_ratio` increases on ON arm.
3. No API/CLI interface break.

### T4 — Hard-slice benchmark runner: 25x25 ON/OFF
Status: TODO
Goal: remove statistical ambiguity from 5-run/10-run noise.
Files:
`tracks/cli_sqlite/scripts/run_learning_curve.py`
`tracks/cli_sqlite/reports/*`
Implementation:
1. Run `shell_git_transfer_hotfix` ON 25 runs, OFF 25 runs.
2. Fixed config:
`--max-steps 6`
`--benchmark-deterministic`
`--benchmark-promoted-only`
`--contract-gap-retry`
`--no-contract-gap-deterministic-recipes`
`--doc-mode lossy`
3. Persist raw session rows and aggregate summary.
Acceptance:
1. Summary artifact generated with all 50 runs.
2. Includes ON/OFF pass rates, late-curve window, mechanism metrics.

### T5 — Stats/report upgrades
Status: TODO
Goal: make claims falsifiable.
Files:
`tracks/cli_sqlite/scripts/run_learning_curve.py`
`tracks/cli_sqlite/reports/*.md`
Implementation:
1. Add Fisher exact test on ON/OFF pass contingency.
2. Add pass-rate delta confidence interval.
3. Embed concise metric glossary in markdown output.
Acceptance:
1. Report includes p-value and CI.
2. “Learning improved” only when pass lift + mechanism evidence hold.

### T6 — Monolith minimum safe split
Status: TODO
Goal: reduce risk and speed up iteration.
Files:
`tracks/cli_sqlite/agent_cli.py`
`tracks/cli_sqlite/contract_gap_retry.py` (new)
`tracks/cli_sqlite/posttask_learning.py` (new)
`tracks/cli_sqlite/lesson_schema.py` (new)
Implementation:
1. Move contract-gap logic out.
2. Move posttask learning pipeline out.
3. Keep `agent_cli.py` as orchestration shell.
Acceptance:
1. No CLI flag behavior changes.
2. All tests pass.
3. Runtime metrics unchanged except intentional additions.

### T7 — Docs/runbook update
Status: TODO
Goal: make execution and interpretation repeatable.
Files:
`tracks/cli_sqlite/README.md`
`docs/MEMORY-V2-BENCHMARKS.md`
`docs/CLI-LEARNING-TASK-BOARD.md`
Implementation:
1. Document canonical hard-slice command presets.
2. Document what counts as valid learning evidence.
3. Document transport default (Responses API first).
Acceptance:
1. A new contributor can run ON/OFF with no ad-hoc decisions.

### T8 — Log retention + git hygiene
Status: TODO
Goal: keep repo readable while preserving useful evidence.
Files:
`.gitignore`
`tracks/cli_sqlite/reports/`
Implementation:
1. Keep summary JSON/MD tracked.
2. Keep bulk per-run `.log` untracked by default.
3. Add naming convention for canonical artifacts.
Acceptance:
1. `git status` remains clean after benchmark execution.

## Parallel execution order
1. Start `wt-transport` (T0) and `wt-quality` (T1/T2) in parallel.
2. After T1/T2 merge, run T4/T5 on fresh baseline.
3. Run T6 split after quality path is stable.
4. Finish with docs/hygiene (T7/T8).

## Daily check-in template
1. What changed (commit IDs)?
2. Which task IDs moved state?
3. What benchmark artifacts were produced?
4. Did mechanism metrics improve?
5. What is blocked and why?

## Done definition (program)
1. 25x25 ON/OFF completed on hard transfer.
2. ON shows statistically significant pass lift over OFF.
3. ON has non-zero lesson generation + activation + help ratio lift.
4. Safe split merged with tests green.
