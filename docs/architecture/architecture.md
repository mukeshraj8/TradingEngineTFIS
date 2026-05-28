# Architecture

## Intent

TradingEngineTFIS is a clean, lightweight rule-engine project for TFIS strategy modeling. It is intentionally separate from existing TradingEngine codebases.

## Core Model

- The Excel workbook is the source specification for formulas, mappings, thresholds, and rule definitions.
- Normalized YAML or JSON artifacts become the runtime input to the engine.
- The runtime engine stays generic; strategy behavior is config-driven rather than embedded directly in engine code.
- Future integration with an existing scoring engine, if needed, should happen through explicit interfaces or adapters, not through copied code.

## Broker Agnostic Boundary

- Core TFIS modules must not directly import or depend on Fyers, Zerodha, Angel, Upstox, or any other broker SDK.
- Broker access belongs behind small adapter interfaces.
- Broker adapters may exist in dedicated boundary packages as long as strategy logic consumes only normalized TFIS events.
- Strategy evaluation, formulas, rule logic, market structure, risk, and scheduling must remain portable across paper, mock, and future real brokers.
- Tests should prefer paper, mock, or fixture-backed broker adapters rather than any external API.

## Non-Goals For This Skeleton

- No live trading
- No broker order placement
- No live-money FYERS integration
- No dashboard
- No replay certification
- No reuse of current-engine scoring internals

## Package Direction

- `tfis.domain`: shared domain models and concepts
- `tfis.formulas`: formula parsing and evaluation interfaces
- `tfis.rules`: rule definitions and rule execution contracts
- `tfis.market_structure`: market-structure abstractions used by rules
- `tfis.strategy`: strategy composition from normalized inputs
- `tfis.execution`: placeholder execution abstractions only, no live order routing
- `tfis.brokers`: broker-agnostic market-data adapters that normalize external payloads into TFIS events
- `tfis.risk`: risk rule abstractions
- `tfis.storage`: persistence for normalized artifacts and outputs
- `tfis.importers`: Excel-to-normalized import pipeline
- `tfis.integrations`: future adapter interfaces to external systems
