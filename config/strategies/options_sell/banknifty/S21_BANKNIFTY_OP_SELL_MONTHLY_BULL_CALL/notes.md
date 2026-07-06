# S21 BankNifty Monthly Bull Call

Source: `d:/TFIS/Selected/Rules/strategies/BNF Monthly OS Rules.jpg`.

This folder models the Bullish / Bullish Confirmed Call Sell leg for S21. It is
configuration and rule-validation scaffolding only; it is not enabled in any
live or paper BankNifty runner.

Configurable defaults:

- strike buffer: `5.0%`
- strike step: `100`
- ideal premium threshold: `2.0%`
- minimum premium threshold: `1.5%`
- entry discount: `7.5%`
- target reduction: `60.0%`
- entry-percent SL: `60.0%`
- structure SL buffer: `7.0%`
- minimum OI: `500 * lot_size`, represented as `17500` with configurable
  `lot_size: 35.0`

Before operational promotion, confirm the active BankNifty lot size, exact
monthly-expiry selection policy, ORPT/RC timing applicability, and
carry-forward/square-off lifecycle rules.
