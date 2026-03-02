# OpenAI Agents SDK Integration Notes

## Scope
- Keep Cortex learning/eval pipeline unchanged.
- Add optional executor transport: `openai_agents_sdk`.
- Preserve existing `openai` transport as fallback and baseline.

## Why this shape
- The memory loop, contracts, and metrics are the proof mechanism.
- Swapping only the executor transport keeps experiments comparable.
- Minimal-risk change avoids another monolithic rewrite in `agent_cli.py`.

## Runtime behavior
- New backend value: `--llm-backend openai_agents_sdk`
- Uses OpenAI Agents SDK model transport (Responses model API surface).
- Tool execution remains in the existing Cortex runtime loop.

## Install (optional dependency)
```bash
pip install openai-agents openai
```

If missing and backend is selected, runtime raises a clear install error.

## Example
```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id incremental_reconcile \
  --domain sqlite \
  --session 4001 \
  --max-steps 6 \
  --llm-backend openai_agents_sdk \
  --model-executor gpt-5-nano \
  --model-judge gpt-5-nano \
  --benchmark-deterministic
```

## Notes
- This is not a full loop migration to SDK Runner.
- It is a transport-layer integration so we can A/B against the existing backend with the same memory loop.
