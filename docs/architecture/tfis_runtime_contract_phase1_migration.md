# TFIS Runtime Contract Phase 1 Migration

Date: 2026-07-29

## Scope

Phase 1 introduces generic AB15-equivalent and AB16-equivalent runtime
contracts without changing S21 or S23 trading behavior.

This change does not add strategies and does not change formulas, thresholds,
gap logic, strike logic, monthly-status rules, broker behavior, paper fill
rules, or lifecycle behavior.

## Old Model / Path

- Runtime input reference packet:
  `src/tfis/paper/runtime_input_derivation.py::S23DecisionReferencePacket`
- Shared paper alias:
  `src/tfis/paper/runtime_input_derivation.py::PaperDecisionReferencePacket`
- Live-paper decision output:
  `src/tfis/paper/live_decision.py::S23PaperTradeDecisionSummary`
- Live-paper decision result:
  `src/tfis/paper/live_decision.py::S23PaperLiveDecisionResult`

Although S21 and S23 both use these paths, the concrete class names and several
implementation seams remain strategy-specific.

## New Model / Path

- Runtime input contract:
  `src/tfis/domain/runtime_contracts.py::TFISRuntimeInput`
- Decision contract:
  `src/tfis/domain/runtime_contracts.py::TFISDecision`
- Supporting generic domain values:
  `TFISProductType`, `TFISDirection`, `TFISExecutionSide`, `TFISTradeResult`,
  `TFISContractIdentity`, `TFISOptionChainContext`, `TFISFormulaTrace`, and
  `TFISPolicyResult`
- Compatibility adapters:
  `src/tfis/paper/runtime_contract_adapters.py`

The generic contracts are immutable dataclasses with deterministic `to_dict`,
`to_json`, and `comparison_key` methods for paper/replay comparison.

## Compatibility Layer

Existing paper paths continue to consume the current reference packet and
decision summary objects. Generic consumers can now use:

- `runtime_input_from_decision_reference_packet(...)`
- `legacy_reference_packet_from_runtime_input(...)`
- `decision_from_trade_decision_summary(...)`
- `decision_from_live_decision_result(...)`

`PaperRuntimeInput` now aliases `TFISRuntimeInput` while
`PaperDecisionReferencePacket` remains the legacy packet for behavior
preservation.

## Field Mapping: Legacy Reference Packet To TFISRuntimeInput

| Legacy field | New field |
| --- | --- |
| `instrument_group` | `monthly_status_evidence.instrument_group` |
| `monthly_status_levels.PMH/PML/CMH/CML/PWH/PWL/CWH/CWL` | `monthly_status_evidence.levels`, `current_month_references`, `current_week_references` |
| `market_reference_levels.d2hh/d2ll/d3hh/d3ll/d4hh/d4ll` | `market_structure_references` |
| `option_reference_values` | `option_chain_context.reference_values` and `runtime_values` |
| `runtime_value_overrides` | `gap_context.runtime_value_overrides` and `runtime_values` |
| `lots` | `lots` |
| `quantity` | `quantity` |
| `strategy_branch` | `strategy_branch` |
| `source_workbook_rule` | `provenance.source_workbook_rule` and `product_specific.source_workbook_rule` |
| `workbook_row_number` | `provenance.workbook_row_number` and `product_specific.workbook_row_number` |
| `fsl_price` | `product_specific.fsl_price` |
| `monthly_status_source` | `monthly_status_evidence.source` |
| `monthly_status_threshold_version` | `monthly_status_evidence.threshold_version` |
| `monthly_status_reference_date` | `monthly_status_evidence.reference_date` and default `session_date` fallback |
| `StrategyRule.strategy_code` | `strategy_code` |
| `StrategyRule.unique_code` | default `strategy_branch` |
| `StrategyRule.symbol` | `symbol` |
| `StrategyRule.segment` | `segment` and derived `product_type` |
| `StrategyRule.parameters/formulas` | `configuration_snapshot.strategy_rule` |

## Field Mapping: Existing Decision Output To TFISDecision

| Existing summary/result field | New field |
| --- | --- |
| `strategy_code` | `strategy_code` |
| `strategy_branch` | `strategy_branch` |
| `monthly_status` | `monthly_status_branch` |
| `status` | `trade_result` |
| selected contract symbol/expiry/strike/option type/LTP/OI | `selected_instrument` |
| current paper option-selling behavior | `execution_side=SELL`, `direction=SHORT` when a selected contract exists |
| `planned_entry_price` and formula explanation | `entry_calculation` |
| `explanation.orpt_rc_timing` | `gap_result` and `missed_entry_result` |
| `lots` | `lots` |
| `quantity` | `quantity` |
| `target_price` | `target_policy.result` |
| `stoploss_price` | `msl_policy.result` |
| `fsl_price` | `msl_policy.evidence.fsl_price` |
| no current generic TSL output | `tsl_policy.result=None` |
| no current generic APS output | `aps_policy.result=None` |
| governance/resume events | `final_exit_rule` |
| contract failure or blocked order reason | `rejection_reason_code` / `rejection_reason` |
| market levels, runtime values, aliases, candidates | `intermediate_calculation_evidence` |
| workbook rule and row | `configuration_versions` |
| full legacy result/summary | `compatibility_payload` |

## Before Flow

```text
strategy YAML
  -> StrategyRule
  -> S23DecisionReferencePacket / PaperDecisionReferencePacket
  -> S23RuntimeInputDeriver / PaperRuntimeInputDeriver
  -> S23PaperLiveDecisionBuilder
  -> S23PaperTradeDecisionSummary / S23PaperLiveDecisionResult
  -> paper order, ledger, dashboard, supervisor paths
```

## After Flow

```text
strategy YAML
  -> StrategyRule
  -> legacy paper reference packet
  -> compatibility adapter
  -> TFISRuntimeInput for generic consumers and replay comparison
  -> existing S21/S23 paper engines unchanged
  -> legacy paper decision summary/result
  -> compatibility adapter
  -> TFISDecision for generic consumers and replay comparison
  -> existing paper order, ledger, dashboard, supervisor paths unchanged
```

## Remaining Coupling

- `S23RuntimeInputDeriver` remains the concrete runtime deriver for both S23
  and the current controlled S21 path.
- `S23PaperLiveDecisionBuilder` still owns the live-paper decision workflow.
- Contract selection and paper order creation still assume the current
  option-selling behavior.
- Current-day gap / missed-entry logic remains embedded in the existing paper
  decision builder.
- TSL and APS are represented in the generic decision contract but are not yet
  populated by a generic policy engine.

## Certification Corrections

- The legacy compatibility adapter remains behavior-preserving for active
  paper runtime safety.
- Strict future-facing adapter functions now fail closed instead of guessing
  product type, direction, execution side, or strategy identity.
- Strict generic decisions retain selected-instrument segment and clear
  `rejection_reason` for successful trade/carry-forward outcomes while keeping
  selection rationale in structured evidence.
- Immutable lifecycle contract definitions now exist for `LifecyclePlan`,
  `TargetStep`, `StopPlan`, `TrailingStopStep`, `APSAction`, and `ExitRule`.
  These are contract definitions only and are not wired into active lifecycle
  runtime behavior.
- The four S23 `start_strike` test failures are classified as
  `PRE-EXISTING`, `NOT CAUSED BY PHASE 1`, and
  `WORKBOOK VERIFICATION PENDING`; fixtures, formulas, and strategy
  configuration remain unchanged.

## Next Remediation Step

Phase 2 should extract policy interfaces around monthly-status branch
selection, gap/missed-entry handling, strike/expiry selection, target/MSL/TSL/APS
calculation, and order-side resolution. That work should happen only after this
contract layer remains behaviorally stable under existing S21/S23 tests.
