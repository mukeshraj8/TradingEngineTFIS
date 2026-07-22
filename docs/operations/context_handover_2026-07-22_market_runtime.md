# TFIS Context Handover - Wednesday, July 22, 2026

This note is the restart point for a fresh Codex thread after the long July 22
market-time runtime investigation.

## What Happened Today

- Pre-open checks passed:
  - scheduled tasks existed for `TFIS S21 Morning Supervised Decision` and
    `TFIS S23 Morning Supervised Decision`
  - both were `Ready`
  - both were due at about `09:08 IST` on Wednesday, July 22, 2026
  - `scripts/pre_live_readiness.py --profile prod --require-token --json`
    returned `overall_status=PASS`
- At the live checkpoints:
  - `09:17 IST`: S23 had launched and written `2026-07-22` artifacts; S21 had
    failed
  - `09:25 IST`: S23 was still healthy; S21 still had no valid session output
  - `09:31 IST`: both S23 and S21 had valid `2026-07-22` session trees,
    `scheduled_run_metadata.json`, stage explainers, and paper order state

## Root Cause Found

- The original S21 scheduled launch collided with S23 during FYERS token
  refresh/auth work.
- S21 failed with FYERS `invalid auth code`.
- A later host-level rerun of S21 with `-SkipRefresh` succeeded and completed
  the morning flow.

## Code Changed In This Market-Time Fix

- `scripts/start_s21_fyers_morning_supervised_decision.ps1`
- `scripts/start_s23_fyers_morning_supervised_decision.ps1`

Both wrappers now:

- capture stdout/stderr through a shared invocation helper
- detect the specific FYERS auth-race symptom (`invalid auth code`)
- retry once with `--skip-refresh`

This is an operational recovery hardening, not a strategy-formula change.

## Operational Outcome

- S23 completed its `09:16 / 09:25 / 09:30` supervised flow on schedule.
- S21 missed the original `09:08` launch but was recovered during market hours.
- The shared paper lifecycle supervisor started and produced live paper-order
  state for both strategies.
- The dashboard URL reported by the runtime remained:
  - `http://127.0.0.1:8765/index.html`

## Important Runtime Truth

- The immediate operational gap is reduced, but the startup architecture is not
  fully solved yet.
- TFIS still needs a cleaner root fix so S21 and S23 do not compete for FYERS
  refresh/auth work at the same startup second.
- The wrapper retry makes the system safer for paper runtime, but it is still a
  fallback, not the ideal final startup design.

## What To Do Next In A Fresh Thread

1. Read:
   - `docs/operations/ai_change_agreement.md`
   - `docs/operations/project_rulebook.md`
   - this handover note
   - `docs/operations/current_state.md`
   - `docs/operations/next_steps.md`
2. Confirm the current working tree and latest commit.
3. Continue the remaining refactor after market close, starting with the
   startup-race root fix before moving back to broader architectural cleanup.
4. Keep TFIS paper-safe; do not introduce live-order behavior.

## Recommended Next Engineering Slice

Build one serialized TFIS morning startup contract:

- one token/auth preparation step
- then S21 and S23 supervised launches
- then one shared lifecycle-supervisor handoff

That should replace the current "both wrappers refresh independently" posture
and remove the FYERS auth-code collision rather than merely retrying around it.

## Notes About The Wider Worktree

- The worktree contains many refactor changes beyond this market-time fix.
- Do not revert unrelated modified files.
- The July 22 market-time recovery should be treated as one operational hardening
  step within the broader shared-paper-runtime refactor already in progress.
