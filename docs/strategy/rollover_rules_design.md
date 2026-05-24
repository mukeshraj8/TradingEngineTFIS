# Rollover Rules Design

## Scope

Rollover should be implemented as a separate lifecycle module later.

It should not be folded into:

- entry formula logic
- target formula logic
- stoploss formula logic

## Reference Timing Windows

### Options Buy And Options Sell

- index and stock options: `2:30 PM` to `3:00 PM`
- currency options: `4:00 PM` to `4:30 PM`

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

## Special Handling Notes

- target-achieved states may change the rollover behavior
- partial target completion may affect the carried quantity
- next-contract pricing may require premium or discount adjustment logic

## Open Questions

- exact quantity adjustment after partial targets
- exact target and stoploss recalculation logic in the next contract
- premium or discount adjustment between current and next contract
- whether stoploss should be assumed hit if next-contract CMP invalidates the
  carried setup
- what data is required for next-contract price comparison and decision audit

## Deferred Status

Rollover behavior is documented here for future implementation, but remains
deferred until:

- the lifecycle module is designed explicitly
- the necessary data inputs are defined
- the edge cases are clarified from the reference materials
