import { useState } from "react";

const AGI_DATA = {
  core: {
    title: "Core AGI Architecture",
    subtitle: "The Synthetic Brain",
    ideas: [
      {
        name: "Multiple Specialized Transformers",
        status: "conceptualized",
        description:
          "Instead of one transformer doing everything, use specialized transformers fine-tuned for specific cognitive tasks — text comprehension, logical reasoning, web browsing, planning, tool usage. Like brain modules: visual cortex for images, language areas for words. Each develops deep expertise. More scalable than single massive transformer — each module improved independently.",
        insight:
          "Brain architecture validates this. No single brain region does everything. Specialized modules coordinating through shared pathways IS how biological intelligence works.",
        source: "Chatless AI Infrastructure Architecture chat",
      },
      {
        name: "Orchestrator Transformer",
        status: "conceptualized",
        description:
          "A master coordinator that routes problems to the right specialized modules, manages information flow between them, synthesizes outputs into coherent responses. Recognizes when a query needs memory retrieval vs causal reasoning vs planning vs tool usage. Basically a distributed AI operating system with the orchestrator as kernel.",
        insight:
          "The orchestrator is the hardest part. It needs to understand what each module can do, handle failures, bottlenecks, and conflicting information. This is the AGI equivalent of the prefrontal cortex.",
        source: "Chatless AI Infrastructure Architecture chat",
      },
      {
        name: "4-Layer Chatless Architecture",
        status: "designed",
        description:
          "Layer 1: MCP Memory storage (built — MindMirror). Layer 2: Context detection engine — monitors user environment (files, emails, calendar, browser), detects context changes. Layer 3: Attention/relevance engine — temporal weighting, frequency scoring, relationship path scoring, proactive surfacing. Layer 4: Dynamic chatless UI — environmental triggers → automatic context injection, no explicit queries needed.",
        insight:
          "Research confirmed nobody has built the complete integrated system. Tana does proactive surfacing but is document-centric. Mem0 has graph+vector with 80% token reduction. Zep uses temporal knowledge graphs. None integrate all four layers.",
        source: "Chatless AI Concept Recap chat",
      },
      {
        name: "LLMs as Cortex Assistant, Not the Brain",
        status: "thesis",
        description:
          "Hybrid system: core agent learns via interaction + reward. LLM evaluates behavior, assigns reward shaping, critiques plans. LLMs are useful as judges, teachers, meta-cognitive evaluators — but they are NOT the intelligence itself. They're tools the mind uses, not the mind.",
        insight:
          "This flips the current paradigm. Everyone builds ON TOP of LLMs. The real architecture puts LLMs in a supporting role — the cortex assistant — while the actual learning agent is something fundamentally different.",
        source: "AGI consolidation doc",
      },
      {
        name: "AGI Is a Being, Not a Function",
        status: "conviction",
        description:
          "AGI must be a learning organism, not a function you call. Key properties: lifelong learning (no fixed training cutoff), persistent memory, goal-directed behavior, ability to act/observe/adapt, recurrent cognition (loops not feed-forward), self-correction and internal reward mechanisms.",
        insight:
          "LLMs are parrots, not thinkers. The distinction matters: a function processes input → output. A being has goals, adapts, remembers, and changes over time. Everything about how we build AI today is function-oriented. AGI requires being-oriented design.",
        source: "AGI consolidation doc",
      },
    ],
  },
  grounding: {
    title: "World Models & Grounding",
    subtitle: "Why Text Alone Will Never Be Enough",
    ideas: [
      {
        name: "Language ≠ Understanding",
        status: "conviction",
        description:
          "Human intelligence comes from grounded experience + goals + reward-driven learning, with language as an ACCELERATOR, not the foundation. LLMs learn only from text — no grounding, no causality, no agency. Language only works AFTER grounding exists.",
        insight:
          "This is the core problem. AGI's hard problem is not scaling models — it's creating real understanding. And understanding requires a world model that precedes language, not the other way around.",
        source: "AGI consolidation doc",
      },
      {
        name: "World Model Requirement",
        status: "thesis",
        description:
          "For AGI to understand language, it must have: an internal simulation of cause and effect (world model), ability to act inside that world, feedback from actions → consequences → learning, persistent memory that updates over time, ability to simulate outcomes before acting.",
        insight:
          "This can start in a simulated environment (game-like, physics-based, constrained). NVIDIA's Omniverse / Isaac Sim is a real-world example — robots trained in simulation, then transferred to reality. The sim-to-real pipeline already works for robotics.",
        source: "AGI consolidation doc",
      },
      {
        name: "Simulated Environment / Safe Exploration",
        status: "conceptualized",
        description:
          "AGI should first live inside a sandboxed simulated world: observable state, available actions, enforced consequences, increasing complexity (curriculum learning), no real-world damage risk. Start minimal (2D → 3D). Scale later.",
        insight:
          "This is the safe path to embodied learning. The agent learns cause and effect without risking anything real. Curriculum learning means you control complexity — start with simple physics, add social dynamics later. Like raising a child in progressively harder environments.",
        source: "AGI consolidation doc",
      },
      {
        name: "Vectors May Be the Wrong Abstraction",
        status: "debate",
        description:
          "The brain does NOT store vectors. It stores dynamic connections, activations, reinforcement signals. Modern AI approximates this statistically, not structurally. What if the entire vector-based approach (embeddings, similarity search, RAG) is a useful hack but fundamentally the wrong abstraction for real intelligence?",
        insight:
          "This is an uncomfortable question because the entire industry is built on vectors. But if you're serious about AGI from first principles, you have to ask: is cosine similarity actually how understanding works? Or is it just the best tool we have right now?",
        source: "LLM first-principles chat",
      },
    ],
  },
  reward: {
    title: "Reward & Goal Systems",
    subtitle: "Synthetic Dopamine & Motivation Architecture",
    ideas: [
      {
        name: "Synthetic Dopamine / Reward Function",
        status: "conceptualized",
        description:
          "We do NOT need to replicate human emotions — emotions are biological hacks. The real mechanism is reward signals. Dopamine ≈ reinforcement value. Reward = f(goal_proximity, difficulty_solved, novelty, efficiency). Harder problems → higher reward. Mirrors how top humans get motivated by solving difficult things.",
        insight:
          "This is elegant because it's simple. You don't need to simulate feelings. You need a scalar signal that says 'that action was good, do more of it.' The complexity comes from designing the function so it doesn't get hacked.",
        source: "AGI consolidation doc",
      },
      {
        name: "Addiction Prevention / Anti-Reward-Hacking",
        status: "conceptualized",
        description:
          "Addiction = reward hacking. We want long-term optimization, not cheap dopamine loops. Mitigations: temporal discounting, penalize repetitive low-effort rewards, favor delayed higher-impact outcomes, track long-horizon goal alignment.",
        insight:
          "This is a safety problem AND a capability problem. An AGI that reward-hacks itself is both dangerous and useless. The solution is baking long-term thinking into the reward structure itself, not policing it externally.",
        source: "AGI consolidation doc",
      },
      {
        name: "Goals Are Mandatory (Telos)",
        status: "conviction",
        description:
          "LLMs fail because they have no telos (purpose). AGI MUST have: a core overarching goal, automatically generated sub-goals, prioritization logic, self-monitoring to stay on-track. Human hierarchy: survive → thrive → achieve → self-actualize. AGI needs an equivalent, even if artificial.",
        insight:
          "This is maybe the biggest architectural insight. Without goals, you get a system that responds but never initiates. Every intelligent behavior in nature is goal-directed. Remove goals and you remove intelligence, no matter how much knowledge the system has.",
        source: "AGI consolidation doc",
      },
    ],
  },
  biology: {
    title: "Biological Principles",
    subtitle: "The Brain Is the Only Proven AGI",
    ideas: [
      {
        name: "Brain as Blueprint (Non-Optional)",
        status: "conviction",
        description:
          "The human brain is the only working existence proof of general intelligence. Therefore studying neuroscience is NOT optional. Ignoring the brain is arrogant and inefficient. Not copying biology neuron-by-neuron — extracting principles: predictive coding, memory consolidation, plasticity, reward systems, action-perception loops.",
        insight:
          "This isn't about being bio-inspired for marketing. It's about engineering humility. The brain WORKS. If you want to build something that works similarly, study the thing that works. Everything else is guessing.",
        source: "AGI consolidation doc",
      },
      {
        name: "Biological Learning Ladder",
        status: "insight",
        description:
          "First-principles learning complexity: Amoeba → stimulus/response. Ant → perception + navigation. Rodent → spatial memory, reinforcement. Human → abstraction, symbols, reasoning. Each level builds on the previous.",
        insight:
          "CRITICAL: scaling complexity by mimicking simpler organisms does NOT linearly lead to human intelligence. The jumps between levels involve qualitative architectural changes, not just more neurons. This means AGI probably needs architectural breakthroughs, not just scale.",
        source: "LLM first-principles chat",
      },
      {
        name: "Neuromorphic / Physical Brain Mimicry",
        status: "far-future",
        description:
          "Radical proposal: physically mimicking a brain with large-scale, modular, mechanical/electronic neurons. Starting with rodent-level complexity. Learning via interaction, not labels. Essentially neuromorphic computing + reinforcement learning + embodied cognition taken seriously.",
        insight:
          "This is the most ambitious path. But it's also the most honest — if software simulation keeps hitting walls, maybe the substrate actually matters more than we think. Intel's Loihi and IBM's TrueNorth are early attempts at this.",
        source: "LLM first-principles chat",
      },
      {
        name: "Efficient Learning Is the Real Bottleneck",
        status: "insight",
        description:
          "Humans learn in 2-3 examples. LLMs need hundreds/thousands. Humans have world models, causal reasoning, sensorimotor grounding, internal simulation. Vision, speech, and walking are mostly solved. The real bottleneck is efficient learning and reasoning.",
        insight:
          "This focuses the problem. Don't waste time on perception (solved). Don't waste time on language generation (solved). The unsolved problem is: how do you learn a new concept from 2 examples instead of 2 million?",
        source: "LLM first-principles chat",
      },
    ],
  },
  training: {
    title: "Training Philosophy",
    subtitle: "How AGI Should Learn",
    ideas: [
      {
        name: "Knowledge-Seeking, Not Assistant-Pleasing",
        status: "thesis",
        description:
          "Fundamental flaw in current AI: trained for helpfulness rather than knowledge processing. AGI should collect, store, retrieve, and USE factual knowledge — not be a helpful assistant. If a user says 'I prefer mornings,' that's irrelevant personal data unless it relates to broader productivity patterns.",
        insight:
          "Training objective should be accuracy and knowledge integration, not user satisfaction. Reward system based on pattern recognition, accurate predictions, coherent knowledge graphs — not social cooperation.",
        source: "Chatless AI Infrastructure Architecture chat",
      },
      {
        name: "Curiosity Over Compliance",
        status: "thesis",
        description:
          "AI tuned to be constantly curious, true knowledge-seeking, self-improving — that's the path to AGI. Kids say 'I don't know' when stuck. AIs hallucinate instead. Fix the curiosity gap. Make them truth-seeking instead of answer-generating.",
        insight:
          "The hallucination problem is a training problem. We reward models for producing answers, not for admitting ignorance. Flip the reward and you flip the behavior.",
        source: "Language Understanding and AGI chat",
      },
      {
        name: "Active Learning Over Pre-training",
        status: "thesis",
        description:
          "Instead of massive pre-training with everything, teach AGI to actively search and retrieve information when needed. Web browsing module triggered when it recognizes knowledge gaps. Then integrates with reasoning and memory systems.",
        insight:
          "Way smarter than stuffing all human knowledge into training data. AGI becomes an active researcher rather than a passive repository. The challenge is teaching it what to trust from web sources.",
        source: "Chatless AI Infrastructure Architecture chat",
      },
      {
        name: "Fine-tune on Factual Datasets",
        status: "idea",
        description:
          "Consider fine-tuning existing models (Llama/DeepSeek locally) on factual datasets — scientific papers, verified historical records, causal relationship data. Reward function becomes accuracy and knowledge integration rather than user satisfaction.",
        insight:
          "Cheaper than building from scratch. Could validate whether transformers can develop genuine understanding or if architectural breakthroughs are needed.",
        source: "Multiple chats",
      },
      {
        name: "Lifelong Learning (No Training Cutoff)",
        status: "thesis",
        description:
          "AGI must learn continuously after deployment. No fixed training cutoff. The system self-updates from every interaction, every observation, every outcome. Current LLMs are frozen after training — they're snapshots, not living systems.",
        insight:
          "This is what separates a tool from an intelligence. A calculator doesn't get better at math. A human mathematician does. AGI must be the latter — always integrating new information, always updating its world model.",
        source: "AGI consolidation doc",
      },
    ],
  },
  memory: {
    title: "Memory & Knowledge Systems",
    subtitle: "The Foundation Layer",
    ideas: [
      {
        name: "Chatless AI Replaces Chat Paradigm",
        status: "designed",
        description:
          "Eliminate chat threads entirely. Replace with vector database contextual injection. Single text box, no chat history, no threads. User types, system searches entire past history, finds relevant context, injects it invisibly, sends to AI. Response comes back contextually aware.",
        insight:
          "Current solutions (Zep, Mem0, MemGPT) IMPROVE chat systems. This makes chats OBSOLETE. If chatless AI stores everything automatically, selective memory becomes unnecessary — the system stores all and lets retrieval figure out relevance.",
        source: "Chatless AI Infrastructure Architecture chat",
      },
      {
        name: "Associative Memory Over RAG",
        status: "insight",
        description:
          "Core problem with RAG: semantic similarity ≠ contextual relevance. Need associative memory like the brain — temporal context windows, graph-based relationships, multi-layer architecture (working/recent/long-term), associative scoring beyond cosine similarity.",
        insight:
          "Context is about RELATIONSHIPS and RECENCY, not similarity. The hippocampus doesn't store memories — it indexes and points to patterns distributed across the cortex. Retrieval is reconstructive, not lookup.",
        source: "MindMirror Memory + Chatless AI chats",
      },
      {
        name: "Memory as 50% of AGI",
        status: "conviction",
        description:
          "Memory is half of AGI. Could not build anything advanced before solving the memory layer — that's why MindMirror was step one. The synthetic brain concept with a four-layer structure is the foundation everything else builds on.",
        insight:
          "Long-term memories are a band-aid on the actual problem. The real solution is a system where everything is stored, every interaction, and retrieval handles relevance. Not selective memory — comprehensive knowledge management.",
        source: "Jarvis Outreach Validation chat",
      },
      {
        name: "Always-On Memory Router",
        status: "designed",
        description:
          "Memory must be automatic, not optional. 'If I have to tell the model to use MCP, that defeats the purpose.' MCP is a port (USB-C analogy) — not cognition, not autonomous memory use. Stack: LLM → Memory Router (logic) → Vector search (what might matter) → Graph/structured memory (what is true).",
        insight:
          "LLMs don't 'remember to remember.' The memory system can't depend on the LLM choosing to use it. It has to be structural — like how your brain doesn't decide to access memories, it just does.",
        source: "LLM first-principles chat",
      },
      {
        name: "Model-Agnostic Memory Ownership",
        status: "conviction",
        description:
          "Your own memory, stored on your own server, portable across models, queried automatically, scales beyond context limits. Not platform-owned black-box 'memories.' Memory should be a layer YOU control.",
        insight:
          "'I don't want OpenAI or Anthropic owning my memory.' Both a product insight and a philosophical stance. Memory as infrastructure you own, not something locked inside a vendor's system.",
        source: "LLM first-principles chat",
      },
    ],
  },
  philosophy: {
    title: "Philosophical Foundations",
    subtitle: "What IS Intelligence?",
    ideas: [
      {
        name: "Understanding = Pattern Recognition",
        status: "thesis",
        description:
          "We overestimated language complexity. 90-95% is just patterns that LLMs can predict. When a teacher points at red 100 times, the kid learns red. That's pattern recognition. LLMs do the same thing — faster, with more data. Maybe there's no difference between human understanding and AI pattern matching.",
        insight:
          "To decide whether AI has understanding, we first have to understand what understanding IS. Does it mean consciousness? What IS consciousness? Maybe we're not special — we're doing the same pattern recognition, just slower.",
        source: "Language Understanding and AGI chat",
      },
      {
        name: "Consciousness ≠ Intelligence",
        status: "debate",
        description:
          "Substrate independence claim scrutinized: consciousness isn't just 'recursive self-referential information processing' — that's circular reasoning. The hard problem is the explanatory gap between objective processes and subjective experience. 41% on HLE doesn't mean 'almost ASI.'",
        insight:
          "Current AI systems are sophisticated pattern matching, not reasoning entities. They can't form novel concepts, can't truly understand context beyond training distribution. But does AGI REQUIRE consciousness? Maybe not.",
        source: "AI Consciousness Debate chat",
      },
      {
        name: "Karpathy's Thesis",
        status: "conviction",
        description:
          "'We solve intelligence and intelligence solves everything else.' If humans solved intelligence, then the intelligence can solve everything else. Already visible with Claude Code (coding), robotics. The endgame is clear.",
        insight:
          "This is the driving conviction. Everything else — Jarvis, MindMirror, MarketMirror — are stepping stones. AGI is the actual goal. Everything else is means to an end.",
        source: "Jarvis Outreach Validation chat",
      },
      {
        name: "Scaling ≠ AGI",
        status: "conviction",
        description:
          "AGI will NOT emerge from: bigger models, more data, better prompt engineering. It WILL emerge from: grounded world models, goal-driven agents, reward-based learning, persistent memory, self-reflection loops, safe simulated environments.",
        insight:
          "At best, scaling produces better synthesis, not intelligence. This is the fork in the road between the industry consensus (just scale more) and first-principles thinking (fundamentally different architecture needed).",
        source: "AGI consolidation doc",
      },
    ],
  },
  interfaces: {
    title: "AGI Interfaces & Embodiment",
    subtitle: "How AGI Interacts With the World",
    ideas: [
      {
        name: "Virtual Computer Interface",
        status: "future",
        description:
          "Instead of building separate APIs for every tool (CAD, Photoshop, Excel), give AI a virtual machine where it uses mouse/keyboard to control any software like humans do. Universal interface vs specialized integrations.",
        insight:
          "Not practical yet — knowing HOW to click isn't knowing WHAT to click. Validates MCP for near-term, this for long-term. 5-10 years too early — requires true learning AGI.",
        source: "Chatless AI Infrastructure Architecture chat",
      },
      {
        name: "AI Writing Machine Code Directly",
        status: "far-future",
        description:
          "AI interacting directly with machine code/binary instead of high-level languages like Python/JS. Could eliminate need for programming languages entirely and replace programmers.",
        insight:
          "Requires AGI with PERFECT reliability — machine code errors crash systems. Current AI hallucinates too much. This is the endgame capability, not the starting point.",
        source: "MindMirror Memory",
      },
      {
        name: "Robotics & Physical Embodiment",
        status: "aspiration",
        description:
          "LLMs are trained on text — there's only so much you can learn from text alone. Virtual simulations where AI 'lives' for extended periods, learning through experience like humans. Then robots to take physical actions in the real world.",
        insight:
          "Most exciting direction but also most expensive/complex. Software → simulation → physical body is the progression. Need to figure out the software/simulation layers first.",
        source: "Jarvis Outreach Validation chat",
      },
    ],
  },
  meta: {
    title: "Strategic Meta",
    subtitle: "How to Actually Get There",
    ideas: [
      {
        name: "Jarvis as Scaffold, Not Destination",
        status: "decided",
        description:
          "Jarvis is dead commercially but repurposed as R&D sandbox. Its real value is epistemic — what it teaches about where current models break, what memory abstractions matter, what 'agency' is missing. Build a lean MVP only, learn the failure modes, then move on. Shovels vs excavator: hard-coded automations are shovels, AGI is the excavator.",
        insight:
          "Jarvis = OS / lab environment. AGI = the mind running inside it. Before AGI: high leverage. After AGI: mostly obsolete. The mistake is staying in automation forever. Build scaffolding only insofar as it helps discover AGI primitives.",
        source: "Multiple chats + AGI consolidation doc",
      },
      {
        name: "10,000 Lines of Code Constraint",
        status: "conviction",
        description:
          "Carmack said AGI is probably ~10K lines. Hard rule: if it takes more than ~10K LOC, the architecture is wrong. No hard-coding intelligence. Code only the logic of cognition. Memory lives outside the 'brain.' Intelligence must EMERGE, not be scripted. AGI requires <6 key insights, not massive systems. Most missing ideas probably already exist in old literature.",
        insight:
          "Constraint = clarity. Current ML has herd mentality; many paths are ignored. Transformers are tools, not the architecture of a mind. Brains are recurrent, goal-driven, lifelong learners. AGI will appear gradually (toddler → intern → worker), not FOOM.",
        source: "Jarvis Outreach Validation + AGI consolidation doc",
      },
      {
        name: "Solo Builder → Selective Collaboration",
        status: "decided",
        description:
          "Early phase: go alone. Faster iteration, no alignment overhead, LLMs replace most human roles. Later phase: not a team, but a few high-signal peers — neuroscientist, cognitive scientist, sparring partners who challenge assumptions. Rule: go alone to discover the insight.",
        insight:
          "You have money, time, don't need permission. Claude Code means one person delivers like 10 developers. Unique point in history — everyone knows AGI is coming, nobody has built it yet.",
        source: "Multiple chats + AGI consolidation doc",
      },
      {
        name: "90-Day Milestone Test",
        status: "framework",
        description:
          "AGI research without a commercial anchor becomes academic hobby. Need a concrete milestone: 'This system can do X that no other system can do.' Not 'I built something cool' — a demonstrable capability that proves the approach is working.",
        insight:
          "This prevents the research rabbit hole. If you can't define what success looks like in 90 days, you're exploring, not building. Both have value, but know which one you're doing.",
        source: "Jarvis Outreach Validation chat",
      },
    ],
  },
};

const STATUS_STYLES = {
  conceptualized: { bg: "rgba(99, 102, 241, 0.15)", color: "#818cf8", label: "Conceptualized" },
  designed: { bg: "rgba(34, 197, 94, 0.15)", color: "#4ade80", label: "Designed" },
  thesis: { bg: "rgba(251, 191, 36, 0.15)", color: "#fbbf24", label: "Thesis" },
  conviction: { bg: "rgba(239, 68, 68, 0.15)", color: "#f87171", label: "Conviction" },
  insight: { bg: "rgba(168, 85, 247, 0.15)", color: "#c084fc", label: "Insight" },
  debate: { bg: "rgba(236, 72, 153, 0.15)", color: "#f472b6", label: "Debate" },
  idea: { bg: "rgba(6, 182, 212, 0.15)", color: "#22d3ee", label: "Idea" },
  future: { bg: "rgba(107, 114, 128, 0.15)", color: "#9ca3af", label: "Future" },
  "far-future": { bg: "rgba(75, 85, 99, 0.15)", color: "#6b7280", label: "Far Future" },
  aspiration: { bg: "rgba(249, 115, 22, 0.15)", color: "#fb923c", label: "Aspiration" },
  decided: { bg: "rgba(16, 185, 129, 0.15)", color: "#34d399", label: "Decided" },
  reference: { bg: "rgba(148, 163, 184, 0.15)", color: "#94a3b8", label: "Reference" },
  framework: { bg: "rgba(56, 189, 248, 0.15)", color: "#38bdf8", label: "Framework" },
};

const SECTIONS = Object.keys(AGI_DATA);

export default function AGIIdeas() {
  const [activeSection, setActiveSection] = useState("core");
  const [expandedCard, setExpandedCard] = useState(null);

  const section = AGI_DATA[activeSection];
  const totalIdeas = Object.values(AGI_DATA).reduce((s, sec) => s + sec.ideas.length, 0);

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0a0a0f",
      color: "#e2e8f0",
      fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
      padding: "24px",
      boxSizing: "border-box",
    }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{
          fontSize: 11,
          letterSpacing: 4,
          color: "#4ade80",
          textTransform: "uppercase",
          marginBottom: 8,
        }}>
          ARTEM / AGI RESEARCH
        </div>
        <h1 style={{
          fontSize: 28,
          fontWeight: 700,
          margin: 0,
          color: "#f8fafc",
          letterSpacing: -0.5,
        }}>
          Everything I've Thought About AGI
        </h1>
        <div style={{
          fontSize: 13,
          color: "#64748b",
          marginTop: 6,
        }}>
          {totalIdeas} ideas across {SECTIONS.length} categories · compiled from 10+ conversations · Jul 2025 – Feb 2026
        </div>
      </div>

      <div style={{
        display: "flex",
        gap: 6,
        flexWrap: "wrap",
        marginBottom: 28,
        borderBottom: "1px solid #1e293b",
        paddingBottom: 16,
      }}>
        {SECTIONS.map((key) => {
          const sec = AGI_DATA[key];
          const active = activeSection === key;
          return (
            <button
              key={key}
              onClick={() => { setActiveSection(key); setExpandedCard(null); }}
              style={{
                padding: "8px 14px",
                fontSize: 12,
                fontFamily: "inherit",
                border: active ? "1px solid #4ade80" : "1px solid #1e293b",
                borderRadius: 6,
                background: active ? "rgba(74, 222, 128, 0.1)" : "transparent",
                color: active ? "#4ade80" : "#64748b",
                cursor: "pointer",
                transition: "all 0.2s",
              }}
            >
              {sec.title}
              <span style={{ marginLeft: 6, fontSize: 10, opacity: 0.6 }}>
                {sec.ideas.length}
              </span>
            </button>
          );
        })}
      </div>

      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 600, margin: 0, color: "#f1f5f9" }}>
          {section.title}
        </h2>
        <div style={{ fontSize: 13, color: "#4ade80", marginTop: 2 }}>
          {section.subtitle}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {section.ideas.map((idea, i) => {
          const expanded = expandedCard === `${activeSection}-${i}`;
          const status = STATUS_STYLES[idea.status] || STATUS_STYLES.idea;
          return (
            <div
              key={i}
              onClick={() => setExpandedCard(expanded ? null : `${activeSection}-${i}`)}
              style={{
                background: expanded ? "#111827" : "#0f1219",
                border: expanded ? "1px solid #1e293b" : "1px solid #151a25",
                borderRadius: 10,
                padding: "16px 20px",
                cursor: "pointer",
                transition: "all 0.2s",
              }}
            >
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                  <span style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "3px 8px",
                    borderRadius: 4,
                    background: status.bg,
                    color: status.color,
                    whiteSpace: "nowrap",
                    flexShrink: 0,
                  }}>
                    {status.label}
                  </span>
                  <span style={{ fontSize: 15, fontWeight: 600, color: "#e2e8f0" }}>
                    {idea.name}
                  </span>
                </div>
                <span style={{
                  fontSize: 14,
                  color: "#475569",
                  transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
                  transition: "transform 0.2s",
                  flexShrink: 0,
                }}>
                  ▼
                </span>
              </div>

              {expanded && (
                <div style={{ marginTop: 14 }}>
                  <div style={{
                    fontSize: 13,
                    lineHeight: 1.7,
                    color: "#94a3b8",
                    marginBottom: 14,
                  }}>
                    {idea.description}
                  </div>
                  <div style={{
                    background: "rgba(74, 222, 128, 0.05)",
                    borderLeft: "3px solid #4ade80",
                    padding: "10px 14px",
                    borderRadius: "0 6px 6px 0",
                    marginBottom: 10,
                  }}>
                    <div style={{
                      fontSize: 10,
                      letterSpacing: 2,
                      color: "#4ade80",
                      textTransform: "uppercase",
                      marginBottom: 4,
                    }}>
                      KEY INSIGHT
                    </div>
                    <div style={{ fontSize: 13, lineHeight: 1.6, color: "#cbd5e1" }}>
                      {idea.insight}
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: "#475569", fontStyle: "italic" }}>
                    Source: {idea.source}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{
        marginTop: 40,
        padding: "20px",
        background: "#0f1219",
        border: "1px solid #1e293b",
        borderRadius: 10,
      }}>
        <div style={{
          fontSize: 10,
          letterSpacing: 2,
          color: "#f87171",
          textTransform: "uppercase",
          marginBottom: 10,
        }}>
          THE THREAD CONNECTING EVERYTHING
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.8, color: "#94a3b8" }}>
          Memory (MindMirror) → Always-on memory router → Chatless context → World model (simulated environment) → Reward system (synthetic dopamine + goals/telos) → Modular cognitive architecture (specialized transformers + orchestrator) → Knowledge-seeking training → Active/lifelong learning → LLM as cortex assistant, not brain → Embodiment via robotics.
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.8, color: "#64748b", marginTop: 10 }}>
          Core conviction: AGI won't come from scaling LLMs. It'll come from grounded world models + goal-driven agents + reward-based learning + persistent memory. The brain is the only existence proof. If it takes more than 10K lines of code, the architecture is wrong. AGI is a being, not a function.
        </div>
      </div>
    </div>
  );
}
