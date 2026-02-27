# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Cortex Bridge Commands

- Task-mode dispatch:
  `./bin/cortex_openclaw_dispatch.sh --chat-id <scope> --text "<natural language task>"`
  - explicit mode: `... --text "/run <task or task_id>"`
  - safe/no-memory mode: append `learn=off` in `/run` text
- Learning status:
  `./bin/cortex_openclaw_dispatch.sh --chat-id <scope> --text "/learn-status"`
- Force chat mode:
  `./bin/cortex_openclaw_dispatch.sh --chat-id <scope> --text "/chat <message>"`
- Direct benchmark bridge (advanced/manual):
  `./bin/cortex_cli_bridge.sh --task-id <id> --domain <domain>`
