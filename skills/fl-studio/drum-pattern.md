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
3. Click the 4 step buttons in the Kick row: **step 1, step 5, step 9, step 13**.
   - Click each button once. A lit button confirms activation.
   - **IMPORTANT**: Step buttons show "Select" in the Hint Bar, NOT the channel name. Do not try to verify step buttons via Hint Bar — just click them based on their position in the confirmed Kick row.
   - After each click, take a screenshot to verify the correct step toggled on.
   - If the wrong step or row was clicked, press `Ctrl+Z` to undo, then retry.
4. Press `Space` to start playback. Verify the kick plays on every beat.
5. Press `Space` again to stop.

## Keyboard Shortcuts

- `F6`: Open/focus Channel Rack
- `Space`: Play/Stop
- `Ctrl+Z`: Undo

## Common Mistakes

- Clicking the wrong row (rows are close together, ~20 px apart).
- Channel muted (green LED is off).
- Wrong transport mode (`PAT` should be lit, not `SONG`).
- Re-verifying instead of clicking — once you see "Kick" in the row label, click the steps.

## Verification Checklist

- Steps 1, 5, 9, 13 are lit in the Kick row.
- Transport timer advances during playback.
- You hear a kick on every beat.
