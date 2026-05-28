# Rollover Rules Design

## Scope

Rollover and carry-forward handling should be implemented as a separate
lifecycle module later.

It should not be folded into:

- entry formula logic
- target formula logic
- stoploss formula logic

For TFIS option strategies, we need to distinguish:

- carry-forward of an open position across sessions before expiry
- mandatory close-out before expiry
- entry into the next expiry contract under strategy-specific rules

S23 and similar option-selling strategies may carry forward open positions.
What must remain forbidden is carrying the same option position beyond expiry.

## Reference Timing Windows

### Options Buy And Options Sell

- index and stock options: `2:30 PM` to `3:00 PM`
- currency options: `4:00 PM` to `4:30 PM`

These option timing notes are preserved only as archival reference material.
They do not imply that TFIS should implement option rollover behavior.

### Futures

- index futures: `10:00 AM` on expiry day
- stock futures: `10:00 AM` on `expiry - 1 day`
- currency futures: `10:00 AM` on `expiry - 1 day`
- commodity futures: `10:00 AM` on `expiry - 5 days`

## Reference Rollover Steps

Expected lifecycle sequence from the provided materials:

1. cancel pending orders in the current contract
2. exit the open position in the current contract at CMP or market order
3. carry or take the same position in the next contract where applicable
4. place the cancelled order in the next contract where applicable

These steps are relevant to carry-forward-capable strategies, including option
strategies, but the exact option-policy details must stay strategy- and
instrument-specific.

## Special Handling Notes

- Option selling:
  - no partial target concept unless the strategy explicitly defines one
  - the whole lot is booked on target unless the strategy says otherwise
  - open positions may carry forward before expiry when the strategy allows it
  - positions must be squared off before expiry according to strategy-specific
    T-1 / T-2 handling
- Option buying:
  - strategy-specific carry-forward policy still needs explicit modeling
- S23 option selling:
  - carry-forward is strategy-valid
  - full exit on target still closes the position
  - full exit on stoploss still closes the position
  - expiry handling must force exit before expiry
  - next-expiry handling should follow strategy-specific T-1 / T-2 rules

Future strategies may still need:

- target-achieved state handling
- quantity-carry logic
- next-contract pricing adjustments

## Open Questions

Option strategies:

- exact carry-forward monitoring state across sessions
- exact expiry-trigger timing by strategy and instrument
- exact next-expiry entry rules after mandatory close-out

Future strategies only:

- exact quantity adjustment after partial targets
- exact target and stoploss recalculation logic in the next contract
- premium or discount adjustment between current and next contract
- whether stoploss should be assumed hit if next-contract CMP invalidates the
  carried setup
- what data is required for next-contract price comparison and decision audit

## Deferred Status

Future rollover behavior is documented here for later implementation, but remains
deferred until:

- the lifecycle module is designed explicitly
- the necessary data inputs are defined
- the edge cases are clarified from the reference materials

Confirmed TFIS governance:

- carry-forward and expiry handling should not be hidden inside entry, target,
  or stoploss formulas
- option strategies need explicit lifecycle handling rather than blanket
  same-day assumptions
- futures still need their own separate rollover policy
