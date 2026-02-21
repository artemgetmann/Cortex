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
