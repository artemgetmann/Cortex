# FL Studio Memory V2 Plan

Status: draft  •  Owner: user + Codex
Last updated: 2026-02-16

## Purpose
Deliver an end-to-end Memory V2 experience for the FL Studio 4-on-the-floor kick demo that:
- surfaces every command attempt + failure + hint for human inspection,
- captures runtime errors/fingerprint/tag signals so lessons are domain-agnostic,
- lets the judge reference actual screenshots/zooms when validating success,
- shows measurable improvement across runs once lessons are injected.

This doc is the active plan for the FL Studio axis; modifications here are the single source of truth until approved.

## Scope
1. The baseline execution path is `scripts/run_agent.py --task "Create a 4-on-the-floor kick drum pattern"` (default models + skills).
2. Memory V2 must plug into this path without rewriting the agent SDK pipeline—reuse existing adapters (computer tool, log capture, skill prompts).
3. Failure capture + retrieval should remain task/domain agnostic: no hard-coded CLI error strings or regexes.

## Success criteria
- We can replay one run and step through a timeline that shows: initial prompt + loaded lessons, each tool call, each failure with ErrorEvent (fingerprint + tags), hints injected, and final verification.
- A judge model can look at the recorded zoom/screenshot evidence and explain how the 4-on-the-floor pattern meets/does not meet the checklist.
- Running the same task twice with cleared lessons shows repeated failures until relevant lessons persist and reduce errors.

## Execution Phases

### Phase A: Baseline understanding (📍ongoing)
- Review `scripts/run_agent.py`, `agent.py`, `computer_use.py`, and `skills/fl-studio/*` to confirm current behavior and logging surface.
- Confirm we have tooling to export per-step metadata (events.jsonl, metrics.json, session screenshots). No code change yet.
- Status: in progress.

### Phase B: Failure capture + lesson store
- The FL loop must emit `ErrorEvent` (text + fingerprint + state/action tags) for any tool failure, not just pre-known errors.
- Add helper to `memory.py`/`computer_use.py` if needed to normalize error/state/action for future retrieval.
- Lessons are stored in `learning/` JSONL with statuses (candidate/promoted/etc.) and should be backward compatible with existing store.
- Status: TODO.

### Phase C: Retrieval + injection visibility
- Retrieve on-error before reissuing the same tool to see if a hint can break the failure loop.
- Ranking follows the Memory V2 formula (fingerprint, tag overlap, similarity, reliability, recency) and respects caps/transfer policies.
- Timeline demo for FL should include: system prompt, preloaded lessons, attempted commands, error + fingerprint, injected hints text, final attempt output, screenshot references.
- Status: TODO.

### Phase D: Judge integration + images
- Extend the judge path so it can see the recorded PNG/zoom evidence for each run and reason about success (4 lit steps + playback).
- Document the judge's evaluation prompt, required zoom images, and how lessons influence scoring.
- Prepare doc in `docs/` capturing judge evidence requirements (zoom names, expected GUI states).
- Status: TODO.

### Phase E: Demonstration harness
- Build a demo script (or extend existing timeline demo) that: (a) runs a session, (b) collects metrics/events, (c) outputs JSON summary, (d) optionally clears lessons between runs for comparison.
- Provide commands for: forced failure -> recovery, 3-run improvement, toggle memory, show preloaded vs post-injection lessons.
- Status: TODO (script planned but not yet run).

### Phase F: Documentation + handoff
- Keep this plan updated with statuses, decisions, and commands.
- Commit final artifacts + plan to prove reproducibility for the hackathon video.
- Status: pending.

## Immediate next steps (per user instructions)
1. Use parallel agents to explore/validate Phase A context (this file + runtime artifacts) while drafting Phase B implementation details.
2. Document the forced failure + recovery command plan (see below) without executing yet.
3. Update `AGENTS.md` or other documentation as needed to reflect FL-specific memory behaviors (optional later).

## Phase E command plan (execute later)
- Baseline fail/recover run: `python3 scripts/run_agent.py --task "Create a 4-on-the-floor kick drum pattern" --session 52001 --max-steps 40 --bootstrap --learning-mode strict --posttask-mode candidate --verbose --show-lessons --show-tool-output`. Capture timeline artifacts for demo.
- Cleared memory comparison: repeat with `--clear-lessons` (or manually delete lessons.jsonl) at sessions 52002-52004 to highlight cross-run improvement while keeping other flags identical.
- Judge validation run: `python3 scripts/run_agent.py --task "..." --session 52005 --judge-model claude-sonnet-4-5 --expect-zoom zoom_01.png`. Collect judge output referencing screenshot to confirm 4-on-the-floor success.
- Mixed-protocol demo (for when scheduler ready): run gridtool -> fluxtool -> excel -> sqlite sequence using new harness (command TBD after script exists).

## Testing targets (to be executed later)
- Run `python3 scripts/run_agent.py --task "Create a 4-on-the-floor kick drum pattern" --session 51001 --max-steps 40 --bootstrap --learning-mode strict --posttask-mode candidate --verbose` as a baseline.
- Re-run with `--clear-learning` (or manual lesson cleanup) + `--show-lessons` to demonstrate improvement.
- Timeline demo: `python3 scripts/memory_timeline_demo.py` (FL version to be created). Include `--show-lessons` and `--show-tool-output`.
- Judge-run command: `python3 scripts/run_agent.py ... --judge-mode <??>` (to be defined once judge is wired).
