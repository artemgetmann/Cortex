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
