# Cortex — Start Here

## What This Is

Cortex is a hackathon project (Anthropic "Built with Opus 4.6", Feb 10-16). An AI agent that teaches itself FL Studio through computer use + persistent memory. The gate test passed — native macOS Quartz CGEvent APIs work with FL Studio Desktop on this Mac.

## Documents

```
docs/
├── HANDOFF.md              ← YOU ARE HERE. Read this, then start working.
├── IMPLEMENTATION.md       ← PRIMARY. Architecture, API setup, computer use, memory system, dev plan.
├── FL-STUDIO-REFERENCE.md  ← SECONDARY. FL Studio UI guide, keyboard shortcuts, Hint Bar, Wave Candy.
├── DEMO-AND-STRATEGY.md    ← FOR ARTEM ONLY. Demo narrative, competitive landscape. Don't read this.
├── SECOND-PRIORITY.md      ← REFERENCE ONLY. Cut features, Docker backup. Don't read unless stuck.
```

**Read `IMPLEMENTATION.md` now.** It has everything you need. Reference `FL-STUDIO-REFERENCE.md` when writing skill docs or interacting with FL Studio's UI.

## What To Build

Two components. That's it.

1. **Explorer Agent** — Python script that loops: screenshot FL Studio → send to Opus 4.6 API → parse action → execute via Quartz CGEvent APIs → repeat
2. **Batch Consolidation Script** — Runs BETWEEN sessions. Reads session JSONL logs → generates/updates skill markdown files

No database. No Agents SDK. No Background Monitor. No research agents. No Docker. No custom UI.

## IMPORTANT: FL Studio Must Be Visible

FL Studio **MUST be forefront and visible on screen** for all tests and agent runs. If FL Studio is hidden/minimized:
- Window bounds detection fails (CGWindowListCopyWindowInfo returns nothing)
- Screenshots capture nothing
- Key delivery may still work (CGEventPostToPid) but you can't verify visually

**Before running any script:** Make sure FL Studio is visible and not behind other windows.

## Execution Steps (Do These In Order)

### Step 1: Clone reference implementation
```bash
git clone https://github.com/anthropics/anthropic-quickstarts.git
```
Examine `computer-use-demo/computer_use_demo/loop.py` and `tools/computer.py`. These are the foundation — we're porting them to macOS.

### Step 2: Create project structure
```
Cortex/
├── agent.py                    # Port from reference loop.py
├── computer_use.py             # Port from reference computer.py (xdotool → pyautogui)
├── memory.py                   # Read/write skills + session logs (files on disk)
├── consolidate.py              # Between-session consolidation
├── config.py                   # API key, screen dims, paths
├── requirements.txt            # anthropic, pyobjc (Quartz), Pillow, pynput (pyautogui removed — replaced by native macOS Quartz framework)
├── skills/fl-studio/
│   ├── index.md
│   └── drum-pattern.md         # Hand-written first skill
├── sessions/
├── library/
└── docs/                       # These planning docs
```

### Step 3: Port the reference implementation to macOS

Replace `xdotool` with native macOS Quartz CGEvent APIs (not pyautogui):
- Mouse: `CGWarpMouseCursorPosition` + `CGEventPost` (not `pyautogui.moveTo`/`click`)
- Keys: `CGEventPostToPid` to FL Studio PID (not `pyautogui.press`/`hotkey`)
- Screenshots: `Quartz.CGWindowListCreateImage` (not `pyautogui.screenshot`)
- Activation: `NSRunningApplication.activateWithOptions_` (not `osascript`)

**Activate FL Studio before every action:**

Use `NSRunningApplication.activateWithOptions_` with app name `"FL Studio"` (not `"FL Studio 2024"`). This is more reliable than the old `osascript` approach and doesn't require a subprocess call.

**API config:**
```python
tools=[{
    "type": "computer_20251124",
    "name": "computer",
    "display_width_px": 1024,
    "display_height_px": 768,
    "enable_zoom": True
}]
# Beta header: "computer-use-2025-11-24"
# Model: "claude-opus-4-6-20250219" we could actualy test with cheaper model for the start like haiku 4.5 or sonnet 4.5 idk maybe
```

**Resolution:** Ideal = force display to 1024x768 (BetterDisplay/SwitchResX) for 1:1 coordinate mapping. If can't force, implement Retina 3-layer scaling (see IMPLEMENTATION.md for fallback code).

### Step 4: Test the loop

Run these tests in order. Each must pass before moving on.

1. `"Take a screenshot and describe what you see"` — verify API receives screenshot and responds correctly
2. `"Press F6 to open the Channel Rack"` — verify keyboard execution works
3. `"Click the first step button in the Kick row"` — verify click lands on correct target
4. If clicks are off → check coordinate scaling or prefer keyboard-only

### Step 5: Add session logging

```python
import json, time

def log_action(session_id, step, task, action, success, lesson=""):
    entry = {"session": session_id, "step": step, "timestamp": time.time(),
             "task": task, "action": str(action), "success": success, "lesson": lesson}
    with open(f"sessions/session-{session_id:03d}.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
```

### Step 6: Add post-action verification

Wait for UI to settle before next screenshot:
```python
from PIL import ImageChops
import numpy as np

def wait_for_ui_settle(timeout=5.0, threshold=0.98):
    prev = pyautogui.screenshot()
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
        curr = pyautogui.screenshot()
        diff = ImageChops.difference(prev, curr)
        similarity = 1.0 - (np.array(diff).mean() / 255.0)
        if similarity > threshold:
            return curr
        prev = curr
    return curr
```

### Step 7: Add pause/resume (F12)

```python
from pynput import keyboard
PAUSED = False
def on_press(key):
    global PAUSED
    if key == keyboard.Key.f12:
        PAUSED = not PAUSED
        print(f"{'⏸️ PAUSED' if PAUSED else '▶️ RESUMED'}")
listener = keyboard.Listener(on_press=on_press)
listener.start()
```

## Do NOT

- Use the Anthropic Agents SDK (use raw `anthropic` client)
- Set up any database (no SQLite, no Mem0, no pgvector)
- Build a Background Monitor agent or research sub-agents
- Set up Docker (unless Mac native fails completely — see SECOND-PRIORITY.md)
- Build a custom UI/dashboard
- Install FL Studio Web

## Success Criteria for Day 1

1. ✅ Gate test passed (done)
2. Reference implementation cloned and examined
3. Project structure created
4. Ported loop running — agent screenshots FL Studio and describes it
5. Agent executes at least one keyboard shortcut (F6) and one accurate click
6. Session JSONL logging works

**All 6 done → Day 1 success. Move to Day 2 (skill-following + complete task).**

---

## Evidence Log

### Permission Diagnosis — PASS (2026-02-11)
- **Script:** `scripts/diag_permissions.py`
- **Results:**
  - Alacritty terminal: CGPreflightPostEventAccess = **False** (permission bug confirmed)
  - VS Code terminal: CGPreflightPostEventAccess = **True**
  - Claude Code sandbox: blocks XPC to `com.apple.hiservices-xpcservice` (events silently dropped)
  - Without sandbox: all APIs work correctly

### Space Playback Gate — PASS (2026-02-11)
- **Script:** `scripts/diag_focus_single.py J`
- **Method:** CGEventPostToPid(pid, Space) directly to FL Studio PID
- **Result:** Playback toggled successfully (confirmed by human — audio heard)
- **Window bounds:** owner='FL Studio', bounds=(0, 30, 1024, 678)
- **Key finding:** pyautogui replaced with Quartz CGEvent APIs for reliable input delivery
