# TFIS Phase 2C Offline Shadow Parity

Date: 2026-07-29

## Objective

Phase 2C extends the isolated generic decision path with Target and MSL policy
stages and strengthens offline shadow parity for current S21/S23 decisions.
The work remains offline only. No paper, live, replay, backtest, broker,
dashboard, lifecycle, persistence, or scheduled-job caller is activated through
`TFISDecisionEngine`.

## Authoritative Inputs

- `docs/TFIS_FTAS_v0.7_Business_Engines_Market_Data_Structure_Monthly_Status.docx`
- `docs/specification/TFIS_Monthly_Status_Reference_and_Implementation_Specification_v1.0.docx`

Monthly Status is supplied upstream through `TFISRuntimeInput`. S21/S23 policy
adapters do not calculate, borrow, transition, collapse, or reinterpret it.

## Decision Stage Order

```text
TFISRuntimeInput
  -> ProductPolicy
  -> EntryPolicy
  -> GapPolicy
  -> MissedEntryPolicy
  -> ContractSelectionPolicy
  -> TargetPolicy
  -> MSLPolicy
  -> TFISDecision
```

The generic engine fails closed for missing policy selection, policy errors,
unexpected result types, unavailable required evidence, timestamp drift, and
UNKNOWN or missing Monthly Status. A blocked/no-trade stage stops downstream
execution.

## Target Model

`TargetPolicyResult` is an immutable policy result with ordered
`TargetPolicyTarget` entries. It can represent:

- no target through explicit `NOT_APPLICABLE`
- one target
- multiple ordered targets
- target formula/reference
- target price
- quantity or quantity percentage
- activation order
- intermediate values and evidence

Phase 2C S21/S23 adapters preserve the current single target from
`StrategyEvaluator` trade-plan output. They do not execute targets or manage
positions.

## MSL Model

`MSLPolicyResult` is an immutable policy result for initial/main stop-loss
evidence. It records formula/reference, stop price, direction, activation
timing, quantity scope, intermediate values, quality, and reason.

Phase 2C S21/S23 adapters preserve the current `stoploss_price` from
`StrategyEvaluator` trade-plan output. They do not execute stops, TSL, APS, or
final exits.

## Composition Configuration

`config/strategy_policy_composition.yaml` maps each current S21/S23 strategy
instance to explicit policy keys:

- product
- entry
- gap
- missed entry
- contract selection
- target
- MSL

`load_strategy_policy_composition_config()` validates that all mandatory keys
are present and non-empty. There are no default policy selections in the
generic engine or registry.

## Evidence Inventory

Captured repository evidence:

- `tests/fixtures/paper/s23_fyers_prelude.jsonl`
  - captured: yes
  - branch: `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT`
  - includes Monthly Status, ORPT snapshot, RC snapshot, and trade plan with
    target/MSL
  - does not include option-chain snapshot, so full contract-selection parity
    still requires synthetic option-chain evidence
- `tests/fixtures/paper/s23_archive_ingress_dry_run.jsonl`
  - same captured archive family and usable as captured paper event evidence

Synthetic deterministic evidence:

- all S21 branch parity option-chain inputs
- all S23 branch parity option-chain inputs
- S21 branch-level runtime inputs, because no active S21 captured paper
  contract-discovery evidence is present in repo fixtures
- S23 branch folders other than the captured Bear Put prelude branch

## Parity Methodology

`run_legacy_policy_parity()` evaluates:

1. current legacy `StrategyEvaluator`
2. current legacy option-chain selector
3. `TFISRuntimeInput -> TFISDecisionEngine -> TFISDecision` through legacy
   policy adapters
4. field-level equality for strategy branch, Monthly Status, trade result,
   product, direction, side, entry, gap/missed evidence, selected expiry,
   strike, premium/LTP, OI, target, MSL, lots, quantity, and final reason

Known S23 start-strike workbook expectation failures remain:
`PRE_EXISTING`, `WORKBOOK_VERIFICATION_PENDING`,
`NOT_PHASE_2B_OR_2C_REGRESSION`. Shadow parity compares legacy actual output
to generic actual output and does not modify formulas or expected fixtures.

## Mismatch Classification

The parity result carries field-level mismatch classifications:

- `ADAPTER_DEFECT`
- `GENERIC_MODEL_GAP`
- `LEGACY_INCONSISTENCY`
- `WORKBOOK_VERIFICATION_REQUIRED`
- `INSUFFICIENT_EVIDENCE`

Current deterministic parity has no mismatches between legacy actual and
generic-adapter actual for covered fields.

## Known Limitations

- Captured S23 prelude evidence in the repository is partial because it lacks a
  saved option-chain snapshot.
- Real S23 ORPT/RC derivation remains in the legacy paper decision builder; the
  adapter preserves supplied ORPT/RC evidence but does not recompute it.
- Target/MSL are modeled as decision evidence only. No target, stop, TSL, APS,
  final-exit, order-planner, or lifecycle execution is implemented.
- Active runtime coupling remains unchanged.

## Phase 2D Readiness

Recommended Phase 2D should stay offline unless explicitly approved:

1. add captured option-chain evidence to the saved S23 Bear Put fixture
2. add full saved S23 live-decision summary parity, including ORPT/RC timing
   derivation outputs
3. add S21 captured paper evidence before claiming operational S21 parity
4. compare generic decisions against saved legacy decision summaries in shadow
   reports
5. only after reviewed parity, consider a disabled runtime shadow mode
