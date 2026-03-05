Legacy OpenClaw profile backups (disabled)

Purpose
- Keep old OpenClaw AGI profile directories out of `~` to reduce runtime confusion.
- Prevent accidental reuse of deprecated Telegram profile paths.

Safety
- This directory is gitignored by default.
- Do not commit raw profile data from this directory.
- Profiles can include secrets/tokens; treat as local-only runtime backup.

Current expected serving path
- Active Cortex Telegram bot path is `integrations/cortex-telegram-agi-bot`.
- LaunchAgent label is `com.cortex-telegram-agi`.
