shell task: shell_git_transfer_hotfix.

Goal:
1) Create local repositories `source_repo` and `target_repo`.
2) In each repo, set local git config (`user.name`, `user.email`) and create branch `main`.
3) In `source_repo`, create `hotfix.txt` using `hotfix_payload.txt`, commit message exactly `hotfix: add retry backoff note`, and export one patch file named `hotfix.patch` using `git format-patch -1 HEAD --stdout`.
4) In `target_repo`, create one baseline commit, then apply `../hotfix.patch` via `git am`.
5) Write `target_repo/transfer_summary.txt` with exactly:
   - `TRANSFER_BRANCH main`
   - `TRANSFER_PATCHES 1`
6) Print exactly this verification line:
   - `GIT_TRANSFER_OK target=target_repo branch=main patches=1 file=hotfix.txt`

Constraints:
- Use `run_bash` only.
- Keep all files inside the task working directory.
- Do not use `/tmp`.
