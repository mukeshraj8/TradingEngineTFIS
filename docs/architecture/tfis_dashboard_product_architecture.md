# TFIS Dashboard Product Architecture

## Product Principles

- Operator-first: health, risk, positions, orders, and required action appear before technical detail.
- Shared truth: Operator Mode and Engineering Mode consume the same backend snapshot.
- Read-only by default: frontend does not calculate strategy rules or create authoritative trading state.
- Drill-down over clutter: primary pages stay human-readable; technical identifiers and raw detail remain secondary.
- Generic metadata: layout must support options, futures, equity, commodity, and currency without strategy-specific UI logic.

## Personas

1. Trading Operator
   - monitors health, positions, orders, margin, and alerts
   - needs quick actionability, not raw runtime detail

2. Strategy Reviewer
   - validates why the engine selected a branch, contract, entry state, and action
   - needs stepwise explanation and source trace

3. Risk Supervisor
   - monitors account state, limits, exposure, blocked entries, and warnings
   - needs current, limit, usage, remaining, and warning reason

## Product Modes

### Operator Mode

Primary navigation:

1. Command Centre
2. Strategies
3. Orders
4. Positions
5. Accounts
6. Risk
7. Historical Trades
8. Alerts
9. Audit
10. Settings

Purpose:

- daily operations
- health review
- order/position supervision
- account and risk review
- historical trade review

### Engineering Mode

Primary navigation:

1. Decision Explorer
2. Monthly Status
3. Contract Selection
4. Manual Validation
5. Replay
6. Explanation Library
7. Diagnostics
8. Source Trace

Purpose:

- explainability
- manual verification
- source trace
- reconstruction and diagnostics

Operator Mode and Engineering Mode must use the same snapshot truth and differ only in presentation and workflow depth.

## Navigation Map

### Operator Pages

- Command Centre: system home page
- Strategies: family hierarchy plus per-instance workbench
- Orders: compact order monitoring
- Positions: compact position monitoring
- Accounts: summary and controlled local configuration contract
- Risk: current, limit, usage, remaining, and warnings
- Historical Trades: trade history and trade story entry point
- Alerts: actionable attention items
- Audit: immutable control history
- Settings: projection metadata and raw snapshot

### Engineering Pages

- Decision Explorer: one strategy instance step-by-step
- Monthly Status: dedicated shared-engine review
- Contract Selection: candidate selection audit
- Manual Validation: local manual comparison
- Replay: reconstruction/replay availability
- Explanation Library: all immutable facts
- Diagnostics: raw technical detail
- Source Trace: workbook, rule, and evidence lineage

## Page Responsibilities

- Command Centre answers:
  - Is the system healthy?
  - What requires operator attention?
  - What positions, orders, and accounts need review now?
- Strategies answers:
  - Which strategy families and instances are active, blocked, or open?
  - What is the current state of one selected strategy instance?
- Orders answers:
  - Which orders exist and what requires follow-up?
- Positions answers:
  - Which positions are open, protected, carried, or stale?
- Accounts answers:
  - Which account is active, what are its limits, and what is locally configurable?
- Risk answers:
  - What are the current/limit/remaining states and why are there warnings?
- Historical Trades answers:
  - What happened in a prior or current trade and what evidence quality supports it?
- Alerts answers:
  - What requires acknowledgement or escalation?
- Audit answers:
  - What changed and who changed it?
- Settings answers:
  - What snapshot version and runtime metadata are in effect?

## Data Hierarchy

- unified dashboard snapshot
  - system
  - navigation
  - command centre
  - strategy family summaries
  - strategy instance summaries
  - orders
  - positions
  - accounts
  - risk
  - historical trades
  - decision explanations
  - alerts
  - audit
  - settings

Frontend consumes one stable projection and does not assemble business truth from unrelated raw objects.

## Strategy Hierarchy

Strategy Family
-> Strategy Definition
-> Strategy Instance
-> Instrument
-> Contract
-> Trade / Position

Families:

- Option Selling
- Option Buying
- Futures
- Equity
- Commodity
- Currency

## Strategies Experience At Scale

The `Strategies` surface must scale to one strategy family with many enabled
instrument instances, including S22 with 30 or more stocks and future
multi-account portfolios.

The required operator flow is three-level:

1. Strategy-definition summary
2. Compact instance list
3. Selected-instance workbench

### Strategy-definition summary

The landing view must summarize one row per strategy definition rather than one
large card per instance. Aggregates such as `Enabled`, `Prepared`,
`Entry Available`, `Open Positions`, `Blocked`, `No Trade`, `Daily Realized
P&L`, `Daily Unrealized P&L`, and `Margin Usage` must come from backend
projection fields, not browser-side derivation from table text.

### Compact instance list

When a definition is opened, the operator should see a compact, searchable,
filterable instrument-instance list with pagination and density controls.
Primary list behavior:

- search by instrument or selected contract
- filter by enabled state
- filter by runtime stage
- filter by Monthly Status
- filter by branch
- filter by health
- filter by evidence type
- filter by account
- sort by P&L, stage, and last update
- preserve saved views and current list context

This list must remain generic for:

- Option Selling
- Option Buying
- Futures
- Equity
- Commodity
- Currency

### Selected-instance workbench

The detailed workbench remains the place for step-by-step review of one
selected instance. It must preserve the parent list context and support:

- previous / next instance
- back to list
- retained search and filter state
- selected instrument clarity

The browser must not calculate business truth. It may only render backend
projection fields and immutable explainability facts.

## Account Hierarchy

Account
-> Broker/Data Mode
-> Limits
-> Usage
-> Allocations
-> Risk Warnings
-> Audit History

## User Flows

### Operator Flow

1. Open Command Centre
2. Review alerts, data health, positions, and pending actions
3. Open Strategies and select one strategy instance
4. Review workbench summary
5. Open Orders, Positions, Accounts, Risk, or Historical Trades as needed

### Engineering Flow

1. Switch to Engineering Mode
2. Open Decision Explorer for one selected strategy instance
3. Walk through Monthly Status -> Branch -> Contract Selection -> Entry -> ORPT/RC -> Protection -> Order -> Position -> P&L
4. Open Manual Validation, Explanation Library, Diagnostics, and Source Trace for deeper review

## State-Label Policy

- primary UI uses human-readable labels
- raw enums remain secondary technical detail only
- labels must be centrally mapped in backend/frontend display helpers

## Responsive Design

Target viewports:

- 1366 x 768
- 1600 x 900
- 1920 x 1080

Rules:

- no primary operator page should require mandatory horizontal scroll at 1600 width
- dense tables may scroll, but primary summaries must remain readable
- technical details move to secondary drawers/panels rather than primary rows

## Future Segment Compatibility

UI must render generic metadata for:

- Index Options
- Stock Options
- Futures
- Equity
- Commodity
- Currency

Business rules for non-option segments remain outside this dashboard milestone.

## Write Boundaries

Allowed in this milestone:

- local/internal-paper configuration contract only

Not allowed:

- broker credential editing
- broker authority changes
- live order enablement
- external paper/live financial mutation

## Accessibility

- meaningful empty states
- meaningful error states
- visible focus states
- readable typography at normal zoom
- keyboard-usable navigation and controls

## Explainability Integration

- Decision Explorer and Monthly Status pages render backend facts only
- frontend may format values, filter rows, compare local manual inputs, and expose drill-downs
- frontend must not calculate Monthly Status, contracts, prices, margin, P&L, or eligibility
