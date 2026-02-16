# Artic API Integration Handoff

Use this document as the exact handoff brief for another AI to implement the next benchmark domain.

## Context
- Repo: `/Users/user/Programming_Projects/Cortex`
- Branch: `exp/memory-v2-agnostic`
- Current architecture: Memory V2 (error capture, retrieval, promotion) is integrated in `tracks/cli_sqlite`.
- Active plan source: `docs/MEMORY-V2-EXECUTION-PLAN.md`
- Decision already made: use a public API from `public-apis/public-apis` instead of MindMirror for this benchmark.

## Selected API
- API: Art Institute of Chicago (Artic)
- Docs: `https://api.artic.edu/docs/`
- Base endpoint: `https://api.artic.edu/api/v1`
- Why selected:
  - no auth required
  - stable public JSON API
  - non-trivial structure (search, pagination, nested payloads, follow-up fetches)

## Mission
Integrate Artic as a new benchmark domain so the agent can learn API interaction behavior across sessions using Memory V2.

Do not redesign Memory V2. Reuse the existing learning loop.

## Non-negotiables
- Keep runtime roles: executor + referee.
- Preserve Memory V2 channels and utility logic.
- No task-specific hardcoded error-string map required for memory to function.
- Add observability so demo viewers can see:
  - what was preloaded,
  - what failed,
  - what was injected,
  - what changed in the next attempt.

## Required implementation scope

### 1) New Artic domain adapter
Add:
- `tracks/cli_sqlite/domains/artic_adapter.py`

Requirements:
- domain name: `artic`
- executor tool name: `run_artic`
- tool input shape should support at least:
  - `method` (`GET` only for v1)
  - `path` (relative API path)
  - `query` (object/dict query params)
- execution should:
  - call Artic API
  - return normalized output text (trimmed JSON)
  - surface HTTP/parse failures as clean error text
  - include enough state/action context for Memory V2 fingerprinting

### 2) Register adapter in runtime
Update domain resolution/wiring so `--domain artic` works in:
- `tracks/cli_sqlite/agent_cli.py`
- `tracks/cli_sqlite/scripts/run_cli_agent.py`
- any relevant domain registry files

### 3) Add Artic tasks
Add task folders under `tracks/cli_sqlite/tasks/` for progressive learning:

- `artic_search_basic`
  - objective: find 2 artworks for a query term and display title + id
  - suggested path: `/artworks/search`

- `artic_followup_fetch`
  - objective: search, then fetch details for top result id
  - suggested paths: `/artworks/search` then `/artworks/{id}`

- `artic_pagination_extract`
  - objective: get page 2 with limit N and extract specific fields
  - ensure pagination params are used correctly

Each task needs a `task.md`.
Use judge-first evaluation if no deterministic contract is added.

### 4) Demo observability compatibility
Ensure the timeline/demo scripts clearly display Artic attempts and injected hints:
- `tracks/cli_sqlite/scripts/memory_timeline_demo.py`

No regressions to existing domains.

### 5) Bench script support
Allow running Artic in benchmark workflow (or add a dedicated script) so we can run:
- clean baseline run
- repeated runs for learning signal
- retention/interference check with another domain

## Suggested first task run command
```bash
python3 tracks/cli_sqlite/scripts/run_cli_agent.py \
  --task-id artic_search_basic \
  --domain artic \
  --session 31001 \
  --max-steps 6 \
  --bootstrap \
  --learning-mode strict \
  --posttask-mode candidate \
  --verbose
```

## Acceptance criteria
- `--domain artic` works end-to-end.
- At least one Artic task shows:
  - fail on early run,
  - Memory V2 event capture,
  - on-error hint injection,
  - improved follow-up run.
- Existing tests still pass:
```bash
python3 -m pytest tracks/cli_sqlite/tests -q
```
- Add/extend tests for Artic adapter behavior and timeline visibility.

## Output expected from implementing AI
- change summary
- exact files changed
- test commands and results
- benchmark command(s) and result snippet
- remaining risks/open questions

## Copy-paste prompt for another AI
You are implementing a new API benchmark domain in this repo.

Read first:
1) `docs/MEMORY-V2-EXECUTION-PLAN.md`
2) `tracks/cli_sqlite/agent_cli.py`
3) `tracks/cli_sqlite/domain_adapter.py`
4) `tracks/cli_sqlite/domains/` existing adapters
5) `tracks/cli_sqlite/scripts/run_cli_agent.py`
6) `tracks/cli_sqlite/scripts/memory_timeline_demo.py`

Implement Art Institute of Chicago API (`https://api.artic.edu/docs/`) as domain `artic` with tool `run_artic`, add progressive tasks, and ensure Memory V2 learning + observability work unchanged.

Constraints:
- Keep executor + referee flow.
- Keep Memory V2 architecture; no hardcoded per-task error maps required.
- Maintain compatibility with existing domains and tests.

Deliver:
- working `--domain artic` runs,
- tests updated,
- benchmark/demo commands,
- Conventional Commit(s) with bullet body (what/why/files/risk).
