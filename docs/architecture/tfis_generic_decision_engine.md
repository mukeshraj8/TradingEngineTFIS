# TFIS Generic Decision Engine

Date: 2026-07-29

## Purpose

Phase 2A adds an isolated, product-neutral decision-orchestration foundation
between the Phase 1 `TFISRuntimeInput` and `TFISDecision` contracts. It does not
change current S21/S23 formulas or activate a new decision path in paper, live,
backtest, broker, order, persistence, or lifecycle code.

The design follows the FTAS AB15/AB16 boundary:

```text
StrategyInstanceConfig / external composition
                 |
                 v
          TFISRuntimeInput
                 |
                 v
   explicit PolicySelection + PolicyRegistry
                 |
                 v
          DecisionPolicySet
                 |
                 v
        TFISDecisionEngine
                 |
                 v
           TFISDecision
```

`TFISRuntimeInput` is the immutable AB15-equivalent input. `TFISDecision` is the
immutable AB16-equivalent result. The engine only coordinates already-selected
policies; it does not load strategy configuration, fetch data, calculate
Monthly Status, calculate rolling market structure, call a broker, persist
state, or construct an executable order.

## Package and Dependency Rules

The generic implementation lives in `src/tfis/decision`:

- `models.py`: immutable typed policy inputs and results
- `policies.py`: policy protocols
- `registry.py`: explicit name-based registration and composition
- `engine.py`: deterministic orchestration and fail-closed decision building

The package may depend on generic `tfis.domain` contracts and the Python
standard library. It must not depend on:

- `tfis.paper` or `tfis.backtest`
- `tfis.execution`
- `tfis.broker` or `tfis.brokers`
- S21/S23 rule, recalculation, or runtime modules
- strategy-code inspection
- persistence or dashboard code

Architecture tests scan these boundaries.

## Interfaces

The seven policy protocols are:

- `ProductPolicy`
- `EntryPolicy`
- `GapPolicy`
- `MissedEntryPolicy`
- `ContractSelectionPolicy`
- `TargetPolicy`
- `MSLPolicy`

Each protocol accepts a dedicated immutable input:

- `ProductPolicyInput`
- `EntryPolicyInput`
- `GapPolicyInput`
- `MissedEntryPolicyInput`
- `ContractSelectionPolicyInput`
- `TargetPolicyInput`
- `MSLPolicyInput`

Inputs include `TFISRuntimeInput` and only the preceding typed policy results
needed at that stage. Policies return one of:

- `ProductPolicyResult`
- `EntryPolicyResult`
- `GapPolicyResult`
- `MissedEntryPolicyResult`
- `ContractSelectionPolicyResult`
- `TargetPolicyResult`
- `MSLPolicyResult`

Every result inherits the immutable `PolicyResult` evidence envelope:

- policy name
- evaluation timestamp
- `PASSED`, `BLOCKED`, `UNAVAILABLE`, or `NOT_APPLICABLE`
- applicable flag
- business reason
- requirement ID
- formula and named reference
- calculated value
- input snapshot
- intermediate values
- quality status
- structured evidence

Product results additionally carry explicit product type, direction, execution
side, and branch. Entry results may carry a `TFISFormulaTrace`. Gap and
missed-entry results carry their selected branches. Contract-selection results
carry the selected generic contract identity and candidate count. Target and
MSL results carry decision evidence only; they do not execute exits or manage
positions.

## Explicit Policy Composition

`PolicyRegistry` is keyed by `(PolicyKind, policy_name)`. A composition layer
supplies a `PolicySelection` containing all five names. The registry does not:

- inspect `strategy_code`
- infer a policy from product type
- choose a default
- infer direction or execution side

Unknown names produce `None` in the composed `DecisionPolicySet`. The engine
detects any missing required policy before executing the first policy and emits
a rejected decision with `MISSING_REQUIRED_POLICIES`.

A Contract Selection policy is always explicitly composed. For a product that
does not require a distinct selection operation, the configured policy returns
`NOT_APPLICABLE`; the engine does not infer that outcome from product type.

## Orchestration

The execution order is fixed:

```text
1. Product
2. Entry
3. Gap
4. Missed Entry
5. Contract Selection
6. Target
7. MSL
```

Product and Entry must return applicable `PASSED` results. Gap, Missed Entry,
and Contract Selection may return `PASSED` or an explicit
`NOT_APPLICABLE`. `BLOCKED` produces `NO_TRADE`. `UNAVAILABLE`, an exception,
an invalid result type, a product mismatch, or an evaluation timestamp mismatch
produces `REJECTED`.

The engine takes product type from `TFISRuntimeInput` and verifies that the
Product policy agrees with it. Direction and execution side come only from the
Product policy. The engine contains no BUY/SELL, LONG/SHORT, Futures, Equity, or
option-selling default mapping.

## Monthly Status and Market Structure

Monthly Status is a required upstream dependency. The engine:

- consumes `TFISRuntimeInput.monthly_status`
- rejects `None` as `MONTHLY_STATUS_UNAVAILABLE`
- rejects `UNKNOWN` as `MONTHLY_STATUS_UNKNOWN`
- does not calculate, borrow, transition, group, or reinterpret Monthly Status

Policies consume named values from
`TFISRuntimeInput.market_structure_references`. They must not implement rolling
HH/LL calculations. Completed-candle semantics and lineage remain the
responsibility of the shared Market Structure Engine.

## Determinism and Evidence

The engine uses `TFISRuntimeInput.evaluated_at` as the decision time. Every
policy result must use the same evaluation timestamp. This prevents a replay
from changing merely because wall-clock time advanced.

The decision ID is a stable hash of the evaluation identity, ordered serialized
policy results, and any failure. `TFISDecision.intermediate_calculation_evidence`
records:

- fixed policy execution order
- policies actually executed
- complete ordered typed policy results
- resolved Monthly Status and its upstream evidence
- missing-policy evidence where relevant

Typed Gap and Missed Entry results are serialized into the existing
`TFISDecision.gap_result` and `missed_entry_result` mappings, preserving the
Phase 1 runtime contract.

## Compatibility Adapters

The existing Phase 1 adapters in
`src/tfis/paper/runtime_contract_adapters.py` remain unchanged. They continue
to map legacy S21/S23 paper inputs and outputs to the generic runtime contracts.

No new S21/S23 policy adapter is activated in Phase 2A. Current S21/S23
evaluation combines runtime derivation, formula evaluation, timing
recalculation, option-chain selection, and live-paper reporting in seams that
do not map one-to-one to the new protocols. Wrapping those paths prematurely
would either duplicate business logic or implicitly migrate the active
runtime. Phase 2B should add strategy-specific adapters only after parity
fixtures define each adapter boundary.

## Product Neutrality

`TFISRuntimeInput` and the new policy contracts support:

- Futures
- Option Selling
- Option Buying
- Equity
- BUY and SELL
- LONG and SHORT

Option-chain, strike, premium, and OI data remain optional in the generic
runtime input. Focused tests execute Futures and Equity decisions with no option
context and with both direction/side combinations supplied explicitly.

## Current Non-Goals

Phase 2A does not implement or change:

- active paper/live/backtest integration
- broker behavior or live order routing
- strategy formulas or workbook mappings
- Monthly Status transitions
- rolling market-structure calculations
- product-neutral order planning
- TSL, APS, target, or full lifecycle execution
- S23 start-strike formulas or fixtures
- onboarding of a Futures, Option Buying, or Equity strategy

## Remaining S21/S23 Coupling

Coupling remains in the legacy operational path:

- `S23RuntimeInputDeriver` supports the controlled S21/S23 runtime
- `S23PaperLiveDecisionBuilder` coordinates live-paper decisions
- S23 recalculation and missed-entry modules own current timing behavior
- `S23PaperContractSelector` owns current option-selling contract selection
- paper order/lifecycle/reporting paths retain current S23-first shapes

None of this coupling is imported by or activated through `tfis.decision`.

## Migration Path and Phase 2B

Recommended Phase 2B:

1. Define parity fixtures that capture existing S21 and S23 policy-stage
   inputs/results without changing formulas.
2. Add S21/S23 adapters outside the generic package, one independently tested
   policy seam at a time.
3. Add external strategy-instance-to-policy-name configuration and validation.
4. Compare new engine decisions against existing paper decision summaries in
   shadow/offline mode.
5. Keep active runtime selection unchanged until parity, failure-mode, and
   evidence tests pass.
6. Defer order planning and lifecycle migration to a later phase.
