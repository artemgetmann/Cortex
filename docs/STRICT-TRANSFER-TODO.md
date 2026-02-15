# Strict Transfer TODO Tracker

Use this as the execution checklist. Update checkboxes and append proof links (commit hashes, test commands, or session ids) as work completes.

## Active TODOs
- [ ] Add `learning_mode` plumbing (`strict`/`legacy`) through CLI + agent runtime.
- [ ] Split critic prompt path into strict (generic) and legacy (existing).
- [ ] Implement retrieval provider + domain docs manifest interface.
- [ ] Switch strict hint matching from command regex to semantic/tag matching.
- [ ] Add one holdout fictional domain with remapped syntax/operators.
- [ ] Add `run_cross_domain.py` with train-domain/test-domain split.
- [ ] Add strict-mode tests for filtering, hint matching, and retrieval context wiring.
- [ ] Add holdout + cross-domain experiment commands to docs.
- [ ] Run verification matrix (strict in-domain, strict holdout, cross-domain transfer, legacy regression).

## Verification Matrix (to fill as executed)
- [ ] `python3 -m pytest tracks/cli_sqlite/tests -q`
- [ ] strict in-domain run command + result summary
- [ ] strict holdout run command + result summary
- [ ] cross-domain run command + transfer summary
- [ ] legacy mode sanity run command + summary

## Progress Log
- `2026-02-15`: Tracker created. Baseline checkpoint commit exists before strict-transfer implementation.
