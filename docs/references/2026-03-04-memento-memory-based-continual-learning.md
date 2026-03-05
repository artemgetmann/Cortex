# Memento: Memory-based continual learning for LLM agents

- **Source (X post):** https://x.com/sumanth_077/status/2028820076892475419
- **Author:** @sumanth_077
- **Captured:** 2026-03-04 (Asia/Dubai)

## Why this is relevant to Cortex

Memento’s core idea is very close to a Cortex-style architecture: improve agent behavior over time by storing and retrieving prior trajectories, rather than retraining model weights.

## Key points from the post

- Proposes **continual learning through memory**, not weight updates.
- Maintains a **Case Bank** of past trajectories (task, steps, tools used, outcomes).
- Uses **case-based retrieval** so new tasks can reuse similar prior solutions.
- Describes a **Planner/Executor split**:
  1. Planner LLM decomposes tasks, retrieves cases, selects plan.
  2. Executor runs subtasks via tools (search, code, docs, MCP ecosystem) and logs outcomes back into memory.
- Claims strong performance on long-horizon and out-of-distribution tasks.
- Stated as **open source** in the post.

## Cortex mapping ideas (quick)

- Case Bank ↔ Cortex long-term episodic memory.
- Retrieval + planning loop ↔ Cortex task router/planner.
- Outcome logging ↔ Cortex learning signal pipeline.
- MCP-style tool abstraction ↔ Cortex tool runtime layer.

## Notes

- The post says the GitHub link is in comments; this capture does not include that comment URL.
