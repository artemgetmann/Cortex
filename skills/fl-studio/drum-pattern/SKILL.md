---
name: fl-studio-drum-pattern
description: Use when the task is to create a 4-on-the-floor kick pattern in FL Studio Channel Rack (steps 1,5,9,13) with keyboard-first verification.
version: 1
---

# FL Studio Drum Pattern

Program a basic house/techno kick pattern in FL Studio's Channel Rack.

## Channel Rack Layout

The Channel Rack is a grid. Each row is one instrument:
- Left side: channel number, LED (green = unmuted), channel name (e.g. "808 Kick").
- Right side: 16 step buttons in a horizontal row. Each is a small rectangle.
  - Step 1 = leftmost button. Step 16 = rightmost.
  - Steps 1, 5, 9, 13 are evenly spaced at quarter intervals across the 16 buttons.
  - Lit (bright) = active. Dark = inactive.
- Channel rows are stacked vertically, about 20 px apart. The Kick is usually channel 1 (top row).

## Procedure

1. Press `F6` to open/focus Channel Rack.
2. Identify the row labeled "Kick" (or "808 Kick"). It is usually the first row.
   - If unsure, hover the channel name (left side) and check Hint Bar.
   - If still ambiguous, call `extract_fl_state` to identify kick-row index and active-step status.
   - Once confirmed, proceed to clicking step buttons. Do not re-verify repeatedly.
3. Click the 4 step buttons in the Kick row: step 1, step 5, step 9, step 13.
   - Once the Kick row is visible, click immediately. Do not run extra Hint Bar checks for step buttons.
   - Click each button once. Do not verify between clicks.
   - Step buttons show time elapsed in Hint Bar, not channel name. That is expected and not an error.
   - Do not spam zoom on the step row. At most one zoom is allowed before the click sequence.
   - After all 4 clicks, take one screenshot to verify all 4 are lit.
   - Prefer `extract_fl_state` for final verification of active steps 1/5/9/13.
   - If a click is wrong, press `Cmd+Z` and retry that step.
4. Press `Space` to start playback and verify the kick plays on every beat.
5. Press `Space` again to stop.

## Keyboard Shortcuts

- `F6`: Open/focus Channel Rack
- `Space`: Play/Stop
- `Cmd+Z`: Undo

## Verification Checklist

- Steps 1, 5, 9, 13 are lit in the Kick row.
- Transport timer advances during playback.
- Kick plays on every beat.
