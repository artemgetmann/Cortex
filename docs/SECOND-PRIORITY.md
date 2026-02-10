# CORTEX: Second-Priority Components

**Reference document for features CUT from the main plan. Revisit if ahead of schedule (Day 4+).**

Parent document: `cortex-hackathon-plan.md`

---

## 1. Background Monitor Agent (Haiku 4.5)

**Status:** CUT from main plan. Replaced with serial post-mortem (Opus reviews its own session at the end).

**Why it was cut:** Async coordination between two agents modifying the same filesystem introduces race conditions. Both GPT and Gemini flagged this independently as unnecessary complexity for a 6-day solo hackathon.

**When to revisit:** If serial post-mortem produces low-quality skill updates, or if you want real-time struggle detection during a session (not just end-of-session review).

### Full Original Spec

**Role:** Cheap agent (Haiku 4.5, $1/$5 per M tokens) that watches the Explorer's progress and helps in real-time.

**Functions:**

1. **Struggle detection:** If the Explorer makes the same mistake 2+ times, inject relevant memories into context: "Last time you tried this, you discovered that..." This requires monitoring the Explorer's action log in real-time and comparing against past failure patterns.

2. **Memory consolidation:** After each session, review raw observations (JSONL log entries) and consolidate into structured skill documents. Turns messy "I clicked here and it didn't work" entries into clean "Step 1: Do X. Common mistake: Don't do Y." procedures.

3. **Importance scoring:** Track which memories are retrieved most often across sessions. Increase importance scores for frequently-useful memories, decay scores for unused ones. This helps prioritize what gets injected into context when space is limited.

4. **Skill updates:** When the Explorer learns something new about an existing skill (e.g., discovers a keyboard shortcut for something previously done via clicking), update the skill document automatically.

### Implementation Approach

```python
import anthropic
import json
import time
from watchdog import Observer, FileSystemEventHandler

class MonitorAgent:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.model = "claude-haiku-4-5-20251001"
    
    def watch_session_log(self, log_path):
        """Watch the Explorer's session log for patterns."""
        # Use filesystem watcher to detect new log entries
        # Every N entries, analyze for repeated mistakes
        pass
    
    def detect_struggle(self, recent_entries, all_memories):
        """Check if Explorer is repeating a known mistake."""
        prompt = f"""
        The Explorer agent just performed these actions:
        {json.dumps(recent_entries[-5:], indent=2)}
        
        Here are relevant past memories:
        {json.dumps(all_memories, indent=2)}
        
        Is the Explorer repeating a known mistake? If yes, what memory 
        should be injected to help? Respond with:
        - "NO_INTERVENTION" if the Explorer is doing fine
        - A specific memory/tip to inject if it's struggling
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    
    def consolidate_session(self, session_log_path, existing_skills_dir):
        """End-of-session: consolidate raw logs into structured skills."""
        with open(session_log_path) as f:
            entries = [json.loads(line) for line in f]
        
        prompt = f"""
        Review this session log and produce:
        1. An updated skill document (markdown) incorporating new learnings
        2. A "lessons learned" summary (max 20 bullet points)
        3. Importance scores for each lesson (0.0-1.0)
        
        Session log:
        {json.dumps(entries, indent=2)}
        
        Existing skills:
        {self._load_skills(existing_skills_dir)}
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    
    def score_importance(self, memories, retrieval_counts):
        """Adjust importance scores based on usage patterns."""
        for memory_id, count in retrieval_counts.items():
            # Simple heuristic: more retrievals = more important
            # Decay unused memories over time
            pass
```

### Architecture Diagram (With Monitor)

```
┌─────────────────────────────────────────────┐
│                CORTEX SYSTEM                 │
│                                              │
│  ┌──────────┐    actions    ┌────────────┐  │
│  │ Explorer  │─────────────→│ FL Studio  │  │
│  │ (Opus)    │←─────────────│ (Desktop)  │  │
│  └─────┬─────┘  screenshots └────────────┘  │
│        │                                     │
│        │ logs actions                        │
│        ▼                                     │
│  ┌──────────┐                               │
│  │ Session   │◄──── Monitor watches          │
│  │ Log       │      in real-time             │
│  └─────┬─────┘                               │
│        │                                     │
│        │         ┌──────────────┐            │
│        └────────→│ Monitor      │            │
│                  │ (Haiku 4.5)  │            │
│                  └──────┬───────┘            │
│                         │                    │
│              ┌──────────┴──────────┐         │
│              ▼                     ▼         │
│        ┌──────────┐        ┌──────────┐     │
│        │ Skills/  │        │ Inject   │     │
│        │ Update   │        │ Memory   │     │
│        └──────────┘        └──────────┘     │
└─────────────────────────────────────────────┘
```

---

## 2. Research Sub-Agents (BrightData + Web Scraping)

**Status:** CUT from main plan. Replaced with pre-loaded `library/` folder of FL Studio reference docs.

**Why it was cut:** Getting BrightData + scraping + parsing reliable is a project in itself. Not worth the risk on a 6-day timeline.

**When to revisit:** If the agent encounters UI elements that aren't covered by pre-loaded docs or skills, and you want it to self-research rather than you manually adding documentation.

### Full Original Spec

**Role:** When the Explorer encounters something completely unfamiliar, spawn parallel research agents to find information.

**Implementation:**
- Uses Anthropic Agents SDK for subagent spawning
- Research agent uses BrightData MCP server for web scraping
- Searches FL Studio tutorials, Image-Line documentation, forum posts, Reddit
- Returns structured findings to the Explorer
- Findings get stored as skills for future use

**Example flow:**
1. Explorer encounters FL Studio's "Piano Roll" for the first time
2. Explorer doesn't have a skill file for Piano Roll
3. Explorer spawns research sub-agent: "Find documentation on how to use FL Studio Piano Roll"
4. Sub-agent scrapes:
   - Image-Line official docs (https://www.image-line.com/fl-studio-learning/)
   - FL Studio manual PDF
   - YouTube tutorial descriptions
   - Reddit r/FL_Studio tips
   - Forum posts about Piano Roll workflows
5. Sub-agent returns structured summary:
   ```markdown
   # Piano Roll Quick Reference
   ## Opening: F7 or double-click a pattern
   ## Key Controls:
   - Left click: place note
   - Right click: delete note
   - Ctrl+scroll: zoom
   - Shift+scroll: scroll horizontally
   ## Common Patterns:
   - Chord: stack notes vertically
   - Melody: place notes sequentially
   ```
6. Explorer uses this knowledge to proceed
7. Knowledge gets stored as `skills/fl-studio/piano-roll.md` for future use

### Implementation Code

```python
import anthropic
from anthropic import Agent, AgentTeam

class ResearchSubAgent:
    def __init__(self):
        self.client = anthropic.Anthropic()
    
    def research(self, query, sources=None):
        """Spawn a research agent to find information."""
        system_prompt = """
        You are a research agent. Your job is to find practical, 
        actionable information about FL Studio features.
        
        When given a query:
        1. Search for official documentation first
        2. Look for tutorial content
        3. Check community forums for tips and gotchas
        4. Return a structured markdown summary
        
        Focus on: step-by-step procedures, keyboard shortcuts, 
        common mistakes, and visual descriptions of UI elements.
        """
        
        # Using BrightData MCP for web scraping
        tools = [
            {
                "type": "mcp",
                "server": {
                    "url": "https://mcp.brightdata.com/sse",
                    "token": "YOUR_TOKEN"
                }
            }
        ]
        
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",  # Cheap for research
            max_tokens=2000,
            system=system_prompt,
            tools=tools,
            messages=[{
                "role": "user", 
                "content": f"Research this FL Studio topic: {query}"
            }]
        )
        return self._parse_to_skill(response)
    
    def _parse_to_skill(self, response):
        """Convert research results into a skill document."""
        # Extract text content, format as markdown skill
        pass
```

### BrightData MCP Integration

```python
# MCP server configuration for BrightData
mcp_config = {
    "name": "BrightData",
    "url": "https://mcp.brightdata.com/sse",
    "token": "YOUR_BRIGHTDATA_TOKEN",
    "capabilities": [
        "scrape_as_markdown",  # Get page content as markdown
        "search_engine",       # Google/Bing search
        "scrape_batch"         # Multiple URLs at once
    ]
}

# Example: scrape FL Studio documentation
search_queries = [
    "FL Studio Piano Roll tutorial site:image-line.com",
    "FL Studio Channel Rack guide",
    "FL Studio keyboard shortcuts complete list"
]
```

---

## 3. Image Memories (Step 3 — Stretch Goal)

**Status:** Deferred to Day 4+ if Steps 1-2 work solidly.

**Why it was deferred:** Text-only skills are sufficient to demonstrate learning. Adding image storage/retrieval adds complexity without proportional demo impact.

**When to revisit:** If text-only skills hit accuracy limits (e.g., agent can't distinguish between similar-looking UI elements without visual reference), or if you want to make the demo more visually impressive.

### Full Spec

**What it adds to skills:**
- Screenshots at key decision points (annotated with red circles/arrows)
- "What success looks like" reference images
- "What failure looks like" reference images (e.g., wrong row selected)
- Before/after screenshots for each procedure step

**What it adds to memories:**
- `screenshot_before` and `screenshot_after` fields in JSONL entries
- Visual diff: "this is what I saw before clicking, this is what happened after"
- Enables the agent to recognize UI states it's seen before

**Example enhanced skill:**
```markdown
# Skill: Create a Kick Drum Pattern

## Steps
1. Open Channel Rack (F6)
   - Success: ![channel-rack-open](screenshots/channel-rack-open.png)
   - Failure: ![wrong-panel](screenshots/mixer-not-channel-rack.png)
   
2. Find Kick row (first row, labeled "Kick")
   - Target area: ![kick-row-highlight](screenshots/kick-row-annotated.png)
   - Common mistake: ![clap-row-confusion](screenshots/clap-vs-kick.png)
   
3. Click step buttons 1, 5, 9, 13
   - Success: ![steps-lit](screenshots/kick-pattern-complete.png)
```

**Implementation:**
```python
import base64
from PIL import Image

def store_visual_memory(session_id, step, action, screenshot_before, screenshot_after, success):
    """Store a memory entry with visual references."""
    # Save screenshots to disk
    before_path = f"memories/screenshots/s{session_id}_step{step}_before.png"
    after_path = f"memories/screenshots/s{session_id}_step{step}_after.png"
    screenshot_before.save(before_path)
    screenshot_after.save(after_path)
    
    # Log entry with paths
    entry = {
        "session": session_id,
        "step": step,
        "action": action,
        "success": success,
        "screenshot_before": before_path,
        "screenshot_after": after_path,
        "visual_diff_significant": images_are_different(screenshot_before, screenshot_after)
    }
    return entry

def inject_visual_skill(skill_path, context_messages):
    """Load a skill with images into the API context."""
    # Read markdown
    with open(skill_path) as f:
        skill_text = f.read()
    
    # Find referenced images and encode as base64
    content_blocks = [{"type": "text", "text": skill_text}]
    for img_ref in extract_image_refs(skill_text):
        img = Image.open(img_ref)
        b64 = base64.b64encode(img.tobytes()).decode()
        content_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64}
        })
    
    return content_blocks
```

**Token cost consideration:** Each screenshot is ~1500 tokens (at 1024x768). A skill with 5 reference images adds ~7500 tokens. Manageable, but adds up across multiple skills. Only inject images for the active task's skill, not all skills.

**Novelty claim:** No existing AI skill system includes visual references alongside procedural text. This is genuinely novel — humans learn with both text instructions and visual examples, and Cortex would replicate that.

---

## 4. Importance Scoring & Memory Decay

**Status:** CUT. Part of the Background Monitor that was eliminated.

**When to revisit:** If the agent accumulates >50 lessons and you need to prioritize which ones to inject.

### Spec

```python
class MemoryImportance:
    def __init__(self):
        self.retrieval_counts = {}  # memory_id -> count
        self.last_accessed = {}     # memory_id -> timestamp
    
    def score(self, memory_id, base_importance=0.5):
        """Calculate importance score with retrieval boost and time decay."""
        retrievals = self.retrieval_counts.get(memory_id, 0)
        last_access = self.last_accessed.get(memory_id, time.time())
        age_hours = (time.time() - last_access) / 3600
        
        # Boost for frequent retrieval, decay for age
        retrieval_boost = min(0.3, retrievals * 0.05)
        time_decay = min(0.2, age_hours * 0.01)
        
        return min(1.0, base_importance + retrieval_boost - time_decay)
    
    def get_top_n(self, memories, n=20):
        """Return the N most important memories for context injection."""
        scored = [(m, self.score(m['id'])) for m in memories]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, s in scored[:n]]
```

---

## 5. Deterministic Success Verification (Haiku)

**Status:** Optional enhancement. Mentioned in main plan but not fully specified.

**What it does:** After the Explorer completes an action, send the screenshot to Haiku 4.5 with a simple yes/no question: "Are step buttons 1, 5, 9, 13 lit in the Kick row?" This is cheaper and faster than using Opus for verification.

### Spec

```python
def verify_success(screenshot_b64, expected_state_description):
    """Use Haiku to cheaply verify if an action succeeded."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}
                },
                {
                    "type": "text",
                    "text": f"Answer YES or NO only: {expected_state_description}"
                }
            ]
        }]
    )
    answer = response.content[0].text.strip().upper()
    return answer == "YES"

# Usage:
success = verify_success(
    screenshot_b64=current_screenshot,
    expected_state_description="Are exactly 4 step buttons lit in the first row (Kick) at positions 1, 5, 9, and 13?"
)
if not success:
    # Retry or try alternative approach
    pass
```

**Cost:** ~$0.001 per verification (Haiku is cheap). Worth adding if you have time — gives the demo a "self-checking" quality that impresses technical judges.

---

## Priority Order for Adding These Back

If you finish the core (Steps 1-2) by Day 3 and have time:

1. **Deterministic Success Verification (Haiku)** — 1 hour to add. Highest impact per effort. Makes the agent self-checking.
2. **Image Memories in Skills** — 2-3 hours. Makes skills richer. Good for demo ("look, it even stores screenshots of what went wrong").
3. **Background Monitor** — 4-6 hours. Real-time struggle detection is impressive but complex. Only if everything else works.
4. **Research Sub-Agents** — 4-6 hours. BrightData integration is risky. Only if agent gets stuck on things not covered by pre-loaded docs.
5. **Importance Scoring** — 1 hour. Only matters if you have 50+ memories. Unlikely in hackathon timeframe.

---

## 6. Backup: Docker + Reference Implementation (If Mac Native Fails)

**Status:** Backup approach. Only use if pyautogui on Mac has persistent issues (focus problems, coordinate bugs, FL Studio blocking programmatic input).

**When to switch:** If by end of Day 1, the ported macOS loop has reliability issues that can't be fixed in <2 hours.

### What This Gives You

Anthropic's reference implementation is a fully working Docker container with:
- Ubuntu + Xvfb (virtual display at 1024x768)
- Mutter (window manager) + Tint2 (taskbar)
- Chromium browser
- Python agent loop (`loop.py`) already wired to Opus API
- `xdotool` for mouse/keyboard control (already works, no porting needed)
- Web interface to view and interact with the container

**Source:** https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo

### The Tradeoff

| Aspect | Mac Native (Primary) | Docker (Backup) |
|--------|---------------------|-----------------|
| FL Studio | Desktop with all plugins | Would need FL Studio Web (toy) or Wine (fragile) |
| Setup time | Port loop.py (~2-3 hours) | `docker build` (~30 min) |
| Third-party VSTs | ✅ All installed | ❌ Not available |
| Audio output | ✅ Real audio | ⚠️ Needs PulseAudio config |
| Demo impressiveness | ✅ "Real pro desktop app" | ⚠️ "Web app in a container" |
| Reliability | ⚠️ macOS quirks (focus, permissions) | ✅ Battle-tested on Linux |

### How to Set Up (If Needed)

```bash
git clone https://github.com/anthropics/anthropic-quickstarts.git
cd anthropic-quickstarts/computer-use-demo
export ANTHROPIC_API_KEY=your_key
docker build -t cortex .
docker run -p 8080:8080 -p 5900:5900 -p 6080:6080 cortex
# Open http://localhost:8080 to see the agent's screen
```

Then navigate to FL Studio Web (fl.studio) in the container's Chromium browser. The loop.py already handles screenshot → API → xdotool → screenshot. You'd only need to add the memory/skills layer on top.

### Docker + FL Studio Web Limitations (Why This Is Backup, Not Primary)

- No third-party plugins (no Serum, FabFilter, Sausage Fattener)
- FL Studio Web may still be in beta waitlist
- Browser control is less impressive than desktop control for judges
- Audio routing from Docker container is tricky
- Claude Code already does browser automation — this approach is less novel

### Docker + Wine + FL Studio Desktop (Last Resort)

If you absolutely need FL Studio Desktop in Docker:
```dockerfile
# Very fragile — Wine + FL Studio has known issues
RUN dpkg --add-architecture i386 && apt-get update
RUN apt-get install -y wine64 wine32
# Then install FL Studio via Wine... 
# This is likely to eat a full day of debugging. NOT recommended for a hackathon.
```

**Recommendation:** If Mac native fails, try Docker + FL Studio Web first. If that also fails, pivot to a simpler target application (see Appendix B in main plan doc).
