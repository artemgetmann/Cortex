# FL Studio — Domain Reference

**FL Studio-specific knowledge for building skills and understanding the target application.**

---

## 2. TARGET APPLICATION: FL Studio

### Why FL Studio (Not Fusion 360, Not Photoshop, Not Browser Apps)

| Option | Verdict | Reason |
|--------|---------|--------|
| **Fusion 360** | ❌ Too complex | Requires 3D spatial awareness from 2D screenshots. CAD MCP servers produce poor results. Artem tried them — slow and unreliable. |
| **Photoshop** | ❌ Already done | Adobe shipped agentic AI for Photoshop (Oct 2025). ChatGPT can use Photoshop via API (Dec 2025). Adobe MCP server exists. Judges would see this as non-novel. |
| **Browser/coding agents** | ❌ Already exist | Claude Code does coding. Chrome extensions automate Gmail/Reddit. Every hackathon team will build one. |
| **FL Studio** | ✅ Novel + feasible | 2D UI (menus, piano roll, mixer, channel rack). No 3D spatial reasoning needed. Artem has music production background. Zero existing vision-based FL Studio agents. |

### FL Studio Web (Exists But NOT Our Approach)

**FL Studio Web launched in public beta in December 2025.** It's browser-based, simplified, and has no third-party VST support. While it eliminates setup complexity, it's a toy compared to the desktop version:

- ❌ No third-party plugins (no Serum, FabFilter, Sausage Fattener)
- ❌ Browser control is less impressive (Claude Code already does browser automation)
- ❌ Judges would see it as "just browser automation with extra steps"
- ❌ Not representative of how real music producers work

**We're using FL Studio Desktop on Artem's Mac instead:**
- ✅ Full plugin ecosystem (all third-party VSTs installed)
- ✅ Real professional production environment
- ✅ Desktop computer use (more impressive than browser control)
- ✅ Real audio output during development and demo
- ✅ Zero setup time (already installed with projects and presets)

### The "Deaf Composer" Problem

**Concern:** The agent can't hear what it creates. How can it make music?

**Answer:** AI has been composing music without hearing it since 2019.

- **OpenAI MuseNet (2019):** Generated 4-minute multi-instrument compositions by predicting MIDI tokens. Never "heard" anything — learned patterns from hundreds of thousands of MIDI files.
- **MIDI-LLM (Nov 2025):** LLMs adapted for text-to-MIDI generation. They generate symbolic music (notes, timing, velocity) based on pattern recognition from training data, not audio feedback.
- **MIDI Agent (commercial product):** VST plugin that uses ChatGPT, Claude, Gemini to generate MIDI directly in DAWs. The AI models never hear the output.
- **Key research finding:** "Models do not yet 'listen' as humans do, and are dependent on the quality and scope of symbolic input data." But they can still compose structured, musically coherent pieces.

**Claude Opus 4.6 has been trained on massive amounts of music theory, MIDI data, and production tutorials.** It knows that a kick drum typically hits on beats 1 and 3, hi-hats on every 8th note, snares on 2 and 4. It knows what a C minor scale is. It knows how FL Studio's piano roll works from documentation and tutorials in its training data. It doesn't need to hear the output to place notes correctly — it needs to understand music theory and the FL Studio UI, both of which it has.

**Practical approach for demo:**
1. Agent places notes based on music theory knowledge (not audio feedback)
2. The output plays audibly for the human viewer/judge
3. The impressive part isn't the music quality — it's that the agent **learned to navigate FL Studio and improved across sessions**

**Visual audio feedback (Wave Candy trick):**
Dock FL Studio's native **Wave Candy** plugin on the Master channel, set to Spectrum or Oscilloscope mode, pinned as "Detached" and "Always on Top" in a corner of the screen. This gives the agent visual proof that sound is playing — if there are no green waves in the visualizer, something is wrong (muted channel, VST not loaded, etc.). Add to the agent's system prompt: "If Wave Candy shows no activity after pressing Play, the audio chain is broken — check mute buttons and channel routing."

**If FL Studio proves too limited due to the hearing constraint,** pivot to a more visual application where output is immediately verifiable via screenshots (e.g., a simpler creative tool). But test FL Studio first — the novelty factor is highest here.

---


---

## APPENDIX A: FL Studio Desktop UI Elements (For Skill Creation)

Key UI components the agent needs to learn:
- **Channel Rack** — grid of instruments with step sequencer
- **Piano Roll** — note editor with pitch (vertical) and time (horizontal)
- **Playlist** — arrangement view with patterns and audio
- **Mixer** — volume, panning, effects for each channel
- **Transport** — play, stop, record, tempo, pattern/song mode
- **Browser** — file/sample/plugin browser

For the hackathon demo, focus on: **Channel Rack** and **Piano Roll** only.



## FL Studio Keyboard Shortcuts (Critical — Use These Over Clicking)

| Shortcut | Action |
|----------|--------|
| F5 | Playlist |
| F6 | Channel Rack (Step Sequencer) |
| F7 | Piano Roll |
| F9 | Mixer |
| Space | Play / Stop |
| Cmd+Z | Undo |
| Escape | Close dialog / deselect |
| Ctrl+S | Save |
| Tab | Toggle between Pattern and Song mode |
| Numpad +/- | Next/Previous pattern |
| Ctrl+L | Toggle pattern length |

**Always prefer keyboard shortcuts over clicking.** FL Studio's buttons are tiny (15-20px). Keyboard is reliable.

## Hint Bar

FL Studio has a **Hint Bar** at the bottom of the window. It shows the name/description of whatever UI element the mouse is hovering over. This is free ground-truth verification:

1. Move mouse to intended target
2. Read Hint Bar text
3. If Hint Bar matches intended target → click
4. If Hint Bar shows wrong element → adjust mouse position

This prevents the most common agent failure: clicking the wrong row/button because coordinates were slightly off.

## Wave Candy (Visual Audio Feedback)

**Problem:** The agent can't hear audio output.
**Solution:** Dock FL Studio's native **Wave Candy** plugin on the Master mixer channel:
- Set to Spectrum or Oscilloscope mode
- Pinned as "Detached" and "Always on Top" in bottom-right corner
- If Wave Candy shows activity → audio is playing
- If Wave Candy is flat → something is wrong (muted channel, VST not loaded, etc.)

Add to system prompt: "If Wave Candy shows no activity after pressing Play, the audio chain is broken — check mute buttons and channel routing."

## FL Studio Project Template

Create a `default.flp` template for deterministic session resets:
- Channel Rack visible
- 4 default channels: Kick, Clap, Hat, Snare
- Pattern 1 selected, empty
- Tempo: 120 BPM
- Wave Candy on Master, docked bottom-right
- All mixer channels at default volume
- No plugins loaded (keep it simple)

Open this template at the start of every session to ensure identical starting state.
