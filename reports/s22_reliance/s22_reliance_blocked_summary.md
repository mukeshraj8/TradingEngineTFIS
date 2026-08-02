# S22 RELIANCE Metadata Gate Summary

Verdict: `S22_RELIANCE_BLOCKED`

S22 source closure and the RELIANCE operator selection are accepted, but the
Stage 1 one-stock implementation cannot safely begin because the required dated
instrument-master snapshot is not present in the repository.

## StrategyInstance Assessment

`StrategyInstanceDefinition` is sufficient for the S22 RELIANCE Stage 1 model.
It already carries strategy definition, strategy version, underlying,
exchange, segment, account, execution mode, lot quantity, and schedule. The
existing `PositionCycleIdentity` isolates mutable state with
`strategy_instance_id + trading_date + position_cycle_id`, and selected
contract identity can be attached to the pre-market/evaluation output.

No `InstrumentBoundStrategyInstance` abstraction is required by the available
evidence.

## Metadata Result

Required metadata gate result: `BLOCKED_METADATA`.

Missing required evidence:

- RELIANCE F&O eligibility for the test trading date.
- Lot size with effective date from a dated instrument-master snapshot.
- Strike interval and tick size from the dated metadata source.
- Monthly option expiry availability.
- Broker and market-data identifiers.
- Usable option-chain, premium, and OI evidence.

Workbook-derived RELIANCE rows remain valid S22 formula cross-check evidence,
but they are not the accepted current exchange-eligibility or instrument-master
authority.

## Runtime Impact

Runtime impact: `NONE`.

No source code, runtime configuration, broker path, paper path, live path,
PositionCycle logic, accounting logic, or workbook files were changed.

## Next Gate

Provide or add a dated versioned RELIANCE instrument-master snapshot with the
required fields, then rerun the S22 RELIANCE one-stock proof. Do not select a
substitute stock automatically.
