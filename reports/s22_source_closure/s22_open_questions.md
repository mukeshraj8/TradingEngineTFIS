# S22 Open Questions

Verdict: `S22_SOURCE_AND_UNIVERSE_CONDITIONAL`

## S22-Q001 - Current Exchange-Eligible Stock-Options Universe

Status: `CLOSED_USER_CLARIFIED_ARCHITECTURE_RULE`

- Business stage: stock universe.
- Source inspected: `AB8` stock dropdown list, `config/tradable_universe/liquid_stock_options.yaml`, `config/monthly_status_instruments.yaml`.
- Evidence: `AB8!B5` is dated `2023-08-01`; `config/tradable_universe/liquid_stock_options.yaml` has `symbols: []`.
- Decision: use a versioned instrument-master snapshot applicable to the trading date as authoritative `EXCHANGE_ELIGIBLE_UNIVERSE`.
- Consequence: AB8/AB10 are strategy-supported-universe evidence only and must not be treated as indefinitely current F&O eligibility.

## S22-Q002 - Operator-Enabled S22 Subset

Status: `CLOSED_USER_CLARIFIED_OPERATOR_SELECTION`

- Business stage: operator controls and simultaneous risk.
- Source inspected: `config/tradable_universe/liquid_stock_options.yaml`.
- Decision: enable `RELIANCE` as the only Stage 1 S22 internal-paper stock.
- Scope: one instrument-bound S22 strategy instance and one internal-paper account.
- Metadata gate: before implementation, the dated instrument-master snapshot must confirm F&O eligibility for the test trading date, lot size and effective date, strike interval and tick size, monthly option expiry availability, broker and market-data identifiers, and usable option-chain, premium and OI evidence.
- Fail-closed rule: if RELIANCE metadata is incomplete, return `BLOCKED_METADATA` and report exact missing fields. Do not select a substitute automatically.

## S22-Q003 - Per-Stock Instrument Metadata Master

Status: `CLOSED_USER_CLARIFIED_ARCHITECTURE_RULE`

- Business stage: contract selection, quantity, accounting, subscriptions.
- Source inspected: `AB11!H12/K12`, `AB16!I90:W91`, `config/monthly_status_instruments.yaml`.
- Evidence: workbook contains a RELIANCE example, but the repo does not contain a complete current master for all enabled stocks with lot-size effective dates, strike interval, broker symbol/token, data-provider symbol/token, expiry support, tick size, and current option eligibility.
- Decision: use a versioned, trading-date-specific instrument-master snapshot. Missing, stale, conflicting, or ambiguous metadata must produce `BLOCKED_METADATA`.
- Consequence: S22 policy stores `configured_quantity_lots = 1`; runtime resolves exchange units from the trading-date-applicable lot size.

No S22 source/universe questions remain open. S22 implementation may begin only
with the RELIANCE metadata gate; no substitute stock may be selected
automatically.
