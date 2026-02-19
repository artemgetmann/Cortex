# Cortex: Persistent Memory For Agents

Claude Code Hackathon Project Feb 2026 (Built with Opus 4.6)

Current AI agents usually improve only inside one chat.  
New chat, same mistakes again.

That breaks real productivity.

## The Problem

Most agent memory systems are either:

- manual (user must maintain notes/skills/docs),
- session-local (wiped between chats),
- or unsafe (retrieves irrelevant memory and causes contamination).

If the user has to manage memory themselves, the product does not scale.

## The Solution In This Repo

Memory V2: an automatic memory loop that learns from failures and reuses lessons across runs.

Core loop:

1. Agent acts.
2. Runtime captures failures/progress signals.
3. Failure is fingerprinted and tagged.
4. Retrieval injects relevant lessons (pre-run + on-error).
5. End-of-run outcomes update lesson utility.
6. Lessons are promoted/suppressed over time.

This enables learning across sessions without requiring users to manually maintain skill docs.

## How Success/Failure Is Measured

We keep runtime roles:

- executor model: attempts the task.
- referee/judge layer: scores pass/fail and quality.

Evaluator behavior:

- deterministic evaluator first when available,
- LLM judge fallback when deterministic checks are unavailable/insufficient.

So outcomes are explicit and trackable, not based on vague impressions.

## What The Demo Shows

The hackathon CLI demo runs a mixed protocol:

- `gridtool` warmup,
- `fluxtool` interference,
- `shell` Excel-style interference,
- `sqlite` interference,
- `gridtool` retention check.

You should see:

- early failures in cold start,
- lesson activation in later waves,
- improved pass rate/steps/errors/tokens as memory becomes useful.

## Run The Demo (One Command)

```bash
START_SESSION=120001 \
AUTO_TIMELINE=1 AUTO_TOKEN_REPORT=1 \
bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh --pretty
```

Outputs:

- wave summaries: `/tmp/memory_mixed_wave*.json`
- timelines: `/tmp/memory_timeline_wave*.txt`
- token report: `/tmp/memory_mixed_tokens_*.json`

Legacy command compatibility (same behavior, alias wrapper):

```bash
START_SESSION=120001 \
AUTO_TIMELINE=1 AUTO_TOKEN_REPORT=1 \
bash tracks/cli_sqlite/scripts/run_hackathon_demo_legacy.sh --pretty
```

## Targeted 3-Wave Checks (Fast)

Grid memory curve (expected pattern: fail -> pass -> pass):

```bash
bash tracks/cli_sqlite/scripts/run_tool_three_waves.sh \
  --domain gridtool \
  --task-id multi_step_pipeline \
  --start-session 100651 \
  --max-steps 4
```

Shell memory curve (expected pattern: fail -> pass -> pass):

```bash
bash tracks/cli_sqlite/scripts/run_tool_three_waves.sh \
  --domain shell \
  --task-id shell_excel_multi_summary \
  --start-session 100451 \
  --max-steps 4
```

## Why This Matters

If this loop is reliable, users stop repeating themselves across chats.  
The agent gets faster, cheaper, and less error-prone over time.

That is the path from “token predictor” behavior to persistent, compounding productivity.

## Status

This repo proves the architecture in a controlled CLI lab.  
Real GUI/computer-use reliability (for harder domains like FL Studio) is still a separate reliability problem, mainly visual grounding and action precision.

## FL Studio Bench Commands

Run one live FL session:

```bash
./scripts/run_fl_live_demo.sh 210001 12
```

Run FL with subscription-backed `claude -p` executor (no API key required for executor loop):

```bash
CORTEX_LLM_BACKEND=claude_print ./scripts/run_fl_live_demo.sh 210011 12
```

Run repeated FL sessions and produce a benchmark JSON:

```bash
python3 scripts/run_fl_benchmark.py \
  --start-session 210001 \
  --runs 10 \
  --max-steps 12 \
  --llm-backend anthropic \
  --output-json /tmp/fl_benchmark_210001.json
```

Render a compact per-session FL timeline with deterministic/judge/final verdict line:

```bash
python3 scripts/render_fl_timeline.py --session 210001 --show-output
```

## Isolated VM Runner

If you want background iteration without blocking your host desktop:

```bash
./scripts/vm/provision_cortex_vm.sh
./scripts/vm/start_cortex_vm.sh
./scripts/vm/status_cortex_vm.sh
open "vnc://127.0.0.1:5905"
```

Stop it:

```bash
./scripts/vm/stop_cortex_vm.sh
```

Details and limitations: `docs/VM-RUNNER.md`

## Docs

- `docs/README.md` - docs index
- `docs/MEMORY-V2-AGNOSTIC-PLAN.md` - requirements/status
- `docs/MEMORY-V2-BENCHMARKS.md` - benchmark protocol + interpretation
- `docs/archive/memory-v2-history/HACKATHON-DEMO-NARRATION.md` - archived narration script
