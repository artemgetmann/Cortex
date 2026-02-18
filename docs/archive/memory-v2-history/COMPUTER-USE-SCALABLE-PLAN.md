# Computer Use Scalable Plan

Last updated: 2026-02-16
Owner: Cortex FL + Memory V2 track
Status: In progress

## Execution Status (2026-02-16, sprint window)

Completed in code:

- Added separate visual judge module for FL end-of-run screenshot adjudication.
- Wired hybrid authority in runtime: deterministic contract + visual judge + disagreement -> `uncertain`.
- Added explicit judge metrics fields (`judge_model`, `judge_score`, `judge_confidence`, `judge_reasons`, `eval_final_verdict`).
- Added visual judge event emission in session trace (`tool=visual_judge`).
- Kept `extract_fl_state` advisory (planning helper), not final authority.

Pending in code:

- Full timeline renderer support added via `scripts/render_fl_timeline.py` (prints deterministic/judge/final verdict line).
- Full FL 10-step benchmark rerun on machine with Quartz permissions and final demo artifact export.

## Goal

Build a computer-use architecture that is:

- reliable on FL Studio 4-on-the-floor within tight step budgets,
- generalizable to other software classes (browser, design tools, office apps),
- memory-improving across sessions without brittle task scripts.

## Problem Statement

Recent run evidence showed a false positive:

- The model-reported `extract_fl_state` output claimed `active_match=true`,
- but final screenshot inspection showed mismatched activated steps.

Conclusion:

- LLM vision extraction is useful for planning,
- but cannot be pass/fail authority by itself.
- FL loop needs a separate judge path (like `tracks/cli_sqlite`) for end-of-run authority.

## Non-Negotiables

1. Keep true computer-use loop (screenshots + actions + docs-guided reasoning).
2. Do not hardcode per-task action scripts as the long-term solution.
3. Keep memory useful but suppress low-utility or noisy lessons.
4. Separate execution policy from referee authority.
5. Preserve cross-software scalability by using shared primitives + contracts.

## Target Architecture (Scalable)

### 1) Perception Layer (Generic primitives)

Produce structured UI state from screenshots with confidence:

- text/OCR anchors,
- row/list/grid geometry,
- toggle/active state candidates,
- confidence per extracted field.

Output is machine-readable state, not free-form prose.

### 2) Policy Layer (Executor)

Model plans actions from:

- task,
- docs/skills,
- latest structured state,
- memory hints.

Guardrails:

- avoid inspection loops,
- retry invalid/non-productive strategy without burning full budget,
- force decisive action after repeated ambiguity.

### 3) Referee Layer (Authority)

Hybrid verdict:

- deterministic contract checks where objective signals exist,
- separate LLM visual judge for fuzzy visual checks,
- disagreement policy: mark uncertain/fail for promotion purposes.

### 4) Memory Layer

Store outcome-linked lessons from verified signals:

- include state/action/outcome deltas,
- rank retrieval by context match + utility history,
- suppress stale/noisy lessons (permission-era noise, repeatedly unhelpful items).

## FL Studio Phase-1 (Immediate)

### A) Keep `extract_fl_state` as planning tool only

- Use it to guide targeting and disambiguate UI.
- Do not treat it as final proof of task success.

### B) Add deterministic visual verification for kick pattern

Contract-driven check for this task:

- row matched to kick-like label,
- required active step indices = 1, 5, 9, 13,
- no critical forbidden mismatches.

This is a contract implementation, not a one-off action script.

### C) Restore separate visual judge in FL loop

Add a dedicated end-of-run visual judge (independent of executor policy and independent of `extract_fl_state`).

Judge input must include:

- final run screenshot,
- user-provided reference screenshot(s),
- explicit rubric for success/failure.

### D) Referee disagreement handling

If deterministic verifier and visual judge disagree:

- set verdict to uncertain/fail for promotion,
- emit disagreement reason,
- generate corrective lesson candidate.

### E) Retrieval hygiene

- prioritize lessons with positive utility,
- downrank/suppress stale permission-noise lessons,
- keep dedup/conflict checks active.

## Cross-Software Scalability Plan

Use the same pattern per software family:

1. Add/extend UI primitives (panels, rows, grids, toggles, text fields).
2. Define declarative contracts for outcomes (JSON).
3. Reuse same executor loop + referee/memory pipeline.

This avoids 500-line task scripts while acknowledging that each software still needs adapter/contract coverage.

## Demo Narrative (Hackathon)

Show this sequence visibly:

1. Agent reads task + docs.
2. Agent acts and fails.
3. Memory + state extraction influences next actions.
4. Referee verifies from objective checks + visual evidence.
5. Later run improves with fewer wasted steps.

## Acceptance Criteria

1. No false-positive pass when screenshot state is wrong.
2. 10-step FL run shows reduced inspect-loop waste (governor evidence in trace).
3. At least one run reaches correct pattern with deterministic + visual judge agreement.
4. Memory retrieval avoids old permission-noise contamination.
5. Timeline view clearly shows: action -> state -> hint -> deterministic verdict -> visual judge verdict -> final verdict.

## Open Risks

1. Vision extraction drift across themes/zoom/resolution.
2. Deterministic verifier overfitting to one skin/layout.
3. LLM judge consistency under ambiguous visuals.
4. Step-budget pressure may still require stronger planning policy.

## Next Implementation Order

1. Referee disagreement mode + deterministic kick verifier.
2. Add separate visual judge path with reference-screenshot comparison.
3. Keep `extract_fl_state` planning-only (not scoring authority).
4. Expand timeline output with deterministic/visual/final verdict markers.
5. Run 5x ten-step consistency benchmark with reproducible report.

## Implementation Checklist (Logic-First)

### 1) Referee disagreement mode

What:

- Add a final verdict state: `pass | fail | uncertain`.
- If deterministic verifier and visual judge disagree, return `uncertain` (treated as fail for promotion).

Why this helps:

- Prevents false-positive wins from one hallucinating component.
- Keeps memory clean by only rewarding trusted outcomes.

How (runtime logic):

1. Compute deterministic result from contract.
2. Compute visual judge result from final screenshot + reference screenshot + rubric.
3. If both `pass`, final = `pass`.
4. If both `fail`, final = `fail`.
5. If mismatch, final = `uncertain`, reason = `judge_disagreement`.

### 2) Deterministic verifier as contract primitive (not task script)

What:

- Verify step pattern from image geometry + active-step detection under a JSON contract.
- Keep verifier generic around row/grid/toggle primitives.

Why this helps:

- Gives objective pass/fail signal for promotion and benchmarking.
- Avoids brittle free-text claims from model outputs.

How (runtime logic):

1. Read contract (`target_row_regex`, `required_steps`, `forbidden_steps`).
2. Extract row + grid coordinates from current state.
3. Detect active cells per step index.
4. Compare against required/forbidden rules.
5. Emit structured referee result with evidence.

### 3) `extract_fl_state` stays advisory

What:

- Use `extract_fl_state` only to choose next actions, never as final authority.

Why this helps:

- Keeps model flexibility for exploration.
- Avoids over-trusting uncertain vision parsing.

How (runtime logic):

1. Executor requests `extract_fl_state` when uncertain.
2. Action planning can use this output.
3. Final scoring comes from deterministic + visual judge, not extractor self-claims.

### 4) Memory gating by trusted outcome

What:

- Promote lessons only when final verdict is `pass` (or clear `fail` diagnosis with strong evidence).
- Suppress lessons produced during `uncertain` runs unless repeated with consistent evidence.

Why this helps:

- Prevents memory pollution from ambiguous runs.
- Increases retrieval precision over time.

How (runtime logic):

1. Write verdict + reason into run metadata.
2. If verdict `uncertain`, set lesson weight low and block promotion.
3. If lesson repeatedly retrieved with no gain, suppress.

### 5) Timeline observability upgrade

What:

- Show all steps in order with explicit markers:
  - action,
  - extracted state summary,
  - deterministic referee snapshot,
  - visual judge snapshot,
  - disagreement marker,
  - final verdict.

Why this helps:

- Demo clarity.
- Faster debugging when behavior diverges.

How (runtime logic):

1. Persist state snapshot after relevant steps.
2. Persist referee evidence block at end.
3. Render one timeline view with lane tags (`policy`, `state`, `referee`, `memory`).

## “Will this scale?” (Direct answer)

Yes, if we keep this split:

1. Generic primitives in code.
2. Declarative contracts in data.
3. App-specific adapters minimal and thin.

No, if we keep adding one-off per-task Python rules.

## 4-Hour Feasibility

### Short answer

Yes, for a **strong demo slice**. No, for full “all software” production robustness.

### 4-hour scope (realistic)

Must ship:

1. Referee disagreement mode (`pass/fail/uncertain`).
2. Deterministic FL kick-pattern verifier wired into final verdict.
3. Memory promotion blocked on `uncertain`.
4. Timeline output showing disagreement + final authority.
5. 3-5 reproducible 10-step runs with report.

Should ship (if time remains):

1. Better lesson suppression for uncertain/noisy runs.
2. One optional wide-scaling experiment (2-3 rollouts, judge pick best).

Defer:

1. Cross-app primitive pack (Photoshop/browser/universal UI kit).
2. Full training/data flywheel.

### Success definition for this 4-hour window

- Zero false-positive pass on wrong FL screenshot.
- At least one valid 10-step pass with deterministic + visual judge agreement.
- Clear demo timeline proving why a run passed or failed.

## Judge Model Decision (Current)

- `extract_fl_state` currently uses `model_decider` (`claude-haiku-4-5`) in `agent.py`.
- `model_heavy` is `claude-opus-4-6`.
- Side-by-side A/B on the same FL screenshot showed mixed behavior:
  - Haiku matched `1/5/9/13` in one case,
  - Opus over-detected active steps in the same case.
- Decision: do not rely on a single extractor model for pass/fail.
- Plan: keep extractor advisory and restore dedicated visual judge path with reference-image comparison.

## External Patterns (Web Research)

### Agent S3 pattern (what to borrow)

Source stack:

- S3 paper: `https://arxiv.org/abs/2510.02250`
- S3 implementation: `https://github.com/simular-ai/Agent-S`

Pattern:

- Keep single-run policy relatively simple,
- run multiple rollouts in parallel,
- summarize each trajectory into behavior/facts,
- use a comparative judge to select best rollout (Behavior Best-of-N).

Adoption note:

- For this project, this can be introduced as a fallback mode for hard tasks,
- while preserving strict single-run mode for cost-sensitive demos.

### Official vendor loop patterns

Sources:

- OpenAI computer use guide: `https://developers.openai.com/api/docs/guides/tools-computer-use`
- OpenAI CUA article: `https://openai.com/index/computer-using-agent/`
- Anthropic computer use docs: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool`
- Anthropic safety/research note: `https://www.anthropic.com/news/developing-computer-use`

Shared pattern:

- action loop with screenshot-grounded observation each turn,
- explicit stop/iteration bounds,
- safety checks + human acknowledgment for risky actions,
- environment sandboxing and allowlist controls.

### Benchmark-backed reliability pattern

Sources:

- OSWorld paper/page: `https://arxiv.org/abs/2404.07972`, `https://os-world.github.io/`

Pattern:

- use executable/verifiable outcomes (not text-only success),
- evaluate cross-app and long-horizon behavior,
- measure disagreement and failure modes explicitly.
