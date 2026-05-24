# Monthly Option Buying Design

## Scope

Monthly option buying is a separate strategy family from the current S23
option-selling engine.

It should not be mixed into:

- S23 option-selling formulas
- S23 option-selling backtests
- S23 rollover assumptions

## Reference Themes From Provided Materials

The monthly option buying materials appear to involve:

- target-status based rollover or continuation management
- target `1`, `2`, `3`, and `4`
- APS handling
- separate stock-option buying monthly rules

These need their own modeling and should not be inferred into the existing
option-selling lifecycle.

## Design Separation

Monthly option buying should later have its own:

- strategy family classification
- lifecycle assumptions
- target-state model
- rollover rules
- backtest support rules

## Stock Option Buying Monthly

Stock option buying monthly rules require separate modeling and should depend on
a configurable liquid-stock universe.

They should not reuse the S23 option-selling assumptions automatically.

## Deferred Status

The materials are valuable references, but implementation should wait until:

- the target-state transitions are documented precisely
- APS semantics are clarified
- rollover behavior is separated from option-selling logic
- the tradable stock-option universe is defined explicitly
