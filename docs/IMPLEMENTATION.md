# CORTEX — Implementation Spec

**This is the primary technical document. Contains everything needed to build the system.**

Related docs:
- `FL-STUDIO-REFERENCE.md` — FL Studio UI guide, keyboard shortcuts, domain knowledge
- `SECOND-PRIORITY.md` — Cut features, Docker backup, stretch goals
- `DEMO-AND-STRATEGY.md` — Demo narrative, competitive landscape, positioning (not needed for implementation)

---

## 3. ARCHITECTURE

### Two Components (Keep It Simple)

```
┌─────────────────────────────────────────────────────┐
│                    CORTEX SYSTEM                     │
│                                                      │
│  ┌──────────────┐    ┌──────────────┐               │
│  │  COMPONENT 1 │    │  COMPONENT 2 │               │
│  │  Explorer     │◄──►│  Memory      │               │
│  │  Agent        │    │  (Skills as  │               │
│  │  (Opus 4.6)  │    │   folders)   │               │
│  └──────┬───────┘    └──────────────┘               │
│         │                                            │
│         ▼                                            │
│  ┌──────────────┐    ┌──────────────┐               │
│  │  Computer    │    │  Batch       │               │
│  │  Use API     │    │  Consolidate │               │
│  │  (screenshot │    │  (between    │               │
│  │   + actions) │    │   sessions)  │               │
│  └──────────────┘    └──────────────┘               │
└─────────────────────────────────────────────────────┘
```

### Component 1: The Explorer Agent (Opus 4.6)

**Role:** The main agent that interacts with FL Studio via computer use.

**Implementation:** Port Anthropic's reference implementation (`loop.py` + `computer.py`) to macOS. Replace `xdotool` with `pyautogui`. Keep their battle-tested loop logic and tool parsing. Source: https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo

**API setup (raw Anthropic API, NOT Agents SDK):**
```python
import anthropic
client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-opus-4-6-20250219",
    max_tokens=4096,
    tools=[{
        "type": "computer_20251124",
        "name": "computer",
        "display_width_px": 1024,
        "display_height_px": 768,
        "enable_zoom": True
    }],
    messages=[...],
    betas=["computer-use-2025-11-24"]
)
```

**System prompt core directives:**
- "You are controlling FL Studio Desktop on macOS via screenshots and mouse/keyboard."
- "KEYBOARD FIRST: Always prefer keyboard shortcuts over clicking. F6=Channel Rack, F7=Piano Roll, Space=Play/Stop, Ctrl+Z=Undo, Escape=Close dialogs."
- "HINT BAR VERIFICATION: Before clicking any UI element, move the mouse to the target and read the Hint Bar at the bottom of FL Studio. Verify it matches your intended target. Only click after Hint Bar confirmation."
- "ZOOM FOR PRECISION: When UI elements are small or dense, use the zoom action to inspect the region at full resolution before clicking."
- "SEMANTIC MEMORY: When recording what you learned, describe targets semantically ('Kick row, first row in Channel Rack') not by raw coordinates. Coordinates change if the window moves."
- "After every action, take a screenshot and evaluate: did the UI change as expected? If not, Ctrl+Z and try again."
- "When you succeed at something, note exactly what worked and why."
- "When you fail, note what went wrong and what you'll try differently."

**Computer Use tool details:**
- Tool version: `computer_20251124` (for Opus 4.6)
- Beta header: `"computer-use-2025-11-24"`
- Available actions: screenshot, left_click, right_click, double_click, type, key, hold_key, mouse_move, left_click_drag, scroll, wait, zoom
- Resolution: 1024x768 (XGA) — force display to this, eliminates coordinate scaling
- `zoom` action: inspects screen regions at full resolution. Enable with `enable_zoom: true`. Critical for FL Studio's dense UI.
- `wait` action: pause between actions (use instead of `time.sleep` in code)

**Engineered learning contrast (CRITICAL FOR DEMO):**
- **Session 1:** Load ZERO skill files. Only base system prompt + keyboard shortcut reference. Let the agent fumble. This produces authentic mistakes and memories.
- **Session 2:** Load hand-crafted/updated skill docs + curated failure lessons from Session 1. Be prescriptive. The skill docs should be explicit enough that ANY competent model follows them.
- This contrast is what makes "learning" visible and measurable.

**Window focus management (before every action):**
```python
import subprocess
def activate_fl_studio():
    subprocess.run(["osascript", "-e", 'tell application "FL Studio" to activate'])
```

**Emergency recovery (on unexpected state):**
```python
def emergency_reset():
    activate_fl_studio()
    pyautogui.press('escape', presses=5)   # Close any dialogs/menus
    pyautogui.hotkey('ctrl', 'z', presses=10)  # Undo recent actions
    pyautogui.press('f6')                   # Reopen Channel Rack
    time.sleep(0.5)
```

**Agentic loop (ported from reference implementation):**
```
1. Activate FL Studio window (osascript)
2. Take screenshot
3. Load relevant skills + lessons into context (smart injection, <50k tokens)
4. Send screenshot + context to Opus API
5. Parse response for tool_use blocks
6. For each action:
   a. If click: move mouse first, read Hint Bar (verify target), then click
   b. If key: execute keypress
   c. Wait for UI to settle (post-action verification loop)
   d. Take screenshot, evaluate result
   e. Log action + result to session JSONL
7. If task complete → run post-mortem (update skills, generate lessons)
8. If stuck (same mistake 3x) → emergency_reset() + try keyboard alternative
```

### Component 2: The Memory System (Skills-as-Folders)

**Role:** Persistent knowledge base the agent builds about FL Studio over time.

**Implementation: Plain files on disk. No database. No Mem0. No embeddings.**

```
skills/
├── fl-studio/
│   ├── navigation.md          ← How to get around the UI
│   ├── channel-rack.md        ← Step sequencer basics
│   ├── piano-roll.md          ← Note editing
│   ├── drum-pattern.md        ← First skill (hand-written by Artem)
│   ├── hi-hat-pattern.md      ← Second skill (agent-generated)
│   └── screenshots/
│       ├── channel-rack-overview.png
│       ├── kick-step-buttons.png
│       └── piano-roll-note-placement.png
memories/
├── session-001.jsonl          ← Raw observations, failures, successes
├── session-002.jsonl          ← Agent improves with these
└── lessons-learned.md         ← Consolidated insights
```

**Why this over a database:** Opus 4.6 has 1M token context. You can load entire skill files + recent memories directly into the prompt. No retrieval pipeline, no embedding model, no vector search. Just read the files and stuff them into context. For a hackathon with <50 skill files, this is optimal.

### Three-Step Priority Order

**Step 1 (Day 1-2): Hand-written skill + control FL Studio**
- Artem writes the first skill document: `drum-pattern.md` with screenshots
- Agent receives this skill as context + screenshots
- Test: can it follow the instructions and control FL Studio?
- This proves: computer use works, skill format works, FL Studio is controllable
- **NO memory system needed yet. Just a hand-written guide.**

**Step 2 (Day 2-3): Text memories for learning from mistakes**
- Agent logs observations/failures/successes as JSONL entries per session
- Between sessions, agent (or Haiku monitor) consolidates lessons into text
- New sessions load: skill docs + past lessons → agent avoids repeated mistakes
- Agent generates NEW skill docs from experience (e.g., hi-hat after learning kick)
- **This is where "learning" becomes visible. Session 2 is faster than Session 1.**

**Step 3 (Day 4+, stretch goal): Image memories**
- Skills get annotated screenshots at decision points
- Agent stores "what failure looks like" vs "what success looks like" as images
- Memory entries include before/after screenshots
- Makes skills richer and more human-like (we memorize visually too)
- **Only do this if Steps 1-2 work solidly.**

**Skill document format (hand-written example for Step 1):**
```markdown
# Skill: Create a Kick Drum Pattern

## Prerequisites
- FL Studio is open
- Channel Rack is visible (if not, press F6)

## Steps
1. In the Channel Rack, locate the "Kick" channel (usually first row)
2. Click on step buttons 1, 5, 9, 13 for a basic four-on-the-floor pattern
   - Screenshot: screenshots/kick-step-buttons.png
   - Each button represents a 16th note. Buttons 1,5,9,13 = quarter notes.
3. Press Space to play and verify

## Keyboard Shortcuts
- F6: Open Channel Rack
- Space: Play/Stop
- Ctrl+Z: Undo last action

## Common Mistakes
- Clicking the wrong channel row (Kick vs Clap vs Hat)
- Not having the correct pattern selected in the Pattern selector (top left)
- Volume muted — check the green light next to the channel name

## Success Rate: [updated by agent]
## Last Updated: [timestamp]
```

**Memory entry format (Step 2):**
```jsonl
{"session": 1, "step": 3, "task": "place kick on beat 1", "action": "click(412, 287)", "success": false, "lesson": "Clicked Clap row instead of Kick — rows are only 20px apart, need to be more precise with Y coordinate"}
{"session": 1, "step": 4, "task": "place kick on beat 1", "action": "click(412, 267)", "success": true, "lesson": "Correct Y coordinate for Kick row is ~267, not 287"}
```

### ~~Component 3: Background Monitor~~ — CUT

**Status: ELIMINATED.** Both external reviews flagged this as unnecessary complexity. Async coordination between two agents modifying the same filesystem is a race condition nightmare on a 6-day timeline.

**Full spec preserved in:** `cortex-second-priority.md` → Section 1 (includes implementation code, architecture diagram, all 4 functions). Revisit if ahead of schedule on Day 4+.

**Replacement: Serial Post-Mortem.** At the end of each session, the Explorer agent itself (or a single Opus call) reviews its session log and updates skill files. Same outcome, zero async complexity.

```
End of Session 1:
→ Agent reviews session-001.jsonl
→ Updates drum-pattern.md with corrections ("Kick row Y=267, not 287")
→ Generates lessons-learned.md ("Do/Don't" checklist, max 20 lines)
→ Ready for Session 2
```

### ~~Research Sub-Agents / BrightData~~ — CUT

**Status: ELIMINATED.** Getting scraping + parsing reliable is a project in itself.

**Full spec preserved in:** `cortex-second-priority.md` → Section 2 (includes BrightData MCP config, 6-step example flow, implementation code). Revisit if agent gets stuck on undocumented UI elements.

**Replacement:** Pre-load a `library/` folder with relevant FL Studio manual pages (PDF exports or markdown). If the agent gets stuck, it reads the docs — no external scraping needed. Artem knows the software and can curate the right reference material in 30 minutes.

### Core Loop Hardening (CRITICAL — from external reviews)

**1. Reset-to-Known-Good State (start of every session):**
```python
def reset_fl_studio():
    """Execute before every session to ensure clean state."""
    pyautogui.hotkey('ctrl', 'z', presses=20)  # Undo everything
    pyautogui.press('escape', presses=5)         # Close any popups/menus
    pyautogui.press('f6')                         # Open Channel Rack
    pyautogui.press('space')                      # Stop transport if playing
    time.sleep(0.5)
    # Verify: take screenshot, confirm Channel Rack is visible
```
Without this, the agent inherits unknown UI state and dies immediately.

**2. Post-Action Verification (NOT blind sleep):**
```python
def wait_for_state_change(timeout=5.0):
    """Screenshot every 500ms, wait until UI stops changing."""
    prev = pyautogui.screenshot()
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
        curr = pyautogui.screenshot()
        if images_are_similar(prev, curr, threshold=0.98):
            return curr  # UI has settled
        prev = curr
    return curr  # Timeout — return whatever we have

def execute_and_verify(action, expected_description):
    """Execute action, wait for UI to settle, verify result."""
    execute_action(action)
    screenshot = wait_for_state_change()
    # Send to Opus: "Did this action achieve: {expected_description}?"
    # If no → retry or try alternative approach
    return screenshot
```
This prevents the agent from clicking while FL Studio is still loading a plugin or rendering.

**3. "Oh Shit" Button (keyboard interrupt for demo recording):**
```python
import keyboard  # or pynput

PAUSED = False
def toggle_pause():
    global PAUSED
    PAUSED = not PAUSED
    print(f"{'⏸️ PAUSED' if PAUSED else '▶️ RESUMED'}")

keyboard.add_hotkey('f12', toggle_pause)

# In the agent loop:
while task_not_complete:
    while PAUSED:
        time.sleep(0.1)  # Wait until unpaused
    # ... normal agent loop
```
Press F12 to pause. Fix the state manually. Press F12 to resume. Saves $5+ runs from one misclick.

**4. Session Metrics Tracking:**
```python
session_metrics = {
    "session_id": 1,
    "total_actions": 0,
    "mistakes": 0,
    "time_start": time.time(),
    "time_to_first_success": None,
    "actions_log": []
}
```
These metrics are the demo's secret weapon. "Session 1: 42 actions, 8 mistakes, 4 minutes. Session 2: 12 actions, 1 mistake, 45 seconds." Judges see learning quantified.

### Simplified First Version (Day 1 approach)

For the initial gate test, skip Components 2 and 3. Just get Component 1 working:

1. Manually create a `skills/fl-studio/drum-pattern.md` file with:
   - Screenshots of FL Studio's UI (Artem knows the software, take them yourself)
   - Step-by-step instructions for placing a kick drum pattern
   - Keyboard shortcuts as fallback for tricky clicks
2. Give this skill to Opus 4.6 as context alongside the screenshot
3. Test: can Opus screenshot FL Studio, identify UI elements, and click correctly?
4. If YES → proceed to Step 2 (text memories for learning)
5. If NO → debug (resolution? coordinate scaling? UI too dense?) or pivot

---


---

## 4. COMPUTER USE SETUP

### CRITICAL: How Computer Use SDK Actually Works

The Computer Use SDK is **NOT** a self-contained agent that controls your computer. It's a pure API:

1. **YOUR code** takes a screenshot and sends it to the Claude API
2. Claude analyzes the screenshot and returns an action: `click at (500, 300)` or `type "hello"` or `key "ctrl+s"`
3. **YOUR code** executes that action on your machine (using pyautogui, xdotool, AppleScript, etc.)
4. **YOUR code** takes another screenshot and sends it back
5. Repeat until task complete

**The SDK provides the brain. You provide the hands.** On Linux (reference implementation), action execution uses `xdotool`. On macOS, use `pyautogui` or `cliclick`.

### Environment: Run Directly on Mac (Primary Approach)

| Option | Verdict | Reason |
|--------|---------|--------|
| **Direct on Mac + FL Studio Desktop** | ✅ PRIMARY | Zero setup for FL Studio. Full plugins (Serum, FabFilter, Sausage Fattener). Real audio output. Most impressive for demo. |
| **Docker + FL Studio Web** | ❌ Skip | Web version is a toy — no third-party VSTs. Browser control is less impressive than desktop control. Claude Code already does browser automation. |
| **Docker + Wine + FL Studio** | ❌ Skip | Wine is finicky, wastes time on setup instead of building. |
| **Windows VM** | ❌ Skip | Unnecessary complexity. |

### Mac Setup Requirements

```
Your Mac
├── FL Studio (already installed with plugins + Wave Candy on Master)
├── Python agent loop script
│   ├── Anthropic API client (Opus 4.6 + Computer Use beta)
│   ├── pyautogui (screenshot capture + mouse/keyboard control)
│   ├── Skills folder (markdown + screenshots)
│   ├── Session logs (JSONL)
│   ├── Post-action verification loop
│   └── Metrics tracker + pause/resume (F12)
├── Display forced to 1024x768 (eliminates coordinate math)
├── Screen recording software (OBS or QuickTime, with audio)
└── Wave Candy docked on Master channel (visual audio feedback)
```

### Display Resolution: Force 1024x768 (IMPORTANT)

**Do NOT do coordinate scaling math.** Instead, force the display to 1024x768:
- Use **BetterDisplay** or **SwitchResX** to set an external monitor to 1024x768
- Or resize FL Studio window to exactly 1024x768 and capture only that region
- Anthropic docs recommend 1024x768 for optimal performance
- This gives 1:1 mapping: Claude's coordinates = pyautogui's coordinates = actual pixels
- FL Studio UI elements are bigger at this resolution → fewer misclicks

If using a second macOS desktop: keep FL Studio as the **focused, visible app on the active Space** during agent runs. macOS Spaces may not screenshot correctly for background spaces. Don't fight the OS — just let the agent have the screen.

### macOS Accessibility Permissions (CRITICAL)

macOS blocks programmatic mouse/keyboard control by default. You MUST grant permissions:

1. Go to **System Settings → Privacy & Security → Accessibility**
2. Add your terminal app (Terminal, iTerm2, Alacritty) to the allowed list
3. If running via Python directly, add Python to the list
4. Without this, `pyautogui` clicks will be **silently ignored** — no error, just nothing happens

### Gate Test (Do This FIRST — 5 Minutes)

```bash
# Install pyautogui
pip install pyautogui

# Open FL Studio on your Mac, then run this:
python3 -c "
import pyautogui
import time

# Take screenshot
pyautogui.screenshot('fl_test.png')
print(f'Screenshot saved. Screen size: {pyautogui.size()}')

# Wait 3 seconds (switch to FL Studio window)
print('Switch to FL Studio now... clicking in 3 seconds')
time.sleep(3)

# Click somewhere in FL Studio
pyautogui.click(500, 400)
print('Click executed — did FL Studio respond?')
"
```

**If screenshot captures FL Studio correctly AND the click registers → project is a go.**
**If macOS blocks the click → grant Accessibility permissions and retry.**
**If FL Studio ignores programmatic input entirely → investigate AppleScript or switch approach.**

### Coordinate Scaling — ELIMINATED

If you force the display to 1024x768 as described above, there is no scaling math needed. Claude returns coordinates at 1024x768, pyautogui clicks at 1024x768. Done.

If for some reason you can't force 1024x768, keep this fallback code:

```python
import math

def get_scale_factor(width, height):
    long_edge = max(width, height)
    total_pixels = width * height
    long_edge_scale = 1568 / long_edge
    total_pixels_scale = math.sqrt(1_150_000 / total_pixels)
    return min(1.0, long_edge_scale, total_pixels_scale)

def execute_click(x, y, scale):
    pyautogui.click(int(x / scale), int(y / scale))
```

### Safety & Environment Setup

- **Run in a clean macOS user account** (or at minimum, close all sensitive apps). Computer use can click unexpected things.
- **Disable notifications** (Do Not Disturb) — a notification banner over FL Studio will confuse the agent.
- **Close all other windows** — agent should only see FL Studio.
- **Wave Candy** docked on Master channel, Detached + Always on Top, in bottom-right corner.

### Pricing Reality Check

**Opus 4.6:** $5/M input, $25/M output (67% cheaper than Opus 4.1)

**Per computer-use action cost:**
- Screenshot: ~1,500 tokens (image)
- System prompt + tools: ~5,000 tokens (cached after first call → $0.50/M)
- Output reasoning + action: ~1,000-3,000 tokens
- **Estimated: $0.05-0.10 per action**

**Budget math:**
- $500 ÷ $0.10 = ~5,000 actions
- Full learning session: ~50-100 actions
- **~50-100 complete sessions possible**
- With prompt caching (90% savings on repeated context): even more

**Verdict: $500 is NOT a constraint.** Even with wasteful development, you won't run out.

### Key Opus 4.6 Capabilities (Relevant to Project)

- **OSWorld benchmark: 72.7%** — best computer-using model, ahead of GPT-5.2 and Gemini 3 Pro
- **Terminal-Bench 2.0: 65.4%** — strong agentic coding
- **1M token context window** (beta) — can hold massive skill documents
- **Context compaction** — auto-summarizes when approaching limits
- **Adaptive thinking** — adjusts reasoning depth based on task complexity
- **Agent teams / subagents** — native parallel agent support
- **128K output tokens** — can generate comprehensive skill documents in one pass

---

---

## 9. DEVELOPMENT PLAN

### Day 1 (Feb 10) — Gate Test + Agent Loop Skeleton ✅ (GATE TEST PASSED)

**Gate test: PASSED** — pyautogui screenshots, clicks, and keyboard work with FL Studio Desktop on Mac.

**Remaining Day 1 tasks:**
- Clone Anthropic reference implementation: `git clone https://github.com/anthropics/anthropic-quickstarts.git`
- Port `loop.py` + `computer.py` to macOS (replace xdotool → pyautogui)
- Force display to 1024x768 (BetterDisplay or SwitchResX)
- If Retina can't be forced to 1024x768, implement 3-layer coordinate scaling (physical → API → logical) as fallback
- Test: send screenshot to Opus API, get back "describe what you see" — verify it understands FL Studio UI
- Test: Opus says "click Channel Rack tab" → pyautogui clicks → verify correct target
- Set up project structure (see below)
- Hand-write first skill doc: `skills/fl-studio/drum-pattern.md`

**Project file structure:**
```
Cortex/
├── agent.py                    # Core agentic loop (ported from reference impl)
├── computer_use.py             # pyautogui wrapper + coordinate scaling + focus management
├── memory.py                   # Read/write skills and session logs (file-based)
├── consolidate.py              # Between-session memory consolidation script
├── config.py                   # API keys, screen dimensions, paths
├── requirements.txt            # anthropic, pyautogui, Pillow
├── skills/
│   └── fl-studio/
│       ├── index.md            # Table of contents for all skills
│       ├── navigation.md       # How to get around FL Studio UI + keyboard shortcuts
│       └── drum-pattern.md     # Hand-written first skill
├── sessions/
│   ├── session-001.jsonl       # Raw session logs
│   └── lessons-learned.md      # Consolidated lessons (top 20, updated between sessions)
├── library/
│   └── fl-studio-manual/       # Pre-loaded reference docs (FL Studio manual excerpts)
├── templates/
│   └── default.flp            # FL Studio project template for deterministic reset
└── demo/
    └── (recorded videos go here)
```

### Day 2 (Feb 11) — Agent Controls FL Studio

- Agent follows skill doc to place a kick drum pattern
- Keyboard-first interaction: F6, F7, Space, Ctrl+Z, Escape
- Hint Bar verification: move mouse → read hint → verify → click
- Add `emergency_reset()` recovery function
- Add `activate_fl_studio()` window focus management
- Wire up session logging (JSONL per session)
- Add post-action verification loop (screenshot diff, wait for UI to settle)
- Create FL Studio project template (`default.flp`) for deterministic session reset

**Day 2 gate:** Agent can complete kick drum pattern task from the skill doc with <5 errors.

### Day 3 (Feb 12) — Learning Loop + Measurable Improvement

- Build `consolidate.py`: reads session JSONL → generates lessons-learned.md + updates skill docs
- Test the engineered contrast: Session 1 (zero skills) → consolidate → Session 2 (full skills + lessons)
- **MEASURE:** Action count, error count, time-to-completion. Session 2 must show >30% improvement.
- Agent generates its own skill doc from experience (new skill, not just updated existing)
- Test generalization: kick skills applied to a structurally different task (tempo change or pattern length)
- Add session metrics tracking (counters dict + summary printout)

**Day 3 gate:** Measurable improvement between Session 1 and Session 2. If not → debug memory injection or pivot.

### Day 4 (Feb 13) — Demo Recording + Polish

- Set up OBS recording (FL Studio window + terminal + audio capture, synchronized)
- Pre-test recording setup thoroughly
- Record Session 1 footage (multiple takes, pick best) — this gets montaged at 4x
- Record Session 2 footage — this plays at 1x-2x
- Record Session 3 footage (generalization task)
- Build metrics summary display (can be simple terminal printout or basic HTML)
- If time: add Haiku success verification (see second-priority doc)

### Day 5 (Feb 14) — Edit Demo + Write Submission

- Edit 3-minute demo video (montage Session 1, highlight Sessions 2-3)
- Add metrics overlay in video editing (action counts, error rates per session)
- Write submission README / documentation
- If time: skill diff visualization, internal monologue overlay
- End-to-end dry run of submission

### Day 6 (Feb 15-16) — Buffer + Submit

- Fix anything broken
- Final demo recording if needed
- Submit before deadline
- 🎉

---


---

## 10. TECHNICAL REFERENCES

### Key Links

- **Computer Use SDK docs:** https://docs.anthropic.com/en/docs/agents-and-tools/computer-use
- **Reference implementation:** https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo
- **Opus 4.6 announcement:** https://www.anthropic.com/news/claude-opus-4-6
- **Opus 4.6 model page:** https://www.anthropic.com/claude/opus
- **FL Studio Web:** https://fl.studio
- **FL Studio MCP (reference):** https://github.com/ohhalim/flstudio-mcp
- **MindMirror (Artem's):** https://usemindmirror.com
- **Anthropic API pricing:** https://platform.claude.com/docs/en/about-claude/pricing

### Model Details

| Model | Use | Pricing |
|-------|-----|---------|
| Claude Opus 4.6 | Explorer agent, computer use, reasoning, post-mortem | $5/$25 per M tokens |
| Claude Haiku 4.5 | Optional: success verification ("Are steps 1,5,9,13 lit?") | $1/$5 per M tokens |

### Computer Use SDK — Available Actions

```
screenshot, left_click, right_click, middle_click, double_click, triple_click,
type, key, hold_key, mouse_move, left_click_drag, scroll, wait, zoom
```

Beta header: `"computer-use-2025-11-24"` (for Opus 4.6/4.5)  
Tool version: `computer_20251124`  
Recommended resolution: 1024x768 (XGA)

---


---

## 11. MEMORY ARCHITECTURE

### Design Philosophy: Files Over Databases

No Mem0. No pgvector. No embeddings. No vector search.

**Why:** Opus 4.6 has 1M token context. For a hackathon with <50 skill files and <10 session logs, you can load everything directly into the prompt. A retrieval pipeline is unnecessary complexity. Files on disk are debuggable, readable, and zero-dependency.

**When this breaks:** If you had 500+ skills or 100+ sessions, you'd need retrieval. Not our problem this week.

### The Two Knowledge Types

| Type | Format | Example | When Created |
|------|--------|---------|--------------|
| **Skills** | Markdown files with screenshots | `drum-pattern.md` — step-by-step guide to placing kick pattern | Step 1: hand-written. Step 2: agent-generated. |
| **Memories** | JSONL log entries per session | `{"action": "click(412,287)", "success": false, "lesson": "wrong row"}` | Step 2: auto-logged during agent execution. |

Skills are the **polished, reusable knowledge**. Memories are the **raw material** that feeds skill creation/improvement.

### How Learning Works Across Sessions

**Session 1 (no prior knowledge except hand-written skill):**
- Agent loads `drum-pattern.md` skill
- Attempts task, makes mistakes, logs memories to `session-001.jsonl`
- End of session: Haiku reviews memories → updates skill doc OR creates `lessons-learned.md`

**Session 2 (clean context, but has memories):**
- Agent loads `drum-pattern.md` (possibly updated) + `session-001.jsonl` lessons
- Avoids previous mistakes, completes faster
- Logs `session-002.jsonl`

**Session 3 (new task type, leverages existing knowledge):**
- Agent loads navigation skills + channel rack knowledge from previous sessions
- Applies known UI navigation to structurally different task (e.g., change tempo, switch pattern length)
- Generates new skill doc: `tempo-and-pattern.md`

### Key Insight: Automatic Context Injection (Smart, Not Brute-Force)

Every existing memory solution (Mem0, Zep, Letta, Claude native, ChatGPT) requires the model to decide to call a tool or the user to ask. Cortex's approach: **load relevant skills and memories into the system prompt BEFORE the agent starts reasoning.** No tool calls needed. The agent just... knows.

**CRITICAL: Don't load everything.** Anthropic charges premium pricing for prompts over 200k tokens, and large context = slow responses. Keep the always-on context small:

**Always inject (every step):**
- `skills/index.md` — one-page map of all available skills (~200 tokens)
- The skill file for the current task (e.g., `drum-pattern.md`, ~500-1000 tokens)
- `lessons/top-20.md` — consolidated top 20 lessons from all sessions (~500 tokens)
- Current session metrics (actions, mistakes, time)

**Inject on-demand (only when relevant):**
- Other skill files — loaded only if the agent references them or encounters related UI
- Full session logs — only during post-mortem review, not during active execution
- Screenshots in skills — only for Step 3 (stretch goal)

**Target: <50k tokens per step.** This keeps latency under 5 seconds and costs under $0.01 per action.

### Visual References in Skills (Step 3 / Stretch Goal)

**Full spec preserved in:** `cortex-second-priority.md` → Section 3 (includes annotated skill example, implementation code, token cost analysis).

When resources allow, skills include:
- Screenshots at key decision points (annotated)
- "What success looks like" vs "what failure looks like" images
- Before/after screenshots for each procedure step

This is genuinely novel — no existing AI skill system includes visual references alongside procedural text. But it's a stretch goal. Text-only skills work first.

**Also see:** `cortex-second-priority.md` → Section 5 for Haiku-based deterministic success verification (cheapest enhancement, ~1 hour to add).

---
