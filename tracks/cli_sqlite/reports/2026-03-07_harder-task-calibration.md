# Harder Task Calibration — March 7, 2026

## What changed

- Added new SQLite transfer task:
  - `tracks/cli_sqlite/tasks/incremental_reconcile_audit_transfer/`
- Added task-specific skill:
  - `tracks/cli_sqlite/skills/sqlite/incremental-reconcile-audit-transfer/SKILL.md`
- Extended SQLite deterministic repair path so this task stays inside the same
  repair family as `incremental_reconcile` instead of falling back to generic
  prose guidance.

## Why this task was added

The goal was to get a third proof slice that is:

1. deterministic,
2. short to execute,
3. harder than `incremental_reconcile`,
4. still close enough to inherit existing lesson/repair patterns.

This task adds two side conditions on top of the original family:

- invalid amount rows must go to `rejects` with reason `invalid_amount`
- one `batch_audit` row must be written with exact counts

## What we learned

### 1. Routing bug was real

Before adding the new skill, the task routed to the generic
`sqlite/import-aggregate` skill. That skill tells the model to build tables and
insert all fixture rows, which is the wrong behavior for this task family.

Result:

- wrong schema guesses,
- invalid `rejects` inserts,
- noisy failures that were not really about memory.

Adding the task-specific skill fixed that.

### 2. The task is now valid, but not yet a clean benchmark

Single-run probes showed:

- at 5 steps: both ON and OFF can pass
- at 4 steps: OFF can still pass, ON can fail from model variance
- at 3 steps: OFF still passed once, ON failed once

So the task is not broken anymore, but it is not yet a trustworthy proof slice.

Why not:

- contract-gap retry plus the task-specific skill already solve too much of it
- memory never activated in the calibration probes
- the remaining failures were mostly model variance, not stable repeatable gaps

That means this task is useful as a live task, but not yet good science for
"lessons helped" evidence.

## Decision

Stop here and do not spend a full 10/10 ON/OFF on this task yet.

Reason:

- it would mostly measure retry + prompt variance
- it would not cleanly isolate memory lift

## Recommended next move

Design the next proof slice so that:

1. OFF fails reliably under a tight cap,
2. contract-gap retry alone is not enough,
3. memory has room to help on later runs,
4. the task still uses deterministic evaluation.
