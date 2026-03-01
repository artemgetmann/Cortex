# Idea: LLM-Generated Contract + Checker

Status: backlog (not active implementation)
Owner: Cortex core loop
Created: 2026-03-01

## Problem
For truly new tasks/domains, we may not have a prewritten contract that defines what success means.

## Idea
Let an LLM generate:
1. A provisional contract (required outputs/checks/failure conditions).
2. Optional checker code for edge cases the generic checker cannot express well.

Then run everything through strict deterministic gates before trusting it.

## Why this could help
- Scales to unknown tasks faster.
- Reduces manual contract authoring overhead.
- Keeps the “user says task in natural language” flow viable across domains.

## Main risk
The same model could define and judge success ("grading its own homework"), which can inflate pass rates and hide real failures.

## Safety design (required)
1. Checker engine remains fixed and trusted by default.
2. LLM-generated contract starts as provisional only.
3. Any generated checker code runs in isolated sandbox.
4. Promotion requires repeated stability on held-out tasks.
5. If generated checker diverges from baseline behavior, demote automatically.

## Activation trigger
Only start this when:
- JSON-only contracts repeatedly fail to express task success, and
- this limitation blocks cross-domain progress for 2+ benchmark cycles.

## Exit criteria (for adoption)
- Better transfer pass rate vs baseline.
- No regression in OFF controls.
- Reproducible results across repeated runs.

