#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: missing env file at $ENV_FILE"
  echo "Create it from .env.example first."
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

# Dynamic path wiring: by default, bind runtime paths to the current checkout
# (repo/worktree) so operators do not need to rewrite .env when switching
# worktrees. Set CORTEX_DYNAMIC_PATHS=0 to pin legacy/static paths.
if [[ "${CORTEX_DYNAMIC_PATHS:-1}" != "0" ]]; then
  REPO_ROOT="$(cd "$ROOT_DIR/../.." && pwd)"
  export CORTEX_ROOT="$REPO_ROOT"
  export CORTEX_DISPATCHER_PATH="$REPO_ROOT/integrations/cortex_dispatch.py"
  export AI_WORKING_DIR="$ROOT_DIR/workspace"
fi

cd "$ROOT_DIR"

# LaunchAgent shells often have a minimal PATH. Resolve bun explicitly so the
# service can start reliably on reboot/login without manual PATH fixes.
BUN_BIN="${BUN_BIN:-}"
if [[ -z "$BUN_BIN" ]]; then
  if command -v bun >/dev/null 2>&1; then
    BUN_BIN="$(command -v bun)"
  elif [[ -x "$HOME/.bun/bin/bun" ]]; then
    BUN_BIN="$HOME/.bun/bin/bun"
  else
    echo "error: bun not found (set BUN_BIN or install Bun at ~/.bun/bin/bun)"
    exit 127
  fi
fi

exec "$BUN_BIN" run src/index.ts
