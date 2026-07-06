# S21 BankNifty Monthly Bull Put

Source: `d:/TFIS/Selected/Rules/strategies/BNF Monthly OS Rules.jpg`.

This folder models the Bullish / Bullish Confirmed Put Sell leg for S21. It is
configuration and rule-validation scaffolding only; it is not enabled in any
live or paper BankNifty runner.

The rule-sheet numeric values are parameterized in `parameters.yaml`, including
the `5.0%` strike buffer, `2.0%` ideal premium threshold, `1.5%` minimum premium
threshold, `7.5%` entry discount, `60.0%` target/entry-SL percentages, and
`10.0%` structure SL buffer.

Before operational promotion, confirm the active BankNifty lot size, exact
monthly-expiry selection policy, ORPT/RC timing applicability, and
carry-forward/square-off lifecycle rules.
