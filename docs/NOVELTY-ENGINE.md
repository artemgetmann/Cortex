# Novelty Engine

## Why this exists

Humans get better when they do:

1. new things,
2. slightly difficult things,
3. with feedback,
4. repeatedly,
5. and then revisit similar problems later.

Cortex should do the same.

The point is not random exploration. Random exploration burns tokens and teaches noise.

The point is controlled novelty:

- try tasks that are new enough to stretch the system,
- but close enough that lessons can transfer,
- then measure whether later performance improves.

## Core idea

The novelty engine is a small scheduler that decides:

1. what the system should practice next,
2. when to repeat old task families,
3. when to try a new domain or a harder variant,
4. when not to waste effort on something already saturated [too easy to measure learning].

## First-principles rules

### Rule 1: novelty must be useful

Do not pick tasks just because they are different.

Pick tasks that are:

- weak spots,
- new but related,
- or good transfer tests.

### Rule 2: exploration must be budgeted

Most runs should still be useful or measurable.

Default split:

- 80% exploitation [useful benchmarks / user tasks / known weak areas]
- 20% exploration [new family / harder variant / new domain]

### Rule 3: the system needs a weakness map

The model does not naturally know what it is bad at.

So Cortex must track it explicitly.

For each task family, store:

- pass rate
- last-5 pass rate
- mean score
- mean errors
- lesson activation rate
- retrieval help ratio
- repeated failure signatures
- date last attempted
- number of distinct variants seen

This becomes the machine version of self-awareness.

### Rule 4: novelty only matters if learning transfers

If Cortex improves only on the exact same task, that is memorization.

We care about:

- same-task lift
- family lift
- transfer lift on similar-but-not-identical tasks

## Proposed task selection logic

Each candidate task gets a score.

Higher score means more worth running.

### Candidate score

`novelty_score = weakness + uncertainty + transfer_value + recency_bonus - saturation_penalty - cost_penalty`

### Terms in plain English

- `weakness`
  - high if pass rate is low or repeated errors are high
- `uncertainty`
  - high if we do not have enough runs yet
- `transfer_value`
  - high if the task is a good test of whether lessons generalize
- `recency_bonus`
  - high if we have not touched this family in a while
- `saturation_penalty`
  - high if the task is already too easy and no longer teaches us anything
- `cost_penalty`
  - high if the task is slow/expensive relative to the information it gives

## Suggested buckets

Every run candidate belongs to one bucket:

1. `known_weak`
   - families with low pass rate or repeated failure loops
2. `transfer_probe`
   - similar to a known family, but with one extra condition
3. `new_family`
   - mostly unseen task type
4. `saturated`
   - too easy; avoid unless used as a sanity check
5. `bad_instrument`
   - too noisy; avoid for learning proof

## Minimal v1 plan

Do not overbuild this.

Version 1 should only do:

1. maintain a small `novelty_registry.json`
2. score task families using simple heuristics
3. pick the next task from:
   - one weak family
   - one transfer probe
   - one new family
4. enforce a simple exploration budget

That is enough to start.

## Suggested data model

```json
{
  "task_family": "sqlite_incremental",
  "domain": "sqlite",
  "runs_total": 18,
  "pass_rate": 0.61,
  "last5_pass_rate": 0.80,
  "mean_errors": 2.7,
  "lesson_activation_rate": 0.55,
  "retrieval_help_ratio": 0.48,
  "repeated_failure_signatures": [
    "required_query_mismatch|required_query|reject_breakdown"
  ],
  "variants_seen": 3,
  "last_attempted_at": "2026-03-07T12:00:00Z",
  "bucket": "known_weak"
}
```

## How this plugs into Cortex

### Input

The novelty engine reads:

- benchmark results
- session metrics
- failure signatures
- lesson activation stats

### Output

It produces:

- the next suggested task
- why it was chosen
- whether it is exploration or exploitation
- whether it is suitable for learning proof

## What this is good for

- makes exploration deliberate instead of random
- increases chance of useful lessons
- helps measure generalization
- reduces wasted token spend

## What this is not

- not autonomous wandering across random tasks
- not a replacement for user tasks
- not a guarantee of AGI

It is just a disciplined way to expose Cortex to novelty without turning the system into a token furnace.

## Practical roadmap

### Phase 1

- build novelty registry
- tag current task families
- score current families with simple heuristics
- print next recommended task list

Status in this worktree:

- implemented as `tracks/cli_sqlite/novelty_engine.py`
- CLI entrypoint: `tracks/cli_sqlite/scripts/run_novelty_engine.py`
- current scope is intentionally small:
  - reads existing `session-*/metrics.json`
  - groups tasks into explicit families
  - marks each family as `known_weak`, `transfer_probe`, `new_family`, `saturated`, or `bad_instrument`
  - outputs one simple recommendation mix

Quick test:

```bash
python3 tracks/cli_sqlite/scripts/run_novelty_engine.py --format text
```

### Phase 2

- integrate novelty suggestions into benchmark runner
- add exploration budget control
- track whether novelty-produced lessons improve later transfer

### Phase 3

- let Telegram / live product runs feed the same registry
- use real user tasks as one source of novelty
- compare user-driven novelty vs synthetic benchmark novelty

## Merge note

Do not merge novelty engine implementation back to `main` until:

1. selection logic is tested,
2. it does not break existing benchmark flows,
3. and we can show it improves task selection quality rather than adding random complexity.
