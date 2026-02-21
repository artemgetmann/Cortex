shell task: shell_git_train_release_flow.

Goal:
1) Use `release_seed.txt` to create `trainer_repo/release_notes.md`.
2) Initialize a git repository in `trainer_repo`, set local git config (`user.name`, `user.email`), and create branch `main`.
3) Commit `release_notes.md` as the baseline commit on `main`.
4) Create branch `feature/release-flow`, add `handoff.md`, append one extra line to `release_notes.md`, and commit.
5) Merge `feature/release-flow` back into `main` with `--no-ff`.
6) Write `trainer_repo/train_summary.txt` with exactly:
   - `TRAIN_BRANCH main`
   - `TRAIN_MERGE feature/release-flow`
7) Print exactly this verification line:
   - `GIT_TRAIN_OK repo=trainer_repo branch=main commits=3 merge=1 summary=train_summary.txt`

Constraints:
- Use `run_bash` only.
- Keep all files inside the task working directory.
- Do not use `/tmp`.
