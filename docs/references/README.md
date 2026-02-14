# Self-Improving Agent Research — Reference Library

## Why These Papers Matter

Cortex is a self-improving agent that learns across sessions without any weight updates.
It fails, generates lessons, loads them next time, and promotes skill patches when scores improve.
This puts us in a small but powerful camp: **in-context lifelong learning with API-only models**.

## The Three Camps of "Self-Improving" Agents

### Camp 1: RL Fine-Tuning (weight updates)
Most papers in this space. LLM weights get updated via RL (PPO, GRPO, DPO).
The "self-improvement" is gradient descent with extra steps.

- **Requires**: GPU clusters, open-weight models, training infrastructure
- **Cannot work with**: Claude, GPT, or any closed-source API
- **Risk**: Catastrophic forgetting, expensive, slow iteration

Papers: Eureka, SAGE, SkillRL, SWE-RL

### Camp 2: In-Context Learning (no weight updates) — THIS IS US
The model stays frozen. Learning = better external memory loaded into context.
Skills, lessons, retrieved examples — all injected into the prompt.

- **Works with**: Any model via API (Claude, GPT, etc.)
- **Speed**: Immediate — next session loads new lessons
- **Interpretable**: Read the lessons, read the skills, understand what changed
- **Ceiling**: Bounded by base model capability (but that ceiling keeps rising)

Papers: Voyager, SICA, **Cortex**

### Camp 3: Self-Play Curriculum
Agent generates its own training problems with increasing difficulty.
Usually combined with Camp 1 (RL) for the actual learning.

Papers: Agent0, SWE-RL, Absolute Zero

## Our Thesis

Most production AI agents use closed-source models via API.
You can't RL fine-tune Claude or GPT. But you CAN:

1. Run sessions, evaluate with deterministic contracts
2. Generate specific lessons from failures
3. Load those lessons into context for the next run
4. Promote validated improvements into persistent skill docs

This is what humans do — fail, take notes, read notes next time.
No brain surgery (weight updates), just better notes (lessons + skills).

**Validation**: On `incremental_reconcile`, this loop took us from 0/3 to 3/4 pass rate.
Session 9303 failed with DISTINCT ON errors, generated 4 specific lessons.
Session 9304 loaded those lessons, avoided the trap, scored 1.0 with zero errors.
The learning loop closes.

## Comparison Table

| | RL (Camp 1) | In-Context (Camp 2 / Us) | Self-Play (Camp 3) |
|---|---|---|---|
| Learning depth | Changes what model *can* do | Changes what model *knows* | Depends on combo |
| Works with closed models | No | **Yes** | No |
| Infrastructure | GPU clusters | API calls | GPU clusters |
| Iteration speed | Hours/days | Seconds | Hours/days |
| Interpretability | Black box | Fully transparent | Mixed |
| Catastrophic forgetting | Real risk | Zero risk | Real risk |
| Deployability | Hard | **Easy** | Hard |

## Papers (by relevance to our approach)

### Tier 1: Architecture Twins
| Paper | Year | Key Idea | Results |
|---|---|---|---|
| [Voyager](voyager/) | 2023 | Skill library + auto-curriculum + iterative prompting in Minecraft | 3.3x more items, 15.3x faster milestones |
| [SICA](sica/) | 2025 | Agent edits its own orchestration code via reflection | 17-53% gains on SWE-bench |

### Tier 2: Interesting Mechanisms (RL-based, different camp but useful ideas)
| Paper | Year | Key Idea | Results |
|---|---|---|---|
| [Eureka](eureka/) | 2024 | LLM writes reward functions, iteratively improves via eval feedback | 83% win rate vs human experts |
| [SAGE](sage/) | 2024 | Sequential rollout — skills from task N feed into task N+1 | +8.9% scenario completion, 59% fewer tokens |
| [SkillRL](skillrl/) | 2025 | Hierarchical skill bank + recursive evolution via RL | +15.3% over baselines |

### Tier 3: Self-Play / Zero-Data (future direction)
| Paper | Year | Key Idea | Results |
|---|---|---|---|
| [SWE-RL](swe-rl/) | 2024 | Agent injects bugs then fixes them, increasing complexity | +10.4 on SWE-bench Verified |
| [Agent0](agent0/) | 2025 | Curriculum agent + executor agent, zero human data | +18% math, +22% reasoning |

## What We Could Steal

- **From Voyager**: Embedding-based skill retrieval (we currently load all skills; could get selective)
- **From SICA**: Let the agent edit its own agent_cli.py code, not just skill docs
- **From SAGE**: Sequential task chains — run tasks in dependency order, feed lessons forward
- **From Agent0**: Self-generated curriculum — agent proposes its own next task
- **From Eureka**: Evolutionary search over multiple reward/eval variants in parallel
