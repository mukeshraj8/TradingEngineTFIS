# S23 Carry-Forward Runtime Gap

## Purpose

This note records the corrected S23 business semantics and separates them from
the current paper-runtime limitation.

## Correct Strategy Semantics

- S23 is a carry-forward strategy by design.
- Most TFIS option-selling strategies are carry-forward strategies.
- `carry_forward_allowed: true` means the strategy may carry positions across
  sessions when its rule set permits it.
- No option position may be carried beyond expiry.
- Expiry-near behavior must follow explicit strategy and instrument rollover
  policy such as `T-1` or `T-2` next-expiry selection.

## Current TFIS Runtime Gap

TFIS does not yet implement full multi-session paper-runtime support for S23.

Today, the current paper runtime still:

- operates as a same-day paper runtime
- requires explicit same-day square-off in the active runtime profile
- aborts if multi-session continuation is requested
- does not yet reopen, monitor, or close carried positions across sessions
- does not yet implement expiry-aware T-1 or T-2 next-expiry continuation

This is an implementation gap, not a business rule.

## Mandatory Safety Rules

- Expiry-safe forced close is mandatory.
- No broker execution is allowed.
- No weakening of selected-contract OI validation is allowed.
- Unsupported workbook paths must remain blocked rather than guessed.

## Required Next Runtime Capabilities

To support S23 correctly, TFIS will need:

- multi-session position state
- carry-forward lifecycle monitoring across sessions
- forced close before expiry
- strategy and instrument specific T-1 or T-2 next-expiry contract selection
- audit trails showing when a current-expiry position was closed and when a
  next-expiry position was selected

## Scope Reminder

This document does not authorize any runtime behavior change. It only clarifies
that the present same-day-only behavior is a current runtime limitation.
