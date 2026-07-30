# Phase 3D Milestone 4 S23 Bear Call Summary

## Verdict

PHASE3D_M4_ACCEPT

## Evidence Classification

S23 Bear Call uses a synthetic golden case. It is not captured parity and does
not claim runtime, paper, live, broker, lifecycle, risk, or execution authority.

## Bear Call Case

- Strategy family: S23
- Strategy definition: S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL
- Strategy branch: NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL
- Monthly Status: BEAR
- Option side: CALL
- Selected contract: NIFTY_20260806_22150_CALL
- Selected expiry: 2026-08-06
- Selected strike: 22150.0
- Premium: 262.8
- OI: 999999.0
- Base Entry: 194.25
- Gap/Missed-Entry: NOT_MISSED
- Effective Entry: 194.25
- Target: 77.7
- MSL: 310.8
- Final decision: TRADE

## Pipeline Executed

strategy_resolution -> monthly_status_and_branch -> underlying_references -> contract_selection -> base_entry -> gap_missed_entry -> effective_entry -> target_msl -> decision -> evidence_packet -> legacy_comparison

## Implementation Map

- Strategy Resolution -> S23ProductPolicyAdapter -> ProductPolicyResult -> blocks on UNKNOWN_S23_BRANCH
- Underlying References -> S23EntryPolicyAdapter + StrategyEvaluator -> EntryPolicyResult -> blocks on UNDERLYING_REFERENCE_FAILURE
- Contract Selection -> S23ContractSelectionPolicyAdapter -> ContractSelectionPolicyResult -> blocks on NO_QUALIFYING_CONTRACT
- Base Entry -> EntryEngine + S23VerticalEntryPolicy -> EntryEngineResult -> blocks on BASE_ENTRY_FAILURE
- Gap/Missed Entry -> evaluate_legacy_gap_missed_entry -> GapMissedEntryEngineResult -> blocks on GAP_MISSED_ENTRY_BLOCKED
- Effective Entry -> EntryEngine + S23VerticalEntryPolicy -> EntryEngineResult -> blocks on EFFECTIVE_ENTRY_FAILURE
- Target/MSL -> S23TargetPolicyAdapter + S23MSLPolicyAdapter -> TargetPolicyResult + MSLPolicyResult -> blocks on TARGET_ADAPTER_FAILURE / MSL_ADAPTER_FAILURE
- Decision and Evidence Packet -> TFISDecision + TFISDecisionEvidencePacket -> TFISDecision + TFISDecisionEvidencePacket -> blocks on evidence packet validation failure

## Reused Components

- OfflineStrategyDecisionOrchestrator
- S23 Product, Entry, Contract Selection, Target, and MSL compatibility adapters
- Generic EntryEngine
- Phase 3C S23 Gap/Missed-Entry backtest-low compatibility policy: legacy.s23.gap_missed_entry.backtest_low_v1
- TFISDecision
- TFISDecisionEvidencePacket

## S23 Compatibility Changes

- Replaced Bull Call constants in the S23 vertical composition with immutable
  branch specs.
- Added Bear Call as a second branch spec and synthetic golden case.
- Kept the Entry policy key unchanged: legacy.s23.vertical.entry.

## Generic Orchestrator Changes

NONE.

The existing orchestrator supported Bear Call as-is; the limitation was an S23
composition limitation, not a generic orchestration defect.

## Legacy-Versus-Vertical Comparison

- base_entry: MATCH (legacy=194.25, vertical=194.25)
- branch: MATCH (legacy=NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL, vertical=NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL)
- configuration_hash: MATCH (legacy=phase3d-m4-s23-bear-call-synthetic-v1, vertical=phase3d-m4-s23-bear-call-synthetic-v1)
- effective_entry: MATCH (legacy=194.25, vertical=194.25)
- gap_missed_entry_status: MATCH (legacy=NOT_MISSED, vertical=NOT_MISSED)
- monthly_status: MATCH (legacy=BEAR, vertical=BEAR)
- msl: MATCH (legacy=310.8, vertical=310.8)
- oi: MATCH (legacy=999999.0, vertical=999999.0)
- option_side: MATCH (legacy=CALL, vertical=CALL)
- order_intent: MATCH (legacy=SHORT/SELL, vertical=SHORT/SELL)
- policy_identities: MATCH (legacy=('legacy.s23.option_selling.entry', 'legacy.s23.option_selling.target', 'legacy.s23.option_selling.msl'), vertical=('legacy.s23.option_selling.entry', 'legacy.s23.option_selling.target', 'legacy.s23.option_selling.msl'))
- premium: MATCH (legacy=262.8, vertical=262.8)
- recalculated_entry: MATCH (legacy=NOT_REQUIRED, vertical=NOT_REQUIRED)
- rejection_reason: MATCH (legacy=None, vertical=None)
- selected_contract: MATCH (legacy=NIFTY_20260806_22150_CALL, vertical=NIFTY_20260806_22150_CALL)
- selected_expiry: MATCH (legacy=2026-08-06, vertical=2026-08-06)
- selected_strike: MATCH (legacy=22150.0, vertical=22150.0)
- strategy_identity: MATCH (legacy=S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL, vertical=S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL)
- target: MATCH (legacy=77.7, vertical=77.7)
- trade_result: MATCH (legacy=TRADE, vertical=TRADE)

Mismatch classifications: none.

## Future-Capability Preservation Notes

- near-expiry to next-expiry fallback remains an existing contract-selection adapter capability; the Bear Call golden selected the supplied expiry and did not exercise fallback
- directional strike traversal is represented by Bear Call start/end strike evidence from the existing S23 rule evaluation; no generic traversal engine was introduced
- ideal-premium and minimum-premium phases are preserved as S23 contract-selection adapter request/evidence fields
- configurable OI threshold is preserved from the Bear Call strategy configuration as minimum_oi=32500
- MSL uses the existing MIN-bounded stoploss formula; Target is the existing ENTRY - PARAM(target_pct)% formula for this branch
- non-positive calculated risk prices were not observed in this golden case and no new risk authority was inferred
- additional historical lookbacks are preserved as branch-specific references in strategy formulas and evidence; no Market Structure redesign was introduced
- any unobserved future rule requirement remains RULE_AUTHORITY_UNRESOLVED for later Contract Selection, Risk, or Market Structure certification

The Bear Call milestone records these requirements in S23 adapter evidence and
reports only. It does not redesign Contract Selection, Risk, or Market
Structure, and it does not add arbitrary string-expression evaluation.
Unobserved or unauthoritative behavior remains RULE_AUTHORITY_UNRESOLVED.

## Bull Call Regression

- Accepted Milestone 3 hash preserved: 4d2e514f05f873c17b7077ce6710c559dac54422ed6898cbb51e6ed9bbb24b84
- Selected contract: NIFTY_20260806_22250_CALL
- Base Entry: 203.5
- Target: 81.4
- MSL: 321.0
- Final decision: TRADE

## Determinism

Repeated Bear Call evaluations produce identical branch, selected contract,
Base Entry, Gap/Missed-Entry status, Effective Entry, Target, MSL, final
decision, normalized evidence packet, and business-output hash.

Bear Call deterministic hash: 39113635711a32f33036bae3f29efab0fe1a3ede898c7d6e0a39df88b238d053

## Fail-Closed Scenarios

- incompatible Monthly Status -> monthly_status_and_branch / UNKNOWN_S23_BRANCH
- unknown branch mismatch -> monthly_status_and_branch / UNKNOWN_S23_BRANCH
- missing underlying reference -> underlying_references / UNDERLYING_REFERENCE_FAILURE
- no qualifying Call contract -> contract_selection / NO_QUALIFYING_CONTRACT
- missing selected-contract historical reference -> base_entry / BASE_ENTRY_FAILURE
- Base Entry unknown policy -> BusinessEngineStatus.BLOCKED
- required Gap/Missed-Entry evidence missing -> EntryFailure.GAP_MISSED_ENTRY_REQUIRED_BUT_MISSING
- Effective Entry recalculation output missing -> effective_entry / EFFECTIVE_ENTRY_FAILURE
- Target adapter failure -> target_msl / TARGET_ADAPTER_FAILURE
- MSL adapter failure -> target_msl / MSL_ADAPTER_FAILURE
- invalid selected-contract evidence packet -> SELECTED_CONTRACT_NOT_IN_CANDIDATES

## Architecture Boundary

- No Bear Call logic was added to the generic orchestrator.
- No duplicate Bear Call orchestrator was created.
- No Contract Selection, Entry, Target, or MSL formulas were copied into the
  generic orchestrator.
- No broker, paper, live, lifecycle, execution, or persistence behavior was
  activated.
- Evaluation does not write files.

## Performance

- Stage count: 11
- Duration seconds: 0.02045969999744557
- Evidence packet size bytes: 12849

## Exact Runtime Impact

NONE.

## Open Rules Left Unchanged

- S23 PUT missed-entry authority remains unresolved and excluded.
- No S21, futures, lifecycle, paper, live, or broker behavior changed.

## Progress Metric

Supported S23 vertical cases: 2

- S23 Bull Call: synthetic golden
- S23 Bear Call: synthetic golden
