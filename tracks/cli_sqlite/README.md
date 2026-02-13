# CLI SQLite Track

This track is an isolated, fast-iteration learning loop that uses `sqlite3` instead of FL Studio GUI actions.

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
