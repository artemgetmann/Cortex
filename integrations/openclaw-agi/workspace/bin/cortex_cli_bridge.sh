#!/usr/bin/env bash
set -euo pipefail

# Thin bridge: OpenClaw runtime -> Cortex CLI learning loop.
# Keep this adapter minimal so all improvements happen in Cortex core code.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
RUNNER="$ROOT_DIR/tracks/cli_sqlite/scripts/run_cli_agent.py"

if [[ ! -f "$RUNNER" ]]; then
  echo "error: Cortex runner not found at $RUNNER"
  exit 1
fi

TASK_ID=""
TASK_TEXT=""
DOMAIN="${CORTEX_BRIDGE_DOMAIN:-shell}"
MAX_STEPS="${CORTEX_BRIDGE_MAX_STEPS:-6}"
SESSION_ID="${CORTEX_BRIDGE_SESSION:-$(date +%s)}"
LLM_BACKEND="${CORTEX_BRIDGE_LLM_BACKEND:-anthropic}"
MODEL_EXECUTOR="${CORTEX_BRIDGE_MODEL_EXECUTOR:-claude-haiku-4-5}"
MODEL_JUDGE="${CORTEX_BRIDGE_MODEL_JUDGE:-}"
VERBOSE=1

usage() {
  cat <<'EOF'
Usage:
  cortex_cli_bridge.sh --task-id <id> [options]
  cortex_cli_bridge.sh --task-id <id> --task "override task text" [options]

Options:
  --task-id <id>           Required task id in tracks/cli_sqlite/tasks
  --task <text>            Optional task override text
  --domain <name>          sqlite|gridtool|fluxtool|artic|shell (default: shell)
  --session <int>          Session id (default: epoch seconds)
  --max-steps <int>        Step cap (default: 6)
  --llm-backend <name>     anthropic|claude_print (default: anthropic)
  --model-executor <id>    Executor model (default: claude-haiku-4-5)
  --model-judge <id>       Optional judge model override
  --quiet                  Disable verbose runner output
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-id)
      TASK_ID="${2:-}"
      shift 2
      ;;
    --task)
      TASK_TEXT="${2:-}"
      shift 2
      ;;
    --domain)
      DOMAIN="${2:-}"
      shift 2
      ;;
    --session)
      SESSION_ID="${2:-}"
      shift 2
      ;;
    --max-steps)
      MAX_STEPS="${2:-}"
      shift 2
      ;;
    --llm-backend)
      LLM_BACKEND="${2:-}"
      shift 2
      ;;
    --model-executor)
      MODEL_EXECUTOR="${2:-}"
      shift 2
      ;;
    --model-judge)
      MODEL_JUDGE="${2:-}"
      shift 2
      ;;
    --quiet)
      VERBOSE=0
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$TASK_ID" ]]; then
  echo "error: --task-id is required"
  usage
  exit 1
fi

CMD=(
  python3 "$RUNNER"
  --task-id "$TASK_ID"
  --domain "$DOMAIN"
  --session "$SESSION_ID"
  --max-steps "$MAX_STEPS"
  --posttask-mode direct
  --contract-gap-retry
  --contract-gap-retry-steps 1
  --structured-lessons-required
  --llm-backend "$LLM_BACKEND"
  --model-executor "$MODEL_EXECUTOR"
)

# Optional task override lets OpenClaw pass user-specific variants without
# changing benchmark task files.
if [[ -n "$TASK_TEXT" ]]; then
  CMD+=(--task "$TASK_TEXT")
fi

if [[ -n "$MODEL_JUDGE" ]]; then
  CMD+=(--model-judge "$MODEL_JUDGE")
fi

if [[ "$VERBOSE" -eq 1 ]]; then
  CMD+=(--verbose)
fi

echo "Running Cortex bridge with:"
echo "  task_id=$TASK_ID domain=$DOMAIN session=$SESSION_ID max_steps=$MAX_STEPS"
echo "  llm_backend=$LLM_BACKEND model_executor=$MODEL_EXECUTOR"
if [[ -n "$MODEL_JUDGE" ]]; then
  echo "  model_judge=$MODEL_JUDGE"
fi

"${CMD[@]}"

SESSION_DIR="$ROOT_DIR/tracks/cli_sqlite/sessions/session-$(printf "%03d" "$SESSION_ID" 2>/dev/null || echo "$SESSION_ID")"
echo "Bridge run completed."
echo "Expected artifacts directory: $SESSION_DIR"
