# CLI SQLite Track

This track is an isolated, fast-iteration lab for Memory V2.

## Why This Exists

Current AI agents mostly reset between chats.
- They can recover inside one run.
- They usually repeat the same mistakes in a new run unless a user manually curates memory/skills.

Memory V2 addresses that gap.
- Capture failures at runtime (`hard_failure`, `constraint_failure`, `progress_signal`, `efficiency_signal`).
- Convert failures into reusable lessons.
- Retrieve relevant lessons automatically before run and on error.
- Track lesson utility over repeated runs so low-value memory gets suppressed.

Why this matters:
- Fewer repeated errors across sessions.
- Faster recovery after interference from other domains/tasks.
- Better step/time/token efficiency without requiring users to manually manage memory.

## Goals

- Keep FL Studio code path untouched.
- Run deterministic CLI tasks in seconds.
- Learn from failures via lessons and gated skill updates.
- Promote queued skill patches only when score trend improves.

## Layout

- `agent_cli.py`: Main CLI agent loop.
- `executor.py`: Safe `sqlite3` tool executor and task DB bootstrap.
- `eval_cli.py`: Contract-driven deterministic evaluator.
- `skill_routing_cli.py`: Skill manifest build/routing and `read_skill` resolution.
- `learning_cli.py`: Lesson generation, storage, and retrieval.
- `self_improve_cli.py`: Candidate queue, skill patching, and promotion gate.
- `memory_cli.py`: Session/event/metrics persistence.
- `scripts/run_cli_agent.py`: Main runner.
- `scripts/score_cli_session.py`: Deterministic re-score for a session.
- `tests/test_cli_track.py`: Unit and integration tests for this track.

## Tasks

- `import_aggregate`: CSV import + grouped totals.
- `incremental_reconcile`: transaction-safe ingest, dedupe-by-id, rejects logging, checkpoint metadata.

## Quick Start

```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id import_aggregate \
  --session 1001 \
  --verbose
```

```bash
python3 tracks/cli_sqlite/scripts/score_cli_session.py \
  --task-id import_aggregate \
  --session 1001
```

## Notes

- Runtime artifacts live under `tracks/cli_sqlite/sessions/` and `tracks/cli_sqlite/learning/`.
- Default models are Haiku for executor and critic.
- Critic-only escalation is enabled by default (`haiku -> sonnet -> opus`) when score/no-update streak triggers fire.
- Skill-read gate is enabled by default. `run_sqlite` is blocked until at least one routed skill is loaded via `read_skill`.

## Strict Transfer Modes

- `--learning-mode legacy`: Original behavior (domain-tuned critic prompt + command-pattern hint routing).
- `--learning-mode strict`: Generic critic contract + retrieval-backed context + semantic hint routing (strict hint cap = 2).

## Holdout and Cross-Domain Validation

- Holdout domain: `fluxtool` (remapped command/operator language).
- Cross-domain runner: `tracks/cli_sqlite/scripts/run_cross_domain.py`.
- Validation command matrix and expected signatures: `docs/STRICT-TRANSFER-VALIDATION.md`.

## Hackathon Demo (One Command)
Clean presentation mode (`--pretty`) suppresses giant JSON dumps and prints compact summaries:

```bash
AUTO_TIMELINE=1 AUTO_TOKEN_REPORT=1 \
bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh --pretty
```

If you want full raw payloads in terminal output, run without `--pretty`.

What this command does:
- Runs 3 waves of mixed protocol:
  - `gridtool -> fluxtool -> shell(excel) -> sqlite -> grid retention`
- Wave 1 starts cold (`--clear-lessons`).
- Waves 2 and 3 reuse memory from prior waves.
- Auto-generates timeline dumps for one representative session per wave.
- Auto-generates token report from session metrics (includes prompt/cache token usage with lessons in context).

Default artifacts:
- `/tmp/memory_mixed_wave1_<start_session>.json`
- `/tmp/memory_mixed_wave2_<start_session+5>.json`
- `/tmp/memory_mixed_wave3_<start_session+10>.json`
- `/tmp/memory_timeline_wave1_<start_session>.txt`
- `/tmp/memory_timeline_wave2_<start_session+5>.txt`
- `/tmp/memory_timeline_wave3_<start_session+10>.txt`
- `/tmp/memory_mixed_tokens_<start_session>.json`

Useful knobs:
- `START_SESSION=57001` to avoid overwriting old runs.
- `MAX_STEPS=5` (default) for pressure; raise for easier solves.
- `AUTO_TIMELINE=0` to skip timeline generation.
- `AUTO_TOKEN_REPORT=0` to skip token summary.
