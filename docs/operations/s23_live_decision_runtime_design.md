# S23 Live Decision Runtime Design

This document describes the current TFIS-native supervised live decision path
for S23 paper trading.

## Purpose

TFIS must own live market decisioning. `TradingEngineProd` may help with
credential refresh automation or later replay evidence, but TFIS itself must be
able to:

- collect normalized market inputs
- derive S23 checkpoints
- classify monthly status
- select the contract with strict OI validation
- build a paper trade decision summary

without placing broker orders and without depending on a TradingEngine runtime
session.

## Current Implemented Path

The current supervised path is:

`S23FyersSnapshotCollector`
-> normalized underlying quote
-> normalized morning underlying bars
-> normalized option-chain snapshot
-> `S23RuntimeInputDeriver`
-> monthly status + TFIS checkpoints + runtime aliases
-> `S23PaperLivePreludeBuilder`
-> `S23PaperLiveDecisionBuilder`
-> `trade_decision_summary.json`
-> `trade_decision_summary.md`

Current operator command:

```powershell
python scripts/run_s23_fyers_live_decision_check.py `
  --config config/paper.s23.fyers_connect_test.yaml `
  --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT `
  --reference-packet config/reference_packets/s23_bear_put_live_decision_reference.json `
  --artifact-root tmp/s23_fyers_live_decision `
  --session-id s23-fyers-live-decision
```

## What TFIS Derives Today

From normalized quote + morning bars + option chain, TFIS now derives:

- `09:15` checkpoint snapshot
- `ORPT` checkpoint snapshot
- `RC` checkpoint snapshot
- current-day high/low across those checkpoints
- required market-level alias validation
- required option-alias validation
- monthly status classification
- S23 paper prelude events
- selected contract with strict OI enforcement
- paper trade decision summary

## What The Reference Packet Still Provides

The current implementation still uses a TFIS reference packet for inputs that
are not yet sourced natively inside TFIS:

- monthly-status reference levels
- prior-session spot reference levels such as `d2hh`, `d2ll`, `d3hh`, `d3ll`
- prior-session option aliases such as `OPT_PRV_2DHH` and `OPT_PRV_3DLL`
- workbook provenance fields
- current sizing values

This is a runtime implementation gap, not a strategy-rule gap.

## Safety Guarantees

The current path remains deliberately bounded:

- S23 only
- NIFTY only
- paper only
- strict option-chain OI validation remains mandatory
- no broker order placement
- no continuous socket/session loop
- no lifecycle execution
- no silent static selected-contract fallback unless explicit smoke override is
  requested

## Why This Matters

This is the first TFIS-native path that can show how the strategy is behaving
for live-paper decision formation:

- monthly status
- selected branch
- required checkpoints
- selected contract
- selected contract premium and OI
- entry / target / stoploss / FSL context

That gives operator-grade visibility into the decision itself before full live
socket orchestration is introduced.

## Remaining TFIS Gaps

The main remaining TFIS runtime gaps are:

1. Replace the reference packet with fully TFIS-native sourcing for prior-day
   and monthly-status reference values.
2. Extend the current one-shot decision path into a supervised socket/session
   orchestrator.
3. Add broader multi-date evidence around checkpoint collection and contract
   selection stability.
4. Keep carry-forward and expiry governance integrated as orchestration grows,
   without introducing broker execution.
