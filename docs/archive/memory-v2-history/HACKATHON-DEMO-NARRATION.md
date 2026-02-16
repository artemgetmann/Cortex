# Memory V2 Hackathon Narration Script

Use this as a single speaking script for your demo video.

## 1) Opening (Problem)

- Current AI is great inside one session, but it usually resets between chats.
- It can recover once, then repeat the same mistake again later.
- Most memory approaches still require the user to manually maintain docs, skills, or reminders.
- That is not how learning should work.

## 2) What I Built (Solution)

- I built a persistent-memory agent and stress-tested it in two environments.
- Environment one is the CLI lab, where the memory loop is stable.
- Environment two is real computer use in FL Studio, which is much harder.

## 3) What the FL Demo Tries To Do

- Open Channel Rack with `F6`.
- Program a 4-on-the-floor kick pattern on steps `1,5,9,13`.
- Play and stop transport to verify behavior.

## 4) What Worked

- I added end-of-run evaluation with hybrid authority.
- Deterministic checks plus visual judge plus disagreement handling.
- No blind pass based on one model claim.
- Lessons persist across sessions and can improve later attempts.

## 5) What Did Not Fully Land

- Reliability is not production-grade yet.
- Visual grounding in dense UI is still brittle.
- Cross-task transfer in messy real UI workflows still needs work.

## 6) Why This Still Matters

- The architecture is proven:
- capture failures,
- store lessons,
- retrieve lessons in later runs,
- score outcomes with an explicit referee layer.
- That is the foundation for reliable long-horizon agents.

## 7) Honest Close

- I chose correctness over fake confidence.
- I can show both successful runs and failure cases.
- Next step is reliability engineering, not architecture invention.

## 8) Optional Punchline

- The memory system works; the frontier problem is robust visual grounding under noisy real-world UI states.

## 9) Live Command To Run During Demo

```bash
AUTO_TIMELINE=1 AUTO_TOKEN_REPORT=1 bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh
```

## 10) What To Show On Screen

- Mixed benchmark JSON outputs in `/tmp/memory_mixed_wave*.json`.
- Timeline traces in `/tmp/memory_timeline_wave*.txt`.
- Token/cost summary in `/tmp/memory_mixed_tokens_*.json`.

