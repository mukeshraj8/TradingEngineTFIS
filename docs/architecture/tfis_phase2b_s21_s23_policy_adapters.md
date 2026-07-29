# TFIS Phase 2B S21/S23 Policy Adapters

Date: 2026-07-29

## Purpose

Phase 2B adds behavior-preserving compatibility policy adapters for the
isolated `TFISDecisionEngine`. The adapters exist only for deterministic
offline parity between the current S21/S23 legacy calculation path and the new
generic policy contracts.

No paper, live, replay, backtest, broker, dashboard, lifecycle, persistence, or
scheduled-job caller is migrated to `TFISDecisionEngine` in this phase.

## Architecture

```text
strategy folder
  -> StrategyRule
  -> external PolicySelection
  -> LegacyPolicyRegistryFactory
  -> TFISRuntimeInput
  -> TFISDecisionEngine
  -> TFISDecision
```

The generic `tfis.decision` package remains strategy-agnostic. S21/S23 imports
live only under `src/tfis/adapters/legacy_policies`.

## Adapter Responsibilities

- `S21ProductPolicyAdapter` and `S23ProductPolicyAdapter` preserve the current
  option-selling branch resolution as `SHORT` / `SELL` and reject Monthly
  Status values that are not configured for the strategy branch.
- `S21EntryPolicyAdapter` and `S23EntryPolicyAdapter` delegate formula
  evaluation to the existing `StrategyEvaluator`.
- `S23GapPolicyAdapter` and `S23MissedEntryPolicyAdapter` return explicit
  `NOT_APPLICABLE` results for the current offline branch parity fixtures,
  where gap and missed-entry timing are not represented as separate policy
  stages.
- `S21ContractSelectionPolicyAdapter` and
  `S23ContractSelectionPolicyAdapter` delegate deterministic option-chain
  selection to the existing selector.
- Phase 2C added `S21TargetPolicyAdapter`, `S23TargetPolicyAdapter`,
  `S21MSLPolicyAdapter`, and `S23MSLPolicyAdapter` to preserve target and
  initial stoploss/MSL evidence from the existing `StrategyEvaluator` trade
  plan.

S21 does not yet have active live/paper monthly contract-discovery runtime.
The S21 contract adapter is therefore an offline compatibility wrapper over the
existing selector mechanics, not operational enablement.

## Composition Model

`policy_selection_for_strategy()` maps strategy codes to named policy keys
outside the generic registry. The generic `PolicyRegistry` still receives only
explicit `(PolicyKind, name)` registrations and does not inspect strategy IDs.

Current mappings:

| Strategy | Product | Entry | Gap | Missed Entry | Contract | Target | MSL |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S21 | `legacy.s21.option_selling.product` | `legacy.s21.option_selling.entry` | `legacy.option_selling.gap.not_configured` | `legacy.option_selling.missed_entry.not_configured` | `legacy.s21.option_selling.contract_selection` | `legacy.s21.option_selling.target` | `legacy.s21.option_selling.msl` |
| S23 | `legacy.s23.option_selling.product` | `legacy.s23.option_selling.entry` | `legacy.s23.gap.not_configured` | `legacy.s23.missed_entry.not_configured` | `legacy.s23.option_selling.contract_selection` | `legacy.s23.option_selling.target` | `legacy.s23.option_selling.msl` |

## Parity Methodology

`run_legacy_policy_parity()` evaluates:

1. the current legacy `StrategyEvaluator` and option-chain selector
2. the generic engine with legacy policy adapters
3. field-level equality for entry, target, stoploss/MSL, strike range,
   premium thresholds, selected expiry, selected strike, selected premium/LTP,
   OI, and contract-selection reason

The parity requirement is legacy actual output equals generic-adapter actual
output. Workbook correctness is a separate acceptance track.

## Branch Coverage

Offline parity covers all currently configured S21 and S23 branch folders:

- S21 BankNifty monthly option-selling Bear Call
- S21 BankNifty monthly option-selling Bear Put
- S21 BankNifty monthly option-selling Bull Call
- S21 BankNifty monthly option-selling Bull Put
- S23 Nifty weekly option-selling Bull Call
- S23 Nifty weekly option-selling Bear Call
- S23 Nifty weekly option-selling Bear Put
- S23 Nifty weekly option-selling Bull Put

## Monthly Status Handling

Adapters consume `TFISRuntimeInput.monthly_status`. They do not calculate,
borrow, transition, collapse, or reinterpret Monthly Status. The
`TFISDecisionEngine` still rejects `UNKNOWN` or missing Monthly Status before
any adapter runs.

The Monthly Status v1.0 document is now tracked under
`docs/specification/TFIS_Monthly_Status_Reference_and_Implementation_Specification_v1.0.docx`.

## Known Limitations

- Gap and missed-entry timing parity is represented as explicit
  `NOT_APPLICABLE` for the branch-level offline fixtures. Active S23 ORPT/RC
  behavior remains in the legacy live-paper decision builder.
- S21 contract parity uses deterministic offline option-chain fixtures only.
  It is not an active BankNifty paper/live contract-discovery migration.
- Target and MSL policy stages are now present as Phase 2C decision-evidence
  stages. They do not execute exits, TSL, APS, final close, or lifecycle
  behavior.
- The four S23 start-strike fixture disagreements remain:
  `PRE_EXISTING`, `WORKBOOK_VERIFICATION_PENDING`,
  `NOT_PHASE_2B_REGRESSION`.

## Remaining Coupling

Legacy operational coupling remains in:

- `src/tfis/paper/runtime_input_derivation.py`
- `src/tfis/paper/live_decision.py`
- `src/tfis/strategy/s23_recalculation.py`
- `src/tfis/paper/contract_selection.py`
- paper order/lifecycle/dashboard runtime paths

None of these paths imports the Phase 2B adapter package.

## Phase 2C Plan

1. Add dedicated parity fixtures for active S23 ORPT/RC gap and missed-entry
   timing outputs.
2. Add first-class target/MSL policy contracts if the generic decision engine
   is expected to own those AB16 outputs directly.
3. Add external strategy-instance composition configuration and validation.
4. Run shadow/offline comparison against real paper decision summaries.
5. Consider runtime activation only after parity and failure-mode evidence is
   complete and reviewed.
