# TFIS Business Capability Master Plan

Status: authoritative engineering roadmap for the remaining TFIS business
capability migration.

Date: Wednesday, July 29, 2026

Verdict: `MASTER_PLAN_ACCEPT`

This document is an implementation blueprint. It is not a marketing document,
not a theoretical architecture paper, and not an approval to activate runtime,
paper authority, or live-money routing.

## 1. Current Platform Status

TFIS now has the foundation needed to migrate the remaining business
capabilities in a controlled, auditable sequence. The key architectural work
already completed is:

- runtime contracts
- Generic Decision Engine
- Strategy Identity and Versioning
- Strategy Configuration Resolution
- Business Engine Framework
- Decision Evidence Packet
- Offline Parity Framework
- Gap and Missed-Entry Business Engine

The current platform shape is mature enough to stop treating S21/S23 behavior
as isolated script behavior and start migrating reusable business capabilities
behind explicit engine contracts. That migration must still remain staged:
offline first, then replay, then disabled shadow, then paper authority, and
only much later live-money authority.

### Completed

Phase 3A completed strategy identity and configuration resolution. Strategy
family, definition, version, instance, evaluation, and position-cycle identity
are explicit. The important outcome is that mutable state and evidence can now
be keyed by strategy instance and evaluation identity instead of loose strategy
codes or folder names.

Phase 3B completed the generic Business Engine Framework. Engines now have a
catalog shape, immutable definitions, required/provided capabilities,
dependency validation, evidence contracts, state expectations, performance
metadata, and deterministic registry validation. The initial catalog defines
the intended pipeline from Market Structure through Execution Intent.

Phase 3C completed the first migrated business capability: Gap and
Missed-Entry. It is certified for offline architecture and supported legacy
parity. It is not activated in runtime. It distinguishes gap output,
missed-entry output, and recalculation instruction, and keeps unresolved S23
PUT and S21 timing rules fail-closed.

Phase 2A through Phase 2D.1 completed the generic decision foundation,
legacy-policy adapter parity, captured/synthetic evidence posture, and
decision-evidence packet integration. These are the support systems that future
business engines must use for certification.

### In Progress

The migration from legacy strategy scripts to business engines is in progress.
Only the Gap/Missed-Entry engine has crossed the Phase 3 certification pattern.
Other catalog entries exist as contracts, not finished migrated business
engines.

Runtime activation is not in progress for the Gap/Missed-Entry engine. It
remains deferred. Disabled shadow, paper authority, and live-money authority
require additional gates.

Captured parity is still incomplete. Supported offline parity can pass with
synthetic golden, partial captured, and legacy fixture cases, but full captured
parity is not yet available across all relevant branches and profiles.

### Remaining

The remaining business capabilities to migrate are:

- Market Structure Engine
- Monthly Status Engine
- Entry Engine
- Contract Selection Engine
- Risk Engine
- Lifecycle Engine
- Execution Intent Engine
- final Decision composition and runtime orchestration
- Execution Adapter boundary for paper/live brokers

Some capabilities already exist in older forms. The migration task is not to
invent rules, but to extract the reusable capability, define typed contracts,
preserve current behavior where supported, and certify evidence/parity before
any runtime adoption.

## 2. Final TFIS Architecture

The final TFIS architecture should separate business decision-making from
runtime orchestration and broker execution.

```text
Strategy Registry / Instance Config
  -> Resolved Strategy Configuration
  -> Evaluation Identity
  -> Business Engine Pipeline
  -> Generic Decision Composition
  -> Decision Evidence Packet
  -> Runtime Readiness Gate
  -> Paper/Live Execution Adapter
```

The core rule is simple: business engines produce typed business facts and
instructions; runtime services decide when to call engines and how to persist
state; execution adapters translate approved execution intent to paper or
broker-specific actions.

### End-State Flow

```text
Market Data / Captured Evidence / Replay Fixture
  -> Normalized Runtime Input
  -> Strategy Identity Resolution
  -> Market Structure
  -> Monthly Status
  -> Gap and Missed Entry
  -> Entry
  -> Contract Selection
  -> Risk
  -> Lifecycle
  -> Execution Intent
  -> Decision
  -> Evidence Packet
  -> Runtime Gate
  -> Execution Adapter
```

Market data, captured evidence, and replay fixtures must be normalized before
they reach business engines. Engines should not fetch broker data, read
arbitrary files, or infer missing strategy configuration.

### Layering Rules

Business engines belong in generic/domain or clearly bounded strategy-policy
layers. They must not import broker SDKs, paper lifecycle, live execution,
dashboard code, or active runtime scripts.

Strategy-specific policy points may exist, but they must sit behind explicit
policy keys resolved by strategy definition and version. S23 on FYERS must not
become the hidden shape of the platform.

Runtime modules may orchestrate and observe engines only after the relevant
runtime activation milestone approves that stage. Until then, engines remain
offline or replay-only.

## 3. Business Engine Pipeline

The target execution order is:

```text
Market Structure
  -> Monthly Status
  -> Gap and Missed Entry
  -> Entry
  -> Contract Selection
  -> Risk
  -> Lifecycle
  -> Execution Intent
  -> Decision
  -> Execution Adapter
```

### Market Structure

Market Structure exists to produce reusable market context from supplied price
levels and timestamps. It should classify and expose market-level references
that later engines consume. It must not decide entry, select contracts, or
manage trades.

### Monthly Status

Monthly Status exists to produce instrument-driven monthly context. It is an
independent service, not part of S23. Monthly-status driven strategies consume
it to choose configured rule groups and branches.

### Gap And Missed Entry

Gap/Missed-Entry exists to evaluate supplied timing and observation evidence,
classify gap and missed-entry state, and emit recalculation instructions. It
does not own final entry formulas, target/stop logic, contract selection,
lifecycle, or execution authority.

### Entry

Entry exists to determine whether a strategy's base entry rule applies, whether
Gap/Missed-Entry output changes that path, whether evaluation must stop, and
which entry policy/formula result becomes authoritative for downstream
selection. It is the next major migration target.

### Contract Selection

Contract Selection exists to turn qualified entry intent into a product-specific
contract reference. For option strategies this includes option-chain candidate
selection, strike/premium/OI references, and near-versus-next contract logic
where configured.

### Risk

Risk exists to define target, stop, MSL, TSL, APS, sizing, and other risk
references after a contract and entry context are known. It must not place
orders or manage position lifecycle.

### Lifecycle

Lifecycle exists to evaluate position/order lifecycle state transitions using
approved business context and current state. It covers waiting, filled, held,
target, stop, expiry, force-close, rollover, and terminal states where those
rules are explicitly configured and certified.

### Execution Intent

Execution Intent exists to convert a lifecycle-approved action into a
broker-agnostic intent. It does not route orders. It produces the shape that a
paper or live adapter may later consume after gates pass.

### Decision

Decision composes engine outputs into a final auditable result:
trade/no-trade, selected contract, risk plan, lifecycle action, execution
intent, warnings, failures, and required operator action.

### Execution Adapter

Execution Adapter is outside the business engine core. It translates approved
broker-agnostic intent into paper state transitions or broker-specific API
actions. Broker SDK usage must remain here or in dedicated broker adapter
packages.

## 4. Business Engine Catalog

This section defines the target catalog contract for each engine. It extends
the Phase 3B catalog with implementation and certification expectations.

### Market Structure Engine

Purpose: classify reusable market context and expose named market references.

Inputs:

- normalized price context
- market levels
- evaluation timestamp
- optional session context
- optional higher timeframe context

Outputs:

- market structure state
- named market-level references
- quality and freshness assessment

State: stateless. It may cache immutable reference data outside evaluation, but
must not own mutable trading state.

Evidence:

- raw price context references
- derived market structure values
- timestamp and source provenance
- missing/stale level warnings

Dependencies: none.

Consumers:

- Monthly Status
- Gap/Missed-Entry
- Entry
- Contract Selection
- Risk where market references are needed

Supported products:

- futures
- option selling
- option buying
- equity

Supported strategy families:

- all families, subject to explicit product support

Strategy-specific policy points:

- product-specific level naming
- instrument-specific reference source
- strategy-specific required level set

Acceptance criteria:

- no broker/runtime imports
- immutable input/output models
- deterministic output for identical input
- fail-closed missing required levels
- provenance for every derived value

Certification criteria:

- architecture boundary tests
- behavior tests for supported product level sets
- evidence packet fragment
- parity against existing market-level behavior
- performance measurement
- runtime readiness matrix

Migration complexity: Medium.

### Monthly Status Engine

Purpose: produce instrument-driven monthly status as reusable market context.

Inputs:

- explicit monthly-status source
- instrument identity
- date/evaluation timestamp
- monthly/weekly/daily reference levels as configured
- optional market structure state

Outputs:

- monthly status
- branch trace
- display status
- warnings/failures

State: stateless for evaluation. Source datasets may be cached by the
orchestrator, not by mutable engine state.

Evidence:

- source bars/levels
- threshold version
- step-by-step status explanation
- missing/stale source warnings
- provenance

Dependencies:

- Market Structure when configured

Consumers:

- Gap/Missed-Entry
- Entry
- Contract Selection
- strategy branch selection

Supported products:

- futures
- option selling
- option buying
- equity

Supported strategy families:

- monthly-status driven strategies
- other strategies only when explicitly configured

Strategy-specific policy points:

- threshold versions
- source instrument selection
- branch mapping from monthly status to strategy rule group

Acceptance criteria:

- instrument-driven, not S23-specific
- explicit source and threshold version
- `UNKNOWN` only for incomplete/error cases
- no option-chain storage mixing
- deterministic evidence

Certification criteria:

- architecture boundary
- behavior coverage for status transitions
- captured evidence where available
- parity against current monthly-status outputs
- performance report
- runtime-readiness separation

Migration complexity: High, because current full-suite failures show monthly
status expectation drift that must be classified before authority.

### Gap And Missed-Entry Engine

Purpose: classify supplied gap and missed-entry evidence and emit downstream
recalculation instruction.

Inputs:

- session timing evidence
- policy key
- entry reference evidence
- monthly status
- market structure state
- ORPT/RC/current-day observations where required
- unresolved rule issues

Outputs:

- gap classification
- missed-entry state
- comparison source/operator/value/reference
- recalculation instruction
- unresolved issue evidence

State: stateless.

Evidence:

- timing evidence
- gap evidence
- missed-entry comparison evidence
- recalculation instruction evidence
- unresolved rule evidence
- typed decision-evidence packet fragment

Dependencies:

- Market Structure
- Monthly Status

Consumers:

- Entry Engine
- Decision Evidence Packet
- future shadow observer

Supported products:

- futures
- option selling
- option buying
- equity, as contract-capable placeholders

Supported strategy families:

- all families by generic contract, with executable behavior only where policy
  support is certified

Strategy-specific policy points:

- S21 evidence-only and unresolved timing profiles
- S23 backtest-low profile
- S23 paper/live-high profile
- S23 unresolved PUT fail-closed profile

Acceptance criteria:

- already met for offline architecture and supported legacy parity
- unresolved S23 PUT and S21 timing rules fail closed
- no runtime activation

Certification criteria:

- Phase 3C certification
- 8 cases, 8 passing supported comparisons, 0 mismatches, 2 fail-closed cases
- deterministic evidence integration

Migration complexity: Completed for offline. Runtime migration complexity:
Medium to High because captured parity and open rules remain blockers.

### Entry Engine

Purpose: decide whether entry applies after monthly status, market structure,
and Gap/Missed-Entry output are known.

Inputs:

- resolved strategy identity and version
- entry policy key
- market structure state
- monthly status
- gap/missed-entry output
- formula inputs
- current-day references supplied by upstream engines
- strategy parameters

Outputs:

- entry state
- base entry result
- effective entry result
- reason for no trade
- required downstream action
- warnings/failures

State: stateless.

Evidence:

- entry formula references
- input values
- policy key and version
- branch selection trace
- compatibility outputs consumed from Gap/Missed-Entry
- null-versus-zero preservation

Dependencies:

- Market Structure
- Monthly Status
- Gap/Missed-Entry

Consumers:

- Contract Selection
- Decision
- Evidence Packet

Supported products:

- futures
- option selling
- option buying
- equity

Supported strategy families:

- S21 and S23 first
- future Option Sell, Option Buy, Futures, and Equity only after strategy
  definitions exist

Strategy-specific policy points:

- S21 entry formulas by explicit strategy definition/version
- S23 entry formulas by explicit strategy definition/version
- future policies without generic engine changes

Acceptance criteria:

- no formulas invented
- current S21/S23 supported behavior reproduced offline
- Gap/Missed-Entry handoff honored
- no target/stop/contract selection included
- fail-closed unsupported formula/input cases

Certification criteria:

- architecture certification
- behavior matrix by strategy/profile/branch
- parity against legacy entry adapters
- evidence packet integration
- performance report
- runtime readiness matrix

Migration complexity: High. This is the next major dependency for downstream
engines.

### Contract Selection Engine

Purpose: convert qualified entry into selected contract/product references.

Inputs:

- entry state
- product reference
- option chain or product universe
- expiry rules
- premium/OI references
- near/next contract policy
- strategy identity

Outputs:

- selected contract
- candidate list
- rejection reasons
- product reference state
- no-selection result

State: stateless for evaluation. Candidate snapshots are supplied inputs.

Evidence:

- option-chain/product-universe snapshot reference
- candidate filtering trace
- selected contract trace
- expiry/strike/premium/OI evidence
- no-selection reasons

Dependencies:

- Entry

Consumers:

- Risk
- Lifecycle
- Execution Intent
- Decision

Supported products:

- option selling
- option buying
- futures
- equity

Supported strategy families:

- S21/S23 first for option selling
- future option buying/futures/equity after definitions exist

Strategy-specific policy points:

- S23 weekly option selling contract selection
- S21 monthly BankNifty selection
- expiry handling by strategy config
- product-specific lot/strike rules

Acceptance criteria:

- no broker SDK dependency
- option-chain evidence supplied, not fetched in core
- near contract first and next only if configured
- no trade when no valid contract exists
- current S21/S23 selected-contract behavior reproduced where certified

Certification criteria:

- architecture boundary
- branch/product behavior coverage
- captured and synthetic parity
- candidate evidence completeness
- performance with bounded candidate universe
- runtime readiness separation

Migration complexity: Very High, because it is strategy-sensitive and touches
option chain, expiry, OI, premium, and selected-contract evidence.

### Risk Engine

Purpose: compute or validate risk references for a selected business intent.

Inputs:

- selected contract
- effective entry
- risk configuration
- premium references
- market references
- strategy parameters
- position context where needed

Outputs:

- target plan
- stoploss plan
- MSL plan
- TSL plan
- APS/FSL references when configured
- risk state
- fail-closed no-authority result

State: stateless for initial risk calculation. Runtime trailing/adjusting risk
must use lifecycle state as supplied input.

Evidence:

- formula references
- target/stop calculations
- intermediate values
- risk configuration hash
- warnings/failures

Dependencies:

- Contract Selection
- Entry
- Market Structure where risk formulas need market refs

Consumers:

- Lifecycle
- Decision
- Execution Intent

Supported products:

- futures
- option selling
- option buying
- equity

Supported strategy families:

- S21/S23 first for target/MSL/FSL parity
- future families after rule definitions exist

Strategy-specific policy points:

- target formula
- SL/FSL/MSL/TSL/APS formula
- risk sizing rule
- carry-forward risk behavior

Acceptance criteria:

- no order placement
- no lifecycle transition ownership
- current supported risk outputs reproduced offline
- unsupported formulas fail closed
- risk evidence maps to packet

Certification criteria:

- architecture
- behavior
- evidence
- parity
- performance
- runtime readiness
- captured readiness
- live readiness

Migration complexity: High.

### Lifecycle Engine

Purpose: evaluate state transitions for waiting orders and open positions using
approved business context.

Inputs:

- risk state
- selected contract
- position/order state
- market event/quote/bar evidence
- session/expiry context
- strategy identity
- operator controls where applicable

Outputs:

- lifecycle state
- position state update
- order state update
- lifecycle action recommendation
- required operator action

State: read-only state during evaluation. Persistence remains owned by runtime
storage/orchestration, not the pure business engine.

Evidence:

- current persisted state reference
- market event evidence
- transition trace
- expiry/rollover/force-close evidence
- skipped action reasons
- stale/missing data evidence

Dependencies:

- Risk
- Contract Selection
- Entry

Consumers:

- Execution Intent
- Decision
- Paper runtime
- future live runtime gate

Supported products:

- futures
- option selling
- option buying
- equity

Supported strategy families:

- S21/S23 first for current paper lifecycle parity
- future families only with explicit lifecycle rules

Strategy-specific policy points:

- expiry behavior
- carry-forward
- rollover
- force-close
- target/stop/FSL order of operations
- waiting-order fill rules

Acceptance criteria:

- no live order routing
- no direct broker SDK access
- state identity keyed by strategy instance/trading date/position cycle
- transitions deterministic for supplied state/events
- missing/stale market data fails closed
- current paper behavior reproduced where certified

Certification criteria:

- architecture
- behavior by lifecycle state
- state/evidence parity
- restart/resume safety
- performance under repeated events
- runtime readiness gates

Migration complexity: Very High.

### Execution Intent Engine

Purpose: convert lifecycle-approved business state into broker-agnostic
execution intent.

Inputs:

- lifecycle state
- selected contract
- risk state
- position/order identity
- approved action
- strategy identity

Outputs:

- execution intent
- idempotency reference input
- action type
- quantity/side/product references
- broker-agnostic constraints
- no-action reason

State: stateless. Idempotency reservation and broker-order persistence belong
to execution/runtime services.

Evidence:

- lifecycle gate evidence
- selected contract identity
- risk/lifecycle references
- intent trace
- broker-agnostic completeness checks

Dependencies:

- Lifecycle

Consumers:

- Decision
- Paper adapter
- Live execution gate
- broker execution adapter

Supported products:

- futures
- option selling
- option buying
- equity

Supported strategy families:

- all configured families after upstream engines are certified

Strategy-specific policy points:

- allowed actions
- quantity sizing reference
- product-specific order intent fields
- strategy-specific operator approvals if configured

Acceptance criteria:

- no broker-specific fields in core intent
- no API routing
- no credential access
- idempotency input available
- fail-closed if lifecycle or selected contract is missing

Certification criteria:

- architecture
- behavior
- evidence
- paper-intent parity
- performance
- runtime readiness
- live gate readiness

Migration complexity: Medium after Lifecycle is complete; High before that.

### Decision Composition

Purpose: collect engine results into an auditable final decision.

Inputs:

- all engine outputs
- validation/failures/warnings
- strategy identity
- evaluation identity
- evidence fragments

Outputs:

- final TFIS decision
- no-trade/trade result
- action summary
- evidence packet
- runtime readiness classification

State: stateless.

Evidence:

- engine result references
- composed evidence packet
- policy keys
- requirement IDs
- data quality warnings

Dependencies:

- all engines up to Execution Intent

Consumers:

- offline reports
- replay reports
- runtime observer
- paper/live gates
- dashboard

Supported products:

- all configured products with certified engine support

Acceptance criteria:

- deterministic packet
- no hidden behavior inference
- fail-closed if any required engine fails closed
- clear operator-visible reason codes

Certification criteria:

- composition tests
- evidence round-trip
- parity against legacy decision outputs
- runtime readiness matrix

Migration complexity: Medium.

### Execution Adapter

Purpose: translate approved execution intent into paper state changes or
broker-specific actions.

Inputs:

- approved execution intent
- runtime gate result
- idempotency reservation
- operator controls
- adapter configuration

Outputs:

- paper order/position update, or broker order request/result
- adapter evidence
- rejection/failure evidence

State: runtime-owned, not business-engine-owned.

Evidence:

- idempotency
- broker/paper action
- acknowledgements
- fills/rejects
- reconciliation evidence

Dependencies:

- Execution Intent
- runtime gates
- adapter configuration

Consumers:

- paper runtime
- live runtime
- reconciliation
- dashboard

Supported products:

- only products certified by upstream engines and adapter capability

Acceptance criteria:

- broker-specific code isolated
- live routing disabled by default
- paper mimics real execution behavior
- broker truth and reconciliation required for live

Certification criteria:

- adapter boundary tests
- paper behavior certification
- live gate review
- broker truth/reconciliation evidence
- operator approval/kill switch

Migration complexity: Very High for live; Medium for paper once upstream
intent is certified.

## 5. Dependency Graph

The intended graph is acyclic:

```text
market_structure
monthly_status depends on market_structure
gap depends on market_structure, monthly_status
entry depends on market_structure, monthly_status, gap
contract_selection depends on entry
risk depends on contract_selection
lifecycle depends on risk
execution_intent depends on lifecycle
decision depends on all engine outputs
execution_adapter depends on execution_intent and runtime gates
```

Visual form:

```text
market_structure
  -> monthly_status
    -> gap
      -> entry
        -> contract_selection
          -> risk
            -> lifecycle
              -> execution_intent
                -> decision
                  -> execution_adapter
```

No engine may depend on a downstream engine. The most important cycle risks
are:

- Entry trying to call Contract Selection to decide whether entry is valid.
- Risk trying to select a new contract after risk calculation fails.
- Lifecycle trying to mutate Risk formulas after a position event.
- Execution Intent trying to query broker state directly.
- Monthly Status using option-chain data from Contract Selection.

Cycle detection must remain part of the catalog validation. Any future engine
or capability must declare dependencies and provided capabilities explicitly.

## 6. Capability Matrix

Legend:

- `P`: provides
- `C`: consumes
- `-`: not applicable

| Engine | MARKET_STRUCTURE | MONTHLY_STATUS | GAP | MISSED_ENTRY | ENTRY | OPTION_CHAIN | STRIKE_SELECTION | PREMIUM_REFERENCE | OI_REFERENCE | TARGET | MSL | TSL | APS | RISK | LIFECYCLE | POSITION_STATE | EXECUTION_INTENT | EXECUTION |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Market Structure | P | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| Monthly Status | C | P | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| Gap/Missed-Entry | C | C | P | P | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| Entry | C | C | C | C/P | P | - | - | - | - | - | - | - | - | - | - | - | - | - |
| Contract Selection | - | - | - | - | C | P | P | P | P | - | - | - | - | - | - | - | - | - |
| Risk | C | - | - | - | C | C | C | C | C | P | P | P | P | P | - | - | - | - |
| Lifecycle | - | - | - | - | C | - | C | - | - | C | C | C | C | C | P | P | - | - |
| Execution Intent | - | - | - | - | - | - | C | - | - | C | C | C | C | C | C | C | P | P |
| Decision | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| Execution Adapter | - | - | - | - | - | - | C | - | - | C | C | C | C | C | C | C | C | P |

Entry is allowed to consume `MISSED_ENTRY` from Gap/Missed-Entry and may also
produce an effective entry-level missed-entry status for decision composition.
That must not re-open the S23 PUT authority question; the authoritative
comparison source remains upstream policy evidence until resolved.

## 7. Strategy Mapping

This mapping defines engine requirements. It does not invent formulas or
declare unsupported strategy behavior.

| Strategy/family | Market Structure | Monthly Status | Gap/Missed-Entry | Entry | Contract Selection | Risk | Lifecycle | Execution Intent | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S21 | Required where configured | Required if workbook/config says monthly-status driven | Evidence-only or unresolved until S21 timing clarified | Required | Required for BankNifty monthly option selling | Required | Required for paper/later live | Required after lifecycle | Do not invent S21 gap rules |
| S23 | Required | Required | Certified offline, runtime deferred | Required next | Required for NIFTY weekly option selling | Required | Required | Required | S23 PUT authority unresolved |
| Future Option Sell | Required | Optional/required by strategy definition | Optional/required by strategy definition | Required | Required | Required | Required | Required | Must use explicit strategy definition/version |
| Option Buy | Required | Optional/required by strategy definition | Optional/required by strategy definition | Required | Required | Required | Required | Required | No current formulas certified |
| Futures | Required | Optional/required by strategy definition | Optional/required by strategy definition | Required | Product reference selection required | Required | Required | Required | No futures strategy rules invented |
| Equity | Required | Optional/required by strategy definition | Usually optional unless strategy defines it | Required | Equity symbol selection or validation | Required | Required | Required | No equity strategy rules invented |

S21 and S23 are the first concrete strategies because they have current
configuration and legacy behavior. Option Buy, Futures, and Equity remain
family placeholders until explicit strategy definitions, rule sources, and
certification fixtures exist.

## 8. Migration Order

Recommended implementation order:

1. Entry Engine
2. Market Structure Engine
3. Monthly Status Engine
4. Contract Selection Engine
5. Risk Engine
6. Lifecycle Engine
7. Execution Intent Engine
8. Decision composition migration
9. Disabled runtime shadow
10. Paper authority
11. Live-money readiness

This differs slightly from the pure dependency order because some upstream
capabilities already exist operationally, while Entry is the immediate
downstream consumer of the completed Gap/Missed-Entry engine. The plan should
avoid blocking Phase 3D on a full rewrite of Market Structure and Monthly
Status, but Phase 3D must use explicit supplied upstream observations and must
not hardcode S23.

### Phase 3D: Entry Engine

Complexity: High.

Why next: Gap/Missed-Entry now emits recalculation instructions. Entry is the
consumer that decides whether base entry applies, whether recalculation output
can be used, and whether evaluation must stop.

Scope:

- generic Entry Engine contract
- S21/S23 compatibility policies
- offline parity
- evidence packet integration
- no runtime activation

### Phase 3E: Market Structure Certification

Complexity: Medium.

Why next: Market Structure is an upstream dependency for Monthly Status, Gap,
Entry, and some Risk calculations. Certifying it reduces repeated ad hoc market
reference handling.

Scope:

- typed market reference contract
- current behavior inventory
- deterministic evidence
- parity where available

### Phase 3F: Monthly Status Certification

Complexity: High.

Why next: Monthly Status determines S21/S23 branch mapping and must be
instrument-driven. Existing full-suite monthly-status expectation failures
should be resolved or classified before runtime authority.

Scope:

- source selection contract
- status transition behavior
- branch mapping evidence
- captured/replay certification

### Phase 3G: Contract Selection Engine

Complexity: Very High.

Why next: After Entry, TFIS needs a generic way to select contracts without
hardcoding S23/FYERS assumptions.

Scope:

- option-chain/product universe contract
- candidate/rejection evidence
- expiry/strike/premium/OI policy boundaries
- near/next selection behavior
- S21/S23 parity

### Phase 3H: Risk Engine

Complexity: High.

Why next: Risk depends on selected contract and entry. Target, SL, MSL, TSL,
FSL, APS, and sizing must be separated from entry and lifecycle.

Scope:

- target/stop/risk result contracts
- S21/S23 risk-policy parity
- evidence packet fragments
- fail-closed unsupported formula handling

### Phase 3I: Lifecycle Engine

Complexity: Very High.

Why next: Lifecycle is where runtime state and market events meet business
rules. It must be isolated and certified before paper authority.

Scope:

- waiting order lifecycle
- open position lifecycle
- expiry/force-close/rollover
- restart/resume state evidence
- paper parity

### Phase 3J: Execution Intent Engine

Complexity: Medium after lifecycle, High before lifecycle.

Why next: Execution Intent converts approved lifecycle action into a
broker-agnostic action shape. It is the final business engine before adapter
boundaries.

Scope:

- broker-agnostic intent contract
- no broker SDK imports
- idempotency input references
- paper/live gate inputs

### Phase 3K: Decision Composition

Complexity: Medium.

Why next: Once engines are certified, their outputs must be composed into one
operator-visible decision and evidence packet.

Scope:

- engine result aggregation
- deterministic packet
- no-trade/trade decision summary
- dashboard/operator evidence model

### Phase 4: Runtime Shadow

Complexity: High.

Why next: Only after offline and replay certification should runtime observe
new engines alongside legacy behavior.

Scope:

- disabled additive observer
- no decision authority
- captured comparison reports
- operator visibility

### Phase 5: Paper Authority

Complexity: Very High.

Why next: Paper authority changes behavior and must wait for stable shadow
evidence.

Scope:

- engine-driven paper decisions
- waiting-order semantics
- fill simulation
- lifecycle parity
- rollback plan

### Phase 6: Live-Money Readiness

Complexity: Very High.

Why last: Live money requires broker truth, idempotency, operator controls,
kill switch, reconciliation, event ingress, and proven paper authority.

Scope:

- reviewed enablement only
- live execution gate
- broker adapter certification
- reconciliation evidence

## 9. Certification Process

Every engine must finish with a certification report. The report should produce
machine-readable JSON and a human-readable Markdown summary.

Required certification sections:

- architecture
- behavior
- evidence
- parity
- performance
- runtime readiness
- captured readiness
- live readiness

### Architecture Certification

Prove:

- generic engine imports no strategy-specific modules
- generic engine imports no broker/runtime/paper/live/backtest modules
- strategy-specific policy code is isolated
- no default policy profile is inferred
- no mutable global engine state exists
- outputs are immutable
- catalog dependencies are valid
- no active runtime path invokes the engine unless the phase explicitly allows
  it

### Behavior Certification

For each strategy/profile/branch:

- supported inputs
- outputs
- fail-closed cases
- unsupported cases
- evidence classification
- known unresolved issues

Do not certify behavior that has not been proven.

### Evidence Certification

Every engine must preserve:

- strategy identity
- policy key
- configuration hash
- input values
- observed/reference values
- formula/requirement references
- provenance
- warnings/failures
- unresolved issues

### Parity Certification

Every migrated behavior must compare generic output with legacy behavior where
legacy behavior exists. Mismatches must be classified. Supported behavior must
have zero unexplained mismatches before runtime shadow.

### Performance Certification

Record:

- sample count
- environment
- validation time
- execution time
- policy resolution time
- serialization time
- artifact size
- deterministic repeat behavior

Do not extrapolate offline timings into live-money throughput.

### Runtime Readiness Certification

Use separate verdicts:

- Offline
- Replay
- Disabled Shadow
- Paper Authority
- Live Money

One broad "ready" statement is prohibited.

## 10. Runtime Activation Roadmap

Runtime activation has five stages.

### Stage 1: Offline

Entry criteria:

- architecture contract complete
- immutable models complete
- deterministic unit tests
- no runtime imports
- offline fixtures available

Permitted behavior:

- unit tests
- fixture tests
- generated reports

Prohibited behavior:

- runtime invocation
- paper authority
- live authority

### Stage 2: Replay

Entry criteria:

- offline certification accepted
- replay/captured input mapping available
- deterministic replay report
- known evidence gaps documented

Permitted behavior:

- replay evaluation
- comparison reports
- no-op evidence generation

Prohibited behavior:

- runtime decision authority
- broker calls from engines

### Stage 3: Disabled Shadow

Entry criteria:

- replay certification accepted
- captured evidence adequate or supplemental evidence approved
- no unexplained supported mismatches
- operator-visible shadow report
- rollback/no-op guarantee

Permitted behavior:

- additive runtime observer
- captured comparison
- no changes to decisions/orders

Prohibited behavior:

- altering paper order creation
- changing lifecycle
- live routing

### Stage 4: Paper Authority

Entry criteria:

- shadow reports stable
- operator review accepted
- paper-specific parity complete
- failure/rollback path proven
- dashboard evidence ready

Permitted behavior:

- engine output may drive paper decisions
- waiting paper orders only where strategy config allows

Prohibited behavior:

- live orders
- unreviewed strategy behavior changes

### Stage 5: Live

Entry criteria:

- paper authority stable
- live execution gate passes
- broker truth supplied
- broker-event/websocket ingress proven
- idempotency active
- reconciliation active
- operator approval active
- kill switch active
- separate go/no-go review accepted

Permitted behavior:

- reviewed live adapter routing within approved scope

Prohibited behavior:

- default live enablement
- bypassing broker truth/reconciliation/operator controls

## 11. Money Readiness Gates

### Before Runtime Shadow

Required:

- engine offline certification accepted
- replay/captured evidence mapped
- no unexplained supported parity mismatches
- open rules either fail closed or are explicitly excluded
- runtime observer is additive and no-op
- dashboard/reporting shows shadow result separately

Current blockers:

- S23 PUT authoritative comparison
- S21 ORPT/RC applicability
- incomplete full captured parity for Gap/Missed-Entry

### Before Paper Authority

Required:

- disabled shadow evidence stable
- paper behavior parity complete
- waiting-order semantics preserved
- lifecycle interaction certified
- fail-closed behavior operator-visible
- rollback to legacy paper path available

Current blockers:

- not all engines migrated
- Lifecycle and Execution Intent not certified
- disabled shadow not complete

### Before Live Money

Required:

- paper authority accepted
- live execution gate enabled by reviewed change
- broker truth evidence
- broker event/websocket ingress
- idempotency
- reconciliation
- operator approval
- kill switch
- live adapter boundary certification

Current blockers:

- live-money routing disabled by project contract
- paper authority not complete
- full engine pipeline not certified

## 12. Open Rule Register

Known unresolved business rules and evidence gaps:

| ID | Area | Status | Safe behavior | Blocks |
| --- | --- | --- | --- | --- |
| TFIS-GME-OPEN-001 | S23 PUT missed-entry authoritative comparison | `LEGACY_INCONSISTENCY`, `WORKBOOK_VERIFICATION_REQUIRED`, `USER_CLARIFICATION_REQUIRED` | unresolved profile fails closed | runtime shadow, paper, live |
| TFIS-GME-OPEN-002 | S21 ORPT/RC applicability | `INSUFFICIENT_EVIDENCE`, `USER_CLARIFICATION_REQUIRED` | evidence-only or fail closed | runtime shadow, paper, live |
| TFIS-GME-OPEN-003 | Full captured Gap/Missed-Entry parity | evidence/capture gap | offline only unless approved evidence supplement | runtime shadow, paper, live |
| TFIS-MONTHLY-OPEN-001 | Monthly-status expectation drift | requires verification | classify before authority | monthly-status authority |
| TFIS-S23-OPEN-001 | S23 strike/workbook expectation failures | `WORKBOOK_VERIFICATION_PENDING` | do not change formulas silently | contract selection/risk/paper authority |
| TFIS-LIFECYCLE-OPEN-001 | Historical lifecycle fixture expectation drift | requires classification | keep lifecycle migration separate | lifecycle authority |

Future phases may add or close open rules, but they must not silently remove
them.

## 13. Project Risks

### Technical Risks

- hidden S23 assumptions leaking into generic engines
- broker/FYERS dependencies entering core modules
- policy resolution by family/display name instead of definition/version
- incomplete evidence causing false parity confidence
- mutable runtime state keyed too broadly
- replay and runtime paths diverging
- unbounded option-chain scans affecting performance
- lifecycle side effects creeping into pure business engines

Mitigations:

- architecture boundary tests
- explicit catalog dependencies
- immutable identity and configuration hashes
- evidence classification
- deterministic reports
- staged runtime activation

### Business Risks

- S23 PUT low/high rule ambiguity
- S21 gap/timing ambiguity
- workbook expectation drift
- incomplete captured evidence
- future strategies lacking source rule definitions
- treating placeholders as implemented capability

Mitigations:

- open-rule register
- fail-closed unresolved policies
- user/workbook confirmation gates
- no unsupported formula invention
- separate readiness verdicts

### Operational Risks

- confusing paper readiness with live-money readiness
- dashboard hiding shadow-vs-authority distinctions
- runtime activation before operator evidence exists
- stale/missing market data driving lifecycle decisions
- live adapter routing without broker truth and reconciliation

Mitigations:

- runtime activation roadmap
- money readiness gates
- operator-visible evidence
- live execution gate
- kill switch and approval controls

## 14. Recommended Remaining Roadmap

### Phase 3D: Entry Engine

Goal: implement and certify the generic Entry Engine as the downstream consumer
of Gap/Missed-Entry output.

Deliverables:

- authoritative Entry Engine specification
- immutable entry input/result/evidence models
- S21/S23 compatibility policies
- parity report
- evidence packet integration
- no runtime activation

Exit verdict:

- `PHASE_3D_ACCEPT`, `PHASE_3D_CONDITIONAL`, or `PHASE_3D_REJECT`

### Phase 3E: Market Structure Engine Certification

Goal: certify reusable market-level context so downstream engines stop
duplicating market reference handling.

Deliverables:

- market structure contract
- behavior inventory
- parity report
- source/evidence classification

### Phase 3F: Monthly Status Engine Certification

Goal: certify Monthly Status as an independent instrument-driven business
engine.

Deliverables:

- monthly status source contract
- threshold/version evidence
- branch trace evidence
- parity/captured report
- classification of existing monthly-status expectation drift

### Phase 3G: Contract Selection Engine

Goal: migrate selected-contract logic behind a generic contract selection
capability.

Deliverables:

- candidate contract model
- selected contract result
- rejection/no-selection evidence
- S21/S23 parity
- expiry/strike/premium/OI policy boundaries

### Phase 3H: Risk Engine

Goal: migrate target, stop, MSL, TSL, APS, FSL, and sizing references behind a
generic risk capability.

Deliverables:

- risk result model
- risk evidence fragment
- formula parity
- unsupported formula fail-closed tests

### Phase 3I: Lifecycle Engine

Goal: migrate waiting-order and open-position state transition rules behind a
generic lifecycle capability.

Deliverables:

- lifecycle state input/result
- transition evidence
- expiry/rollover/force-close contracts
- restart/resume state certification
- paper parity

### Phase 3J: Execution Intent Engine

Goal: convert lifecycle-approved actions into broker-agnostic execution intent.

Deliverables:

- intent model
- idempotency input reference
- no broker SDK imports
- paper/live gate evidence

### Phase 3K: Decision Composition

Goal: compose engine outputs into the final generic decision and evidence
packet.

Deliverables:

- engine result aggregator
- deterministic packet
- no-trade/trade summary
- dashboard/operator evidence model

### Phase 4A: Offline Full-Pipeline Replay

Goal: run the full business-engine pipeline offline against deterministic
fixtures and captured data.

Deliverables:

- full-pipeline replay report
- mismatch taxonomy
- performance report
- captured evidence inventory

### Phase 4B: Disabled Runtime Shadow

Goal: observe the engine pipeline beside legacy runtime without changing
decisions.

Deliverables:

- additive observer
- shadow reports
- operator dashboard distinction
- no-op guarantee

### Phase 5A: Paper Authority Migration

Goal: allow certified engine outputs to drive paper decisions after shadow
evidence is accepted.

Deliverables:

- paper authority gate
- rollback plan
- lifecycle parity
- operator status

### Phase 6A: Live-Money Readiness Review

Goal: decide whether a narrow live-money enablement change can be considered.

Deliverables:

- go/no-go review
- live execution gate evidence
- broker truth and reconciliation evidence
- operator approval and kill-switch evidence
- adapter certification

## Master Acceptance Criteria

The roadmap is acceptable if it:

- preserves Phase 3A identity and versioning
- preserves Phase 3B business-engine catalog direction
- preserves Phase 3C Gap/Missed-Entry certification boundaries
- does not invent unsupported business rules
- keeps S21/S23 specificity behind policy boundaries
- keeps broker dependencies out of core
- separates offline, replay, shadow, paper, and live readiness
- identifies unresolved rules and evidence gaps
- recommends a concrete remaining implementation order

## Final Verdict

`MASTER_PLAN_ACCEPT`

The recommended next implementation phase is Phase 3D: Entry Engine. It should
remain offline-only until independently certified and explicitly approved for a
later runtime stage.
