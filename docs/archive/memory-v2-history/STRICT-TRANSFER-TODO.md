# Strict Transfer TODO Tracker

Use this as the execution checklist. Update checkboxes and append proof links (commit hashes, test commands, or session ids) as work completes.

## Active TODOs
- [x] Add `learning_mode` plumbing (`strict`/`legacy`) through CLI + agent runtime.
- [x] Split critic prompt path into strict (generic) and legacy (existing).
- [x] Implement retrieval provider + domain docs manifest interface.
- [x] Switch strict hint matching from command regex to semantic/tag matching.
- [x] Add one holdout fictional domain with remapped syntax/operators.
- [x] Add `run_cross_domain.py` with train-domain/test-domain split.
- [x] Add strict-mode tests for filtering, hint matching, and retrieval context wiring.
- [x] Add holdout + cross-domain experiment commands to docs.
- [x] Run verification matrix (strict in-domain, strict holdout, cross-domain transfer, legacy regression).

## Verification Matrix (to fill as executed)
- [x] `python3 -m pytest tracks/cli_sqlite/tests -q` (`49 passed` on `2026-02-15`)
- [x] strict in-domain: `python3 tracks/cli_sqlite/scripts/run_cli_agent.py --task-id aggregate_report --domain gridtool --learning-mode strict --session 18001 --max-steps 8 --bootstrap --mixed-errors` -> `eval_passed=true`, `eval_score=1.0`, `steps=6`.
- [x] strict holdout: `python3 tracks/cli_sqlite/scripts/run_cli_agent.py --task-id aggregate_report_holdout --domain fluxtool --learning-mode strict --session 18002 --max-steps 8 --bootstrap --mixed-errors` -> `eval_passed=true`, `eval_score=1.0`, `steps=7`.
- [x] cross-domain transfer: `python3 tracks/cli_sqlite/scripts/run_cross_domain.py --train-domain gridtool --test-domain fluxtool --train-task-id aggregate_report --test-task-id aggregate_report_holdout --learning-mode strict --train-sessions 3 --test-sessions 5 --start-session 18100 --max-steps 8 --bootstrap --mixed-errors --clear-lessons` -> `first_pass_index=1`, `post_pass_regressions=0`, `delta=0.0`.
- [x] legacy sanity: `python3 tracks/cli_sqlite/scripts/run_cli_agent.py --task-id aggregate_report --domain gridtool --learning-mode legacy --session 18003 --max-steps 8 --bootstrap --mixed-errors` -> `eval_passed=true`, `eval_score=1.0`, `steps=4`.
- [x] holdout CLI offline smoke: `python3 tracks/cli_sqlite/domains/fluxtool.py --workdir tracks/cli_sqlite/tasks/aggregate_report_holdout` -> emits grouped `region,total,cnt` CSV output.
- [x] cross-domain runner surface check: `python3 tracks/cli_sqlite/scripts/run_cross_domain.py --help` -> exposes `--train-domain/--test-domain` and transfer runner options.

## Progress Log
- `2026-02-15`: Tracker created. Baseline checkpoint commit exists before strict-transfer implementation.
- `2026-02-15`: Workstream 1 completed (commit hash: `pending-user-confirmation`). Added strict/legacy learning mode CLI plumbing and runtime metric field.
- `2026-02-15`: Workstreams 2-7 completed (commit hash: `pending-user-confirmation`). Added strict critic contract split, retrieval-backed critic context, strict semantic hint matching (cap=2), holdout fluxtool domain, cross-domain runner, strict transfer tests, and validation docs.
- `2026-02-15`: API-backed validation runs completed with `.env` key (sessions `18001`, `18002`, `18003`, `18100`-`18107`).
