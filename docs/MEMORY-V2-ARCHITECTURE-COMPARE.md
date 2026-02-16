# Memory V2 vs Original HTML Diagram

This compares:
- legacy diagram: `docs/archive/fl-studio-legacy/cortex-architecture.html`
- current runtime flow: `docs/MEMORY-V2-CURRENT-FLOW.html`

## High-level
The original HTML models the FL Studio computer-use architecture with skill-manifest routing.  
The current system for this branch is the CLI Memory V2 loop centered on error capture, retrieval lanes, and lesson lifecycle.

## Same
| Area | Legacy Diagram | Current Memory V2 | Why it stayed |
|---|---|---|---|
| Executor loop exists | Main executor action loop | Executor model step loop with tool calls | Core agent pattern still execute -> observe -> continue |
| Referee concept exists | Post-step checks/stuck detection and policies | Deterministic evaluator first + LLM judge fallback | Need independent quality signal outside executor |
| Persistent artifacts | Session logs/metrics shown | `events.jsonl`, `memory_events.jsonl`, `metrics.json`, `lessons_v2.jsonl` | Learning requires persistent traces |
| Safety/guardrails | Recovery policy + escalation | Schema tool-input validation, scoped retrieval, suppression | Guardrails are required to prevent loops/pollution |

## Not Same
| Area | Legacy Diagram | Current Memory V2 | Why changed |
|---|---|---|---|
| Domain | FL Studio GUI computer-use | CLI multi-domain (`gridtool`, `fluxtool`, `sqlite`, `artic`, `shell`) | Branch goal shifted to domain-agnostic memory system |
| Primary memory unit | Skill docs + manifest summaries | Lesson records with fingerprints/tags/status/utility | Need transferable failure memory, not procedural docs only |
| Retrieval path | Router + optional `read_skill(ref)` | Pre-run retrieval + on-error retrieval with strict/transfer lanes | Memory must activate exactly at failure points |
| Failure understanding | Stuck detector/recovery policy | Universal channels: hard/constraint/progress/efficiency | Removes dependence on pre-known domain-specific error strings |
| Promotion logic | PostTask skill patch update | Utility-based promote/suppress lifecycle in V2 store | Need measurable usefulness over repeated runs |
| Transfer controls | Not modeled | strict lane default, optional transfer lane (capped/down-weighted) | Prevent cross-domain contamination while allowing controlled transfer |
| New runtime guards | Not present | tool schema validation + reflection triggers | Reduce wasted steps and repeated-failure loops |

## Why this is the right divergence
1. The legacy diagram optimizes for one UI domain and skill-document growth.
2. Memory V2 optimizes for repeated unseen-task adaptation with measurable utility.
3. The architecture now separates:
   - task execution,
   - failure capture semantics,
   - retrieval policy,
   - lifecycle decisions.

That separation is what makes new adapters/tools pluggable without rewriting memory logic.

## Canonical docs after cleanup
- Current flow map: `docs/MEMORY-V2-CURRENT-FLOW.html`
- Legacy FL Studio architecture: `docs/archive/fl-studio-legacy/cortex-architecture.html`
- Agnostic plan: `docs/MEMORY-V2-AGNOSTIC-PLAN.md`
- Historical execution plan: `docs/archive/memory-v2-history/MEMORY-V2-EXECUTION-PLAN.md`
- Benchmark protocol: `docs/MEMORY-V2-BENCHMARKS.md`
