Shell Git quick reference for deterministic task runs.

Repository bootstrap:
- `git init <repo>`
- `git -C <repo> config user.name "Cortex Bot"`
- `git -C <repo> config user.email "cortex@example.com"`
- `git -C <repo> checkout -b main`

Commit flow:
- `git -C <repo> add <paths>`
- `git -C <repo> commit -m "message"`
- `git -C <repo> checkout -b feature/name`
- `git -C <repo> merge --no-ff feature/name -m "merge: feature/name"`

Patch flow:
- `git -C source_repo format-patch -1 HEAD --stdout > hotfix.patch`
- `git -C target_repo am ../hotfix.patch`

Determinism rules:
- Always create explicit branches before commits.
- Use exact commit messages when task requires them.
- Verify resulting history with `git -C <repo> log --oneline --decorate -n 5`.

One-shot workflow pattern (preferred for benchmark tasks):
- Use one `run_bash` call with a single script that completes setup, edits, commit/merge, and verification.
- End the script with an explicit marker line so evaluator checks are easy to debug.

Example skeleton:
```bash
set -euo pipefail
repo="repo"
git -C "$repo" status --porcelain >/dev/null
# 1) branch setup
# 2) file edits
# 3) commit(s) with exact messages
# 4) merge / patch apply
# 5) deterministic verification
git -C "$repo" log --oneline --decorate -n 6
echo "VERIFY_OK shell_git_flow"
```
