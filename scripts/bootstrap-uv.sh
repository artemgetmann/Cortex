#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

python3 -c "import anthropic, pyautogui, PIL; print('deps ok')"

