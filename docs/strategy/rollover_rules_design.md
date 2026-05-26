# Rollover Rules Design

## Scope

Rollover should be implemented as a separate lifecycle module later, but only
for future-based strategies.

It should not be folded into:

- entry formula logic
- target formula logic
- stoploss formula logic

It is not applicable to:

- option selling strategies
- option buying strategies
- the S23 option-selling family

For TFIS option strategies, any exit ends that position. A later trade must be
a fresh calculation and a fresh position, not a rollover.

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

These steps are future-strategy only. They do not apply to options in TFIS.

## Special Handling Notes

- Option selling:
  - no partial target concept
  - the whole lot is booked on target
  - no rollover after target, stoploss, or expiry-day exit
- Option buying:
  - no rollover
  - any new trade after exit is a fresh calculation and fresh position
- S23 option selling:
  - full exit on target
  - full exit on stoploss
  - full expiry-day exit or square-off
  - no carry to the next option contract

Future strategies may still need:

- target-achieved state handling
- quantity-carry logic
- next-contract pricing adjustments

## Open Questions

Option strategies:

- not applicable for TFIS option selling
- not applicable for TFIS option buying

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

- rollover should not be added to S23
- rollover should not be added to option selling
- rollover should not be added to option buying
- future rollover belongs to a separate future-strategy family
