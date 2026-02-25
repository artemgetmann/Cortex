shell task: shell_git_transfer_hotfix_hard.

Goal:
1) Use `show_fixture` to read `variant_spec.json` first. Treat it as source of truth for filenames, commit message, summary lines, and verification line.
2) Create local repositories `source_repo` and `target_repo`.
3) In each repo, set local git config (`user.name`, `user.email`) and create branch `main`.
4) In `source_repo`, create the exact hotfix file named by `variant_spec.json.hotfix_file`.
   - File content must include all lines from `variant_spec.json.hotfix_lines`.
   - Commit message must exactly equal `variant_spec.json.commit_message`.
   - Export one patch file named `variant_spec.json.patch_file` using `git format-patch -1 HEAD --stdout`.
5) In `target_repo`, create one baseline commit, then apply `../<patch_file>` via `git am`.
6) Write `target_repo/transfer_summary.txt` with exactly all lines from `variant_spec.json.summary_lines` (one line per entry).
7) Print exactly `variant_spec.json.verification_line`.

Constraints:
- Use `run_bash` only.
- Keep all files inside the task working directory.
- Do not use `/tmp`.
