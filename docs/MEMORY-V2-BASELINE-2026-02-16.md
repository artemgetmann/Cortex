# Memory V2 Baseline - 2026-02-16

## Commands

```bash
python3 tracks/cli_sqlite/scripts/run_memory_stability.py --grid-task-id aggregate_report --fluxtool-task-id aggregate_report_holdout --grid-runs 4 --fluxtool-runs 4 --retention-runs 4 --start-session 30001 --max-steps 4 --learning-mode strict --posttask-mode candidate --bootstrap --mixed-errors --cryptic-errors --clear-lessons --output-json /tmp/memory_stability_30001_hard12.json
python3 tracks/cli_sqlite/scripts/report_memory_health.py --input-json /tmp/memory_stability_30001_hard12.json --output-json /tmp/memory_health_30001_hard12.json
```

## Artifacts

- `/tmp/memory_stability_30001_hard12.json`
- `/tmp/memory_health_30001_hard12.json`

## Key Metrics (overall, 12 runs)

- Pass rate: `75.00%` (`9/12`)
- Mean score: `0.7917`
- Mean steps: `3.5`
- Mean tool errors: `1.0`
- Fingerprint recurrence before: `0.0833`
- Fingerprint recurrence after: `0.0000`
- Lesson activations: `12`
