# Strategy Relevance And Data Governance

## Source Of Truth Versus Current-Market Approval

- The Excel workbook is a historical and structural source specification.
- It is not automatic proof that a strategy is still valid in the current Indian derivatives market.
- A strategy should not be implemented blindly just because it appears in the workbook.

## Required Strategy Classification

Before a strategy is treated as operationally relevant, it should be classified as one of:

- `ACTIVE`
- `HISTORICAL_BACKTEST_ONLY`
- `PLACEHOLDER`
- `DISCONTINUED`
- `UNKNOWN_REQUIRES_REVIEW`

Current registry also uses:

- `ACTIVE_CANDIDATE`

`ACTIVE_CANDIDATE` means the strategy is a plausible active-market candidate, but it has not yet completed every relevance and data-governance check required for full `ACTIVE` status.

`ACTIVE_CANDIDATE` is a transitional status:

- it may be backtested
- it is not live-approved
- it still requires evidence and review before promotion to `ACTIVE`

## Checks Required Before Marking A Strategy ACTIVE

Before a strategy can be promoted to `ACTIVE`, TFIS should confirm:

- the instrument or contract still exists
- the expiry cycle still exists
- lot size has been checked
- liquidity is acceptable
- data availability is confirmed
- Excel formula cross-check is completed
- backtest support is available
- current-market relevance is explicitly approved

## Specific Governance Notes

### BankNifty Weekly Options

- BankNifty weekly options should be treated as `HISTORICAL_BACKTEST_ONLY` or `PLACEHOLDER` unless current exchange availability is explicitly verified.
- BankNifty historical backtesting is still useful and should be preserved as a research input.
- BankNifty weekly live strategy work should remain blocked until current exchange availability is reverified.

### Nifty Weekly Options

- Nifty weekly options are reasonable `ACTIVE_CANDIDATE` entries, subject to liquidity and data validation.

### Stock Options

- Stock-option strategies must use a configurable liquid-stock universe rather than a hard-coded broad stock list.
- The liquid stock-option universe must remain user-configurable, not hardcoded from old workbook assumptions.

### Monthly Option Buying

- Monthly option buying should be treated as a separate strategy family.
- It should not be mixed into the S23 option-selling branch family.

### Rollover Rules

- Rollover should be handled in a separate lifecycle module later.
- It should not be embedded into entry, target, or stoploss formula semantics.

## Shared Data Direction

- TFIS should reuse shared captured data where possible.
- Existing `TradingEngine` captured Nifty, BankNifty, and options data should be evaluated for reuse.
- TFIS should avoid building a duplicate live capture framework.

## Practical Governance Rule

- A folder strategy being technically valid does not automatically make it current-market approved.
- Strategy validation, formula safety, and Excel cross-checks confirm structural correctness.
- Strategy relevance classification confirms whether the strategy should still be implemented, backtested, promoted, or held only as historical reference.
