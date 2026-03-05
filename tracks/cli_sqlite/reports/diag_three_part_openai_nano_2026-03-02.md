# Three-Part Diagnosis (OpenAI, 2026-03-02)

Task under test: `shell_git_transfer_hotfix_hard`  
Default executor path: `gpt-5-nano` with strict mode, contract-gap retry on, structured lessons required.

This report answers one question: what is the dominant blocker?
- step cap?
- retry loop design?
- model capability floor?

## Part 1: Step-cap sensitivity (nano, no posttask learning)

Source: `tracks/cli_sqlite/reports/diag_part1_stepcap_summary.json`

- step-cap 6: `0/2` pass
- step-cap 12: `0/2` pass
- step-cap 20: `2/2` pass

Bottom line: step budget is a major blocker on this hard task.

## Part 2: Same total budget, single-long vs multi-attempt

Source: `tracks/cli_sqlite/reports/diag_part2_retryloop_summary.json`

- single attempt, 18 steps: `0/1` pass (score `0.556`, steps `17`)
- multi-attempt, 3x6 steps: `0/3` pass (scores `0.833`, `0.333`, `0.833`)
- in this lane, `v2_activations` stayed `0` for all runs

Bottom line: retry lane did not help here because memory did not engage in this setup (no activation signal).

## Part 3: Capability floor (same loop, nano vs mini)

Source: `tracks/cli_sqlite/reports/diag_part3_modelcap_summary.json`

- `gpt-5-nano`: `1/3` pass
- `gpt-5-mini`: `3/3` pass

Bottom line: capability floor is real on this task family.

## Diagnosis Verdict

Not one cause; three interacting causes:

1. **Step cap is too tight** for hard shell transfer (`6/12` underperform, `20` passes).  
2. **Retry loop currently fails to engage memory in some lanes** (`v2_activations=0`), so retries become repeated fresh failures.  
3. **Model floor matters** (`mini` succeeds consistently where `nano` does not).

## Practical Next Move (80/20)

1. Implement verifier-gated outer retry loop (attempt-based stop condition).  
2. Keep adaptive lesson injection (`1..3`, one per gap family) and enforce activation checks.  
3. Re-run same task with:
   - nano at `max_steps=12`, `max_attempts=3`
   - mini as control
4. Promote to larger benchmark only if:
   - nano shows non-zero activations and attempt-to-success improvement,
   - and ON outperforms OFF with clear delta.

## Artifacts

- `tracks/cli_sqlite/reports/diag_part1_stepcap_summary.json`
- `tracks/cli_sqlite/reports/diag_part2_retryloop_summary.json`
- `tracks/cli_sqlite/reports/diag_part3_modelcap_summary.json`
