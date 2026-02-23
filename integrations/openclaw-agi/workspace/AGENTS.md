# AGI Workspace (OpenClaw -> Cortex Learning Bridge)

Purpose:
- This workspace is a connector runtime for live chat testing.
- Core learning logic stays in Cortex (`tracks/cli_sqlite`).
- Do not re-implement learning logic here.

Routing rule:
1. Parse inbound messages with:
   `./bin/cortex_openclaw_dispatch.sh --text "<message>" --chat-id "<scope>"`
   - If chat scope is unavailable, omit `--chat-id` and dispatcher defaults to `global`.
2. Dispatch behavior is command-based:
   - `/run ...` => Cortex learning loop (execute -> judge -> lessons -> persist)
     - add `learn=off` to run execution-only (no lesson writes)
   - `/learn-status` => return learning signal summary
   - anything else => chat mode (no learning run, no lesson writes)
3. For benchmark tasks, dispatcher reuses known task ids.
4. For unseen tasks, dispatcher generates deterministic dynamic task ids scoped by chat.

Guardrails:
1. Keep bridge usage thin and deterministic.
2. Do not patch OpenClaw core code from this workspace.
3. Do not mutate the main profile at `~/.openclaw`.
4. Do not treat casual chat as tasks; only `/run` triggers task mode.

Quick examples:
1. `./bin/cortex_openclaw_dispatch.sh --chat-id tg-1336356696 --text "/run shell_git_transfer_hotfix"`
2. `./bin/cortex_openclaw_dispatch.sh --chat-id tg-1336356696 --text "/run domain=shell steps=6 build a hotfix branch flow and verify status"`
3. `./bin/cortex_openclaw_dispatch.sh --chat-id tg-1336356696 --text "/learn-status"`
4. `./bin/cortex_openclaw_dispatch.sh --text "/run domain=shell steps=6 verify git repo status and summarize"`
5. `./bin/cortex_openclaw_dispatch.sh --text "/run domain=shell steps=2 learn=off print current working directory and list files"`
