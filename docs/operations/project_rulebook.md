# Project Rulebook

## What TFIS Is

- A clean, separate TFIS rule-engine project.
- A config-driven strategy system built around normalized YAML/JSON definitions.
- A broker-agnostic core that can later connect to multiple adapters.

## What TFIS Is Not

- Not a copy of any sibling trading-engine repository.
- Not a replay-certification or evidence-heavy platform.
- Not a broker-specific live trading implementation.
- Not a place to hardwire Fyers, Zerodha, Angel, or Upstox into core logic.

## Allowed Dependencies In Core

- Python standard library
- `pyyaml`
- `pandas`
- `openpyxl`
- project-local domain, formula, rule, strategy, risk, storage, and abstraction modules

## Forbidden Dependencies In Core

- broker SDKs in core strategy/rule/formula/risk modules
- direct `fyers`, `kiteconnect`, `upstox`, or similar imports in core logic
- live order routing dependencies in formula or strategy evaluation code
- copied TradingEngine scoring internals inside TFIS core

## Broker Integration Rules

- Broker integrations must sit behind adapter interfaces.
- Core strategy code may depend on TFIS broker protocols, not broker SDKs.
- Real brokers must be implemented in dedicated adapter modules only.
- Paper/mock broker should be the default for tests and early development.

## Testing Rules

- Unit tests must run without network access.
- Tests should use the paper/mock broker rather than any external API.
- Deterministic fixtures are preferred over live market dependencies.
- Core imports must remain broker-SDK free.

## Strategy Rule Rules

- Excel workbook is the source specification.
- Runtime consumes normalized YAML/JSON, not raw spreadsheets.
- Strategy rules stay explicit, typed, and testable.
- Formula behavior must fail closed on unsupported syntax.

## Safety Rules

- No `eval` or `exec` for strategy formulas.
- Unsupported formulas or missing runtime references must raise safe errors.
- Core logic must not place live orders.
- Future broker adapters must be isolated from the strategy core.

## Future Integration Rules With Existing TradingEngine

- Existing TradingEngine scoring can only enter TFIS through a clean interface.
- No direct code copying from the old engine into TFIS core.
- Integrations should be optional filters or confirmations, not hidden hard dependencies.

## Operational Coordination Rules

- After every meaningful task, Codex must update:
  - `docs/operations/current_state.md` if implemented behavior, architecture,
    tests, or known limitations changed.
  - `docs/operations/next_steps.md` if task ordering, blockers, or next priority
    changed.
  - `docs/operations/milestones.md` for historical progress.
- If a document does not need an update for a given task, that must be stated
  explicitly in the task close-out.
- Operational coordination docs are part of the implementation discipline, not
  optional cleanup.

## Standard Codex Task Output Contract

Every meaningful task close-out should report:

- files changed
- behavior changed
- tests added or updated
- validation output
- current_state updated: yes or no
- next_steps updated: yes or no
- remaining open questions
- recommended next action
