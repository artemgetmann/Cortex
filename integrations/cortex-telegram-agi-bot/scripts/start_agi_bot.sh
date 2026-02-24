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
exec bun run start
