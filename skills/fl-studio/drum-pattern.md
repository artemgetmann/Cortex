# Skill: Create a 4-on-the-Floor Kick Pattern

Program a basic house/techno kick pattern in FL Studio's Channel Rack.

## Channel Rack Layout

The Channel Rack is a grid. Each row is one instrument:
- **Left side**: channel number, LED (green = unmuted), channel name (e.g. "808 Kick").
- **Right side**: 16 step buttons in a horizontal row. Each is a small rectangle.
  - Step 1 = leftmost button. Step 16 = rightmost.
  - Steps 1, 5, 9, 13 are evenly spaced at quarter intervals across the 16 buttons.
  - Lit (bright) = active. Dark = inactive.
- Channel rows are stacked vertically, ~20 px apart. The Kick is usually channel 1 (top row).

## Procedure

1. Press `F6` to open/focus Channel Rack.
2. Visually identify the row labeled "Kick" (or "808 Kick"). It is usually the first row.
   - If unsure, hover the **channel name** (left side) and check the Hint Bar.
   - Once confirmed, **immediately proceed to clicking step buttons**. Do not re-verify.
3. Batch-click all 4 step buttons in the Kick row: **step 1, step 5, step 9, step 13**.
   - Click each button once, one after another. Do NOT take screenshots or verify between clicks.
   - **CRITICAL**: Step buttons show time elapsed in the Hint Bar, NOT the channel name. This is normal. Do NOT hover step buttons to verify — just click based on position in the confirmed Kick row.
   - After clicking ALL 4 steps, take ONE screenshot to verify all 4 are lit.
   - If any step is wrong, press `Cmd+Z` to undo and retry that step only.
4. Press `Space` to start playback. Verify the kick plays on every beat.
5. Press `Space` again to stop.

## Keyboard Shortcuts

- `F6`: Open/focus Channel Rack
- `Space`: Play/Stop
- `Cmd+Z`: Undo

## Common Mistakes

- Clicking the wrong row (rows are close together, ~20 px apart).
- Channel muted (green LED is off).
- Wrong transport mode (`PAT` should be lit, not `SONG`).
- Re-verifying instead of clicking — once you see "Kick" in the row label, click the steps.
- Verifying after each step click — batch all 4 clicks, then verify once with a screenshot.
- Hovering step buttons and reading time elapsed in Hint Bar — this is expected, not an error.

## Tempo Change Playbook (for tempo tasks)

- Target the BPM number display directly (e.g., `130.000`).
- Use direct entry first: click the BPM field, type target value (e.g., `140`), press `Enter`, verify it reads `140.000`.
- Avoid right-click tempo menus for basic tempo changes unless explicitly requested.
- Avoid repeated scroll loops for tempo; if direct entry fails once, retry with one alternate click-focus and direct entry.

## Verification Checklist

- Steps 1, 5, 9, 13 are lit in the Kick row.
- Transport timer advances during playback.
- You hear a kick on every beat.
