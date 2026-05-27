# S23 Operator Close-Out Policy

## Purpose

This document defines the operator close-out policy for S23 live-paper
ingress-only validation.

Scope:

- S23 only
- NIFTY only
- weekly options only
- paper mode only
- same-day only
- ingress and decision orchestration only
- no broker API
- no real orders
- no fills
- no lifecycle execution

## Required Session Artifacts

A session cannot be accepted unless all required ingress artifacts are present
and readable:

- `session_manifest.json`
- `audit_events.jsonl`
- `decision_summary.json`
- `paper_order_plan.json`
- `paper_order_intent.json`
- `execution_summary.json`
- `replay_bundle_manifest.json`
- `paper_session_review.json`
- `paper_session_review.md`
- `ingress_health_metrics.json`
- `orpt_rc_timing_audit.json`
- `selected_contract_audit.json`
- `s23_live_paper_dry_run.json`
- `s23_live_paper_dry_run.md`

Missing required artifacts are an immediate `NO_GO`.

## Session Classification

### PASS

A session is `PASS` only when all of the following are true:

- terminal state is `ORDER_PLANNED`
- readiness status is `READY`
- replay bundle is valid
- required artifacts are complete
- stale event count is `0`
- late event count is `0`
- missing option-chain count is `0`
- missing selected-contract count is `0`
- timezone mismatch count is `0`
- unsupported branch or continuation count is `0`
- selected contract is present in the option chain
- selected contract quote is fresh at finalize
- selected-contract availability ratio is `100%`
- no-trade reasons are empty
- abort reasons are empty
- ORPT and RC arrival lag are both `<= 2.5s`
- selected-contract freshness at finalize is `<= 5.0s`

### WARNING

A session is `WARNING` when it still satisfies all hard safety rules but needs
manual review before it can count as operationally clean.

Current warning cases:

- ORPT or RC arrival lag is `> 2.5s` and `<= 5.0s`

`WARNING` sessions are not automatically failed, but they cannot be treated as
fully clean evidence.

### NO_GO

A session is `NO_GO` when any hard blocker occurs.

Hard blockers:

- terminal state is not `ORDER_PLANNED`
- readiness status is not `READY`
- any required artifact is missing or corrupt
- any timezone mismatch
- unsupported branch
- unsupported continuation
- selected contract missing at decision time
- selected contract not present in option chain
- selected contract quote not fresh at finalize
- selected-contract freshness at finalize is `> 5.0s`
- stale event count `> 0`
- late event count `> 0`
- missing option chain at decision time
- missing required `09:15`, `ORPT`, or `RC` snapshot
- ORPT or RC arrival lag is `> 5.0s`
- non-empty no-trade reasons
- non-empty abort reasons

## Timing And Freshness Thresholds

### ORPT / RC timing

- clean pass threshold: `<= 2.5s`
- warning threshold: `> 2.5s` and `<= 5.0s`
- hard block threshold: `> 5.0s`

### Selected-contract freshness

- hard maximum quote age at finalize: `5.0s`
- if freshness cannot be proven, the session is `NO_GO`

## Manual Review Triggers

Manual review is required for:

- every `WARNING` session
- every replay-derived normalized source session until a broader multi-date
  ingress suite exists
- any session with non-empty warning flags
- any session where ORPT or RC is near threshold
- any session that touches current-day timing overlays and does not remain a
  clean `PASS`

## Aggregate Acceptance Thresholds

The current operator threshold set for an ingress-only pilot day is:

- minimum `PASS` rate: `80%`
- maximum `WARNING` count: `1`
- maximum `NO_GO` count: `0`
- selected-contract availability: `100%`
- acceptable no-trade rate: `0%`

If these thresholds are not met, the pilot day is `NO_GO`.

## Rollout Interpretation

### NO_GO

Use `NO_GO` when:

- any hard blocker occurs
- aggregate thresholds are not met
- required artifacts are incomplete

### LIMITED_GO

Use `LIMITED_GO` when:

- aggregate thresholds are met
- `NO_GO` count remains `0`
- one bounded `WARNING` session is present at most
- remaining concerns are operational review items rather than strategy defects

This supports continued ingress-only validation and tightly controlled
live-like rehearsal planning. It does not enable broad paper rollout.

### GO_FOR_CONTROLLED_PAPER

Use `GO_FOR_CONTROLLED_PAPER` only when:

- aggregate thresholds are met
- all sessions are clean `PASS`
- replay-derived source shapes no longer need special sign-off
- a broader multi-date ingress suite exists

## Current Baseline

The first broadened ingress-only suite now lives under:

`D:/TradingEngineTFIS/tmp/s23_live_paper_dry_runs/2026-05-27/s23-ingress-validation-suite-v1`

Current result:

- total sessions: `5`
- `PASS`: `4`
- `WARNING`: `1`
- `NO_GO`: `0`
- pass rate: `80.0%`
- selected-contract availability: `100.0%`
- max ORPT/RC lag: `4.0s`
- recommendation: `LIMITED_GO`

Interpretation:

- the ingress-only gate is now operationally enforceable
- live-like fill and lifecycle should still remain disabled until broader
  multi-date ingress evidence exists
