# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Cortex?

Cortex is an AI agent that teaches itself FL Studio (music production) through computer use + persistent memory. It controls FL Studio Desktop on macOS via screenshots and keyboard/mouse actions, learning across sessions by generating and refining skill documents.

**Hackathon project:** Anthropic "Built with Opus 4.6" (Feb 10-16, 2026).

## Commands

```bash
# Install dependencies (Python 3.11+, macOS only)
pip install -r requirements.txt

# Configure
cp .env.example .env   # then set ANTHROPIC_API_KEY

# Run an agent session
python3 scripts/run_agent.py \
  --task "Create a 4-on-the-floor kick drum pattern" \
  --session 2201 --max-steps 80 --verbose

# Run without skills (baseline comparison)
python3 scripts/run_agent.py --task "..." --session 1 --no-skills

# Override model
python3 scripts/run_agent.py --task "..." --model claude-haiku-4-5
```

No test suite, no linter, no build step. Verify changes by running agent sessions and checking `sessions/session-NNN/` output (events.jsonl, metrics.json, step-NNN.png screenshots).

## Architecture

```
agent.py          ← Agentic loop: screenshot → Opus API → parse tool_use → execute → repeat
computer_use.py   ← macOS Quartz CGEvent wrapper (key, click, screenshot, coordinate mapping)
config.py         ← Env-based config loader (CortexConfig dataclass)
memory.py         ← Session path management + JSONL/metrics I/O
consolidate.py    ← Post-session skill generation from logs (stub, not yet implemented)

scripts/
  run_agent.py    ← CLI entry point (argparse → run_agent())

skills/fl-studio/ ← Markdown skill docs loaded into agent context
  index.md        ← Table of contents
  drum-pattern.md ← First skill (4-on-the-floor kick pattern)

sessions/         ← Per-session output (gitignored)
  session-NNN/    ← events.jsonl + metrics.json + step-NNN.png screenshots

docs/
  IMPLEMENTATION.md  ← Primary technical spec (architecture, API setup, dev plan)
  HANDOFF.md         ← Quick-start execution guide
  FL-STUDIO-REFERENCE.md ← FL Studio UI/shortcuts reference
```

### Data flow

1. `run_agent()` builds system prompt + loads skills from `skills/fl-studio/` into context
2. Sends task to Anthropic API with `computer` tool definition
3. Model returns `tool_use` blocks (screenshot, key, click, etc.)
4. `ComputerTool.run()` executes via macOS Quartz CGEvent APIs, returns screenshot
5. Loop continues until model stops requesting tools or hits `max_steps`
6. Events logged to JSONL, metrics written to JSON, screenshots saved as PNGs

### Key design decisions

- **No database/vector store.** Opus 4.6 has 1M token context — skills loaded directly into prompt.
- **Prompt caching** on system blocks + recent user turns (~80% cost reduction on repeated context).
- **Quartz CGEvent APIs** (not pyautogui) for reliable macOS input delivery.
- **Bundle ID matching** (`com.image-line.flstudio`) to find FL Studio, not window title.
- **Coordinate mapping:** API operates in 1024x768 space, mapped to FL Studio window bounds at runtime.
- **UI settle detection:** Post-action screenshot polling with image similarity threshold prevents race conditions.

## macOS / Quartz gotchas

- FL Studio **must be visible and forefront** for input delivery to work.
- `CGEventPostToPid` requires Accessibility permissions granted to the terminal running the script.
- Claude Code's sandbox blocks Quartz/CGEvent APIs silently — use `dangerouslyDisableSandbox: true` for any Bash commands that invoke Quartz (screenshots, key events, window queries).
- `CGWarpMouseCursorPosition` works even with sandbox (different API path).
- `computer_use.py` forbids dangerous key combos (cmd+q, cmd+tab, cmd+w, cmd+m).

## Computer Tool Compatibility (Important)

- Decider models (default Haiku/Sonnet path) use `computer_20250124`.
- Heavy model (default Opus path) uses `computer_20251124`.
- The `zoom` action is available only with `computer_20251124` (Opus path).
- Do not ask Haiku/Sonnet runs to use zoom; they should use screenshot + precise clicks instead.
- If you need zoom-dependent precision checks, run with Opus.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | API key |
| `CORTEX_MODEL_HEAVY` | `claude-opus-4-6` | Main agent model |
| `CORTEX_MODEL_DECIDER` | `claude-haiku-4-5` | Cheaper model for gate tests |
| `CORTEX_DISPLAY_WIDTH_PX` | `1024` | API coordinate space width |
| `CORTEX_DISPLAY_HEIGHT_PX` | `768` | API coordinate space height |
| `CORTEX_ENABLE_PROMPT_CACHING` | `1` | Enable prompt caching |
