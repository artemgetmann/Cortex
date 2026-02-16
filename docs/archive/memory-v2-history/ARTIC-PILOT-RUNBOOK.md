# Artic Pilot Runbook

Run from repo root:

```bash
cd /Users/user/Programming_Projects/Cortex
```

## 1) Single run (Artic API pilot scaffold)

```bash
python3 tracks/cli_sqlite/scripts/run_agent_sdk_pilot.py \
  --task "Artic API pilot smoke run: search artworks for monet and return title + id" \
  --session 41001 \
  --max-steps 12 \
  --mode dry-run
```

## 2) Repeated runs (3 pilot iterations)

```bash
for s in 41001 41002 41003; do
  python3 tracks/cli_sqlite/scripts/run_agent_sdk_pilot.py \
    --task "Artic API pilot smoke run: search artworks for monet and return title + id" \
    --session "$s" \
    --max-steps 12 \
    --mode dry-run
done
```

## 3) Timeline view (for sessions that emit Memory V2 events)

```bash
python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py \
  --start-session 41001 \
  --end-session 41003 \
  --show-ok-steps \
  --show-lessons 8
```

## 4) Memory stability mini-run (demo mode)

```bash
python3 tracks/cli_sqlite/scripts/run_memory_stability.py \
  --grid-runs 1 \
  --fluxtool-runs 1 \
  --retention-runs 1 \
  --start-session 42001 \
  --max-steps 6 \
  --bootstrap \
  --posttask-mode direct \
  --memory-v2-demo-mode \
  --output-json /tmp/artic_memory_stability_mini.json \
  --verbose
```
