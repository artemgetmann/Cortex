# CORTEX — Demo, Strategy & Positioning

**For Artem only. Not needed for implementation. Contains demo narrative, competitive landscape, judging strategy, and positioning.**

---

# CORTEX: An AI Agent That Learns Software By Using It

## Hackathon Project Plan — "Built with Opus 4.6" (Feb 10-16, 2026)

**Builder:** Artem Getman — Solo founder, 24, Dubai  
**Background:** 9 months building AI memory systems (MindMirror), music production (FL Studio), Photoshop experience  
**Credits:** $500 Opus 4.6 API credits  
**Prize:** $100K grand prize pool

---

## 1. THE THESIS

**"AI agents can do anything once, but they can't learn. I built one that can."**

Correction: they can't learn — or struggle to learn — beyond their training data.

Most AI agents are stateless. They execute tasks, then forget everything. Every new session starts from zero. Cortex is different: it explores software through trial and error, stores what it learns as persistent procedural memories and skills, and measurably improves with each session. No fine-tuning. No training data. Just exploration and memory.

**Key framing (important for judges):** We do NOT claim the agent "has never seen FL Studio." Opus 4.6 has seen FL Studio docs in training. Instead, the claim is: **"A stateless agent vs a stateful agent — same model, same software, but one remembers and one doesn't."** That's defensible and more interesting.

### Why This Matters

The gap between "AI can use a computer" and "AI can learn to use a computer" is the gap between a tool and an intelligence. Current computer-use agents (Claude's own, OpenAI Operator, Agent S3) can follow instructions and navigate familiar patterns. But give them software they've never seen, and they start from scratch every time. Cortex doesn't.

### What Makes This Novel

An AI agent that uses **vision-based computer use** (screenshots + mouse/keyboard) to learn and operate professional creative software, with **persistent procedural memory that creates human-readable skills and measurably improves across sessions**. Related work exists (Voyager for Minecraft skill libraries, Reflexion for learning from failures, Microsoft UFO for GUI agents), but the specific combination of: desktop computer use + procedural skill generation + visual references + demonstrated measurable improvement on a real pro creative app — that's the gap.

---


---

## 5. DEMO FLOW (3 Minutes)

### Narrative: "Stateless AI vs Stateful AI — same model, same task, but one remembers."

**Minute 0:00-1:00 — Session 1: The Stateless Run (MONTAGE — sped up 4x)**

Voiceover: "This is Cortex running Claude Opus 4.6 with computer use. It has a hand-written skill guide for FL Studio, but no memories of its own. Watch it fumble."

- Show: FL Studio Desktop with agent's internal monologue overlay (big text showing what it's thinking: "I see the Channel Rack. Looking for the Kick row...")
- **Sped up 4x with voiceover** — watching an agent fail at full speed is boring
- Agent makes mistakes — wrong row clicks, confused by similar buttons
- Slow down to 1x for the KEY MOMENT: agent writes its first lesson to the memory log
- Show: memory entry appearing ("Kick row is at Y=267, not Y=287. Clap is directly below.")
- End of session: agent runs post-mortem, updates skill doc
- **Show the skill diff:** split screen — original skill on left, updated skill on right, new lines highlighted
- **Session 1 stats on screen:** "Actions: 42 | Mistakes: 8 | Time: 4:12"

**Minute 1:00-2:00 — Session 2: The Stateful Run (real-time)**

"Same model. Clean context. But now it has its memories and updated skills."

- Show: agent loading skill doc + lessons-learned before starting
- Internal monologue: "Loading 12 memories from Session 1. Key lesson: Kick row Y=267, verify before clicking."
- Agent navigates FL Studio immediately — goes straight to Channel Rack, correct row
- Avoids ALL previous mistakes
- Completes kick pattern cleanly
- **Play the result — judges hear the beat**
- Wave Candy visualizer shows activity (visual confirmation of audio)
- **Session 2 stats on screen:** "Actions: 11 | Mistakes: 0 | Time: 0:47"
- **Side-by-side comparison:** Session 1 stats vs Session 2 stats

**Minute 2:00-3:00 — Session 3: Generalization (real-time)**

"Now the real test. A task it's never done — but structurally different from kick placement."

Task: **Change the tempo to 140 BPM and switch the pattern length** (NOT just "add hi-hat" which is the same operation on a different row).

- Agent retrieves navigation memories (knows where things are) but encounters new UI targets
- Internal monologue: "I know the Channel Rack. But tempo control is in the Transport bar — I learned that's at the top. Let me look..."
- Agent adapts stored knowledge to novel situation — proves transfer, not just repetition
- Generates new skill doc: `tempo-and-pattern.md`
- **Session 3 stats:** "Actions: 15 | Mistakes: 1 | Time: 1:02"

**Closing:** "Every existing AI integration for music production uses APIs or chatbots. Cortex uses its eyes, its hands, and its memory. Session 1: 42 actions, 8 mistakes. Session 2: 11 actions, zero mistakes. That's not automation — that's learning."

### Visual Setup for Demo

```
┌──────────────────────────────────────────────────┐
│  ┌───────────────────┐ ┌──────────────────────┐  │
│  │                   │ │ INTERNAL MONOLOGUE   │  │
│  │   FL STUDIO       │ │                      │  │
│  │   DESKTOP         │ │ "Looking for Kick    │  │
│  │   (1024x768)      │ │  channel. Last time  │  │
│  │                   │ │  I clicked Y=287 and │  │
│  │   [Wave Candy     │ │  hit Clap. Aiming    │  │
│  │    visualizer     │ │  for Y=267..."       │  │
│  │    bottom-right]  │ │                      │  │
│  └───────────────────┘ └──────────────────────┘  │
│                                                   │
│  ┌──────────────────────────────────────────────┐│
│  │ SESSION 2  |  Actions: 11  |  Mistakes: 0   ││
│  │ Time: 0:47 |  Skills: 3    |  Memories: 14  ││
│  └──────────────────────────────────────────────┘│
└──────────────────────────────────────────────────┘
```

### Demo Enhancements (Low-Effort, High-Impact)

1. **Metrics overlay:** Live counters for Actions, Mistakes, Time. The learning delta IS the demo.
2. **Internal monologue:** Big text panel showing agent's reasoning. "Jarvis UI" feel. Can be a simple Streamlit app or transparent overlay reading from a log file.
3. **Skill diff moment:** Before/after of the skill markdown, highlighted changes. 2 seconds, massive impact.
4. **Audio payoff:** Judges hear the beat. Wave Candy shows visual confirmation.

---


---

## 6. JUDGING CRITERIA ALIGNMENT

| Criteria | Weight | How Cortex Scores |
|----------|--------|-------------------|
| **Impact** | 25% | A self-teaching agent is a step toward AGI. If it can learn FL Studio, it can learn any software. The pattern is universal. Related to Voyager/Reflexion but on real desktop software, not games. |
| **Opus 4.6 Use** | 25% | Uses Opus 4.6's computer use (72.7% OSWorld — their best), adaptive thinking, 1M context, and context compaction. Desktop computer use is harder than browser automation. Can't be done with a lesser model. |
| **Depth & Execution** | 20% | Skills-as-folders memory architecture, post-action verification loop, serial post-mortem for skill generation, metrics tracking, visual audio feedback via Wave Candy. Simple but well-engineered. |
| **Demo** | 30% | Three-act narrative with quantified learning (42→11 actions, 8→0 mistakes). Internal monologue overlay. Skill diff visualization. Audio payoff. Non-technical judges get it immediately. |

---

## 7. COMPETITIVE LANDSCAPE

### What Already Exists for FL Studio AI

| Project | Approach | Limitation |
|---------|----------|------------|
| veenastudio/flstudio-mcp | MIDI API messages to piano roll | Can only write notes. No mixer, effects, VSTs, playlist, automation. |
| karl-andres/fl-studio-mcp | MIDI-based approach | Same severe limitations as above. |
| ohhalim/flstudio-mcp | MIDI workaround | Same. |
| Gopher (FL Studio 2025) | Text chatbot trained on FL manual | Provides advice only. Does NOT control the DAW. |
| Loop Starter (FL Studio 2025) | Generates genre-based loop stacks | Black-box feature, not an agent. |
| Melosurf (Ableton only) | Voice-controlled Max for Live device | Uses Ableton's API, not vision. Not public. |
| MIDI Agent (VST plugin) | ChatGPT/Claude generate MIDI text | Generates MIDI data, doesn't control the DAW UI. |

**Key insight:** All existing integrations use the FL Studio scripting API or MIDI protocol. The scripting API is severely limited — cannot load VST plugins, cannot create new patterns programmatically, cannot control the full UI. **Vision-based computer use bypasses all API limitations because it interacts with the same GUI a human would.**

### Academic / Research Competitors (Know These for Judges)

| Project | What It Does | How Cortex Differs |
|---------|-------------|-------------------|
| **Voyager** (MineDojo) | LLM agent that builds skill library in Minecraft through exploration | Game environment, not real desktop software. Cortex applies this to professional creative tools. |
| **Cradle** (BAAI, ICML 2025) | Skill curation + self-reflection for Red Dead Redemption 2 | Game environment. Research prototype. Cortex is on real productivity software. |
| **CUA-Skill** (Microsoft, Jan 2026) | Structured skills for computer-using agents + retrieval + failure recovery | Closest academic analog. Cortex adds FL Studio domain expertise + measurable learning demo. |
| **Reflexion** | Learning from failures by writing memory/reflections | General framework. Cortex implements this concretely on desktop computer use. |
| **MGA** (Memory-Driven GUI Agent, 2025) | Persistent memory for GUI agents | Academic paper. Similar concept but not applied to creative software. |
| **Agent S3** (Simular AI) | 72.6% on OSWorld, strong computer use | Stateless. No persistent memory across sessions. |

**Positioning for judges:** "Inspired by Voyager's skill library approach and Cradle's procedural memory in game environments, Cortex applies these principles to real professional creative software — with measurable before/after improvement demonstrated live."

**What's genuinely novel:** Computer-use agent + procedural skill generation + Hint Bar verification + measurable learning on a real pro desktop app. The combination is new, even if individual components have precedent.

### What Already Exists for Photoshop AI (Why We're NOT Doing This)

- Adobe's own agentic AI assistant (Oct 2025, private beta)
- ChatGPT can use Photoshop via API integration (Dec 2025)
- Adobe MCP server for layer renaming and manipulation
- Adobe Project Moonlight — cross-app orchestration agent
- Multiple Photoshop AI features built-in (Generative Fill, Distraction Removal, etc.)

**Verdict:** Photoshop AI is a crowded space. Judges would not see this as novel.

---


---

## 8. RISK ASSESSMENT

### What Could Go Wrong

| Risk | Severity | Mitigation |
|------|----------|------------|
| Computer use misclicks on FL Studio's dense UI | High | Use 1024x768 window size (larger elements). Use `zoom` action for precision. Fall back to keyboard shortcuts. |
| Screenshot resolution too low to distinguish elements | Medium | The `zoom` action (new in computer_20251124) inspects regions at full resolution. |
| Agent loop latency makes demo feel slow | Medium | Pre-record demo sections. Speed up replay for time-lapse effect. |
| FL Studio Desktop has macOS-specific issues (rendering, input blocking) | Medium | Gate test on Day 1 catches this. Fall back to simpler creative tool if needed. |
| Agent doesn't meaningfully improve between sessions | Critical | Test this on Day 2-3. If improvement isn't visible, the project doesn't work. Pivot immediately. |
| $500 in API credits runs out | Low | Math shows ~5,000 actions possible. Not a real constraint. |
| 6 days isn't enough solo | Medium | Strict scope management. Core loop first, enhancements later. |

### Kill Criteria (When to Pivot)

- **Day 1 end:** If computer use can't reliably click FL Studio Desktop UI elements → pivot to simpler target app
- **Day 3 end:** If agent doesn't show measurable improvement between sessions → pivot to pure memory demo without computer use
- **Day 4 end:** If demo narrative isn't coming together → simplify to whatever works

---


---

## 12. POSITIONING & NARRATIVE

### For Judges (Technical Audience)

"Most computer-use agents are stateless — they can navigate familiar patterns but can't accumulate knowledge across sessions. Cortex introduces persistent procedural memory to desktop computer use. Same model, same task — but a stateful agent completes it in 11 actions with zero mistakes, versus 42 actions and 8 mistakes without memory. It uses Opus 4.6's computer use, adaptive thinking, and 1M context to explore real professional software, store what it learns as human-readable skills, and measurably improve with each session."

### For General Audience

"Imagine sitting down at software you've never used before. You'd fumble around, make mistakes, and eventually figure it out. Next time you opened it, you'd be faster. Cortex does the same thing — but it's an AI. Watch it go from 42 actions and 8 mistakes to 11 actions and zero mistakes, just by remembering what it learned."

### One-Liner

**"AI agents can do anything once, but they can't learn. I built one that can — and I can prove it with numbers."**

### Why This Is a Step Toward AGI

The ability to learn from experience — not just training data — is a fundamental capability gap in current AI. Fine-tuning requires datasets and compute. In-context learning resets every session. Cortex demonstrates that an AI agent can accumulate procedural knowledge through autonomous exploration, persist that knowledge across sessions, and generalize to novel tasks. That's learning. And it's running on today's models, today.

---


---

## APPENDIX B: Backup Pivot Options

If FL Studio doesn't work out:

1. **Simpler web-based creative tool** — e.g., Canva, Figma (browser-based, 2D UI, visual output)
2. **Terminal-based tool learning** — agent learns to use an unfamiliar CLI tool (less visual but more reliable)
3. **Pure memory demo** — drop computer use, focus on demonstrating the memory architecture with a chatbot that never forgets (weaker but deliverable)

## APPENDIX C: The Name

Options considered:
- **Cortex** — brain region for learning and memory ✅ (current pick)
- **Engram** — neuroscience term for a memory trace
- **Synapse** — connection between neurons (might be taken)

Don't spend more than 5 minutes on this. The project matters more than the name.

