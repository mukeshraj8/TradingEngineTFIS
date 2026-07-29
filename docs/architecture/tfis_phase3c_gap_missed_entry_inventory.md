# TFIS Phase 3C Gap and Missed-Entry Inventory

Date: Wednesday, July 29, 2026

Milestone: 1 - Legacy gap and missed-entry behaviour inventory

Verdict: `MILESTONE_CONDITIONAL`

This inventory is intentionally non-invasive. It records current behaviour and
known evidence before any generic Gap and Missed-Entry Business Engine contract
is designed.

## Scope

Milestone 1 inspected existing documents, configs, implementations, and tests
for:

- gap-up / gap-down / normal-open handling
- ORPT and RC timing
- current-day HH/LL usage
- missed-entry detection
- recalculation
- no-trade and fallback outcomes
- S21 and S23 coverage
- downstream entry, contract, target, MSL, and lifecycle effects
- paper/live/backtest/replay usage

No production code was changed.

## Authoritative And Evidence Sources

Authoritative intent:

- `docs/TFIS_FTAS_v0.7_Business_Engines_Market_Data_Structure_Monthly_Status.docx`
- `docs/specification/TFIS_Monthly_Status_Reference_and_Implementation_Specification_v1.0.docx`
- workbook-derived strategy folders and source-cell metadata

Current implementation evidence:

- `src/tfis/backtest/entry_missed.py`
- `src/tfis/strategy/s23_recalculation.py`
- `src/tfis/backtest/s23_current_day_fsl_trp.py`
- `src/tfis/backtest/historical_runner.py`
- `src/tfis/paper/live_decision.py`
- `src/tfis/adapters/legacy_policies/policies.py`
- S21/S23 strategy folders under `config/strategies/options_sell/`
- Phase 2/3 architecture docs and tests

## High-Level Findings

1. Gap is an intended TFIS core concept, but there is not yet a full generic
   gap-up/gap-down engine.
2. S23 has implemented missed-entry and recalculation helpers, but they are
   strategy-specific and diagnostic/opt-in in historical backtest.
3. S23 has a separate current-day FSL/TRP layer for workbook rows `183-188`.
   It overlaps with missed/not-missed concepts but is explicitly separate from
   the older ORPT missed-entry recalculation path.
4. S21 has normal branch formulas and `entry_time` / `recalculation_time`
   fields, but S21 ORPT/RC runtime applicability is explicitly not confirmed.
5. Phase 2B/2C generic decision parity currently represents gap and missed
   entry as not configured, except when S23 ORPT/RC timing evidence is supplied
   through `gap_context`.
6. There is an implementation inconsistency: diagnostic backtest missed-entry
   detection uses ORPT `option_low < entry_price` for both CALL and PUT, while
   `src/tfis/paper/live_decision.py` uses CALL `option_low < entry_price` and
   PUT `option_high < entry_price`.

## Generic Concepts Identified

These concepts should be generic in Milestone 2:

- opening observation at or near market open
- ORPT observation
- RC observation
- gap classification: unavailable, not applicable, normal/no gap, gap up,
  gap down, invalid
- missed-entry status: unavailable, not applicable, not missed, missed,
  recalculation required, recalculation unavailable, invalid
- timing window state: waiting for 0915, waiting for ORPT, waiting for RC,
  ready, expired, invalid chronology
- observation provenance: captured, imported, synthetic, derived
- recalculation request and downstream entry instruction
- no-trade/fallback result when required observations are missing
- evidence completeness and warnings

## Strategy-Specific Rules Identified

These must remain outside generic modules:

- S23 branch unique-code to formula mapping
- S23 ORPT entry-missed rule and any option-side-specific interpretation
- S23 recalculation formulas for Bull Call, Bear Call, Bull Put, Bear Put
- S23 current-day FSL/TRP workbook rows `183-188`
- S23 resolved workbook clarification for row `184`
- unsupported S23 current-day paths:
  - Bull/Bull CF Put not missed
  - Bear/Bear CF Call not missed
- S21 branch formula matrix and BankNifty monthly assumptions
- S21 ORPT/RC applicability, which remains unconfirmed

## Behaviour Inventory

| Area | Source | Strategy / branch | Inputs | Timing | Rule | Output | Side effects | Evidence status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Base entry formula | `StrategyEvaluator` and strategy `formulas.yaml` | S21/S23 all configured branches | `MarketLevels`, `OPT_LEVELS`, parameters | Strategy `entry_time` is config metadata | Evaluate configured start/end/ideal/minimum/entry/target/stoploss formulas | `TradePlan` | None inside evaluator | Formula values covered by branch tests |
| S23 entry missed | `S23EntryMissedDetector` | S23 CALL and PUT diagnostic backtest path | option type, entry price, ORPT snapshot option low | ORPT `09:24:59` | `option_low < entry_price` | `EntryMissedResult` | None; caller decides recalculation | Unit tests cover missed, not missed, missing option low |
| S23 recalculation | `S23RecalculationEngine` | S23 four canonical branches | base trade plan, market levels, option levels, parameters, ORPT and RC snapshots, entry_missed | RC `09:29:59` after ORPT missed | Branch-specific formulas using completed PRV refs plus current-day RC spot/option values | `RecalculationResult` with recalculated strike/premium/entry fields | None inside strategy helper | Unit tests cover four branches, parameterization, no recalculation |
| S23 historical recalculation overlay | `HistoricalBacktestRunner._apply_s23_recalculation_if_needed` | S23 canonical branches only | option intraday, optional spot intraday, market levels, base plan | ORPT then RC | Detect missed at ORPT; if missed, apply S23 recalculation | Effective lifecycle `TradePlan`; audit payload | Effective lifecycle bars are filtered after RC | Integration tests cover opt-in unchanged default, missing ORPT, base kept, spot source |
| S23 current-day FSL/TRP trigger | `S23CurrentDayFslTrpEngine` | S23 rows `183-188` paths | trigger, ORPT, RC snapshots, base stoploss | trigger `09:15:00`; ORPT `09:24:59`; RC `09:29:59` | `current_day_option_high > stoploss_price` means FSL/TRP missed | `CurrentDayFslTrpTriggerResult` | None inside helper | Unit tests cover supported rows and unsupported paths |
| S23 current-day not missed rows | `S23CurrentDayFslTrpEngine` | row `183` Bull Call, row `186` Bear Put | PRV refs, CDHH/CDLL at ORPT, option levels, parameters | ORPT snapshot | Workbook-backed recalculated strike/premium/entry; target/stop inherited | `S23CurrentDayFslTrpResult` | Historical overlay can update entry/strike/premium and lifecycle start after ORPT | Unit/integration tests cover row `183` and `186` |
| S23 current-day missed rows with full formulas | `S23CurrentDayFslTrpEngine` | row `184` Bull Call, row `185` Bear Call | PRV refs, CDHH/CDLL at RC, option levels, parameters | RC snapshot | Workbook-backed recalculated strike/premium/entry and FSL | `S23CurrentDayFslTrpResult` | Historical overlay can update entry/strike/premium/stoploss and lifecycle start after RC | Unit/integration tests cover rows `184` and `185` |
| S23 current-day FSL-only rows | `S23CurrentDayFslTrpEngine` | row `187` Bull Put, row `188` Bear Put | RC option high, stoploss parameter | RC snapshot | Only recalculated FSL is confirmed; do not infer blank fields | Result with only stoploss override | Historical overlay may update stoploss only | Unit/integration tests cover row `187`; unit covers row `188` |
| S23 unsupported current-day paths | `S23CurrentDayFslTrpEngine` | Bull Put not missed, Bear Call not missed | trigger indicates not missed | ORPT | Workbook path not confirmed | `applied=False`; base plan kept | No effective plan change | Unit tests cover unsupported not-missed path |
| S23 paper/live ORPT/RC audit | `S23PaperLiveDecisionBuilder._build_orpt_rc_timing_audit` | S23 paper/live decision builder | selected-contract ORPT/RC bars, ORPT/RC underlying snapshots, base trade plan | ORPT bar start `09:24`, RC bar start `09:29` | CALL: option low < entry; PUT: option high < entry | Timing audit status such as `BASE_ENTRY_VALID`, `ENTRY_MISSED_RECALCULATED`, `MISSING_*` | Recalculates target and stoploss in audit trade plan when recalculation applies | Unit tests around live-decision timeline and adapter timing evidence |
| Phase 2B gap policy | `S23GapPolicyAdapter` | S23 offline decision parity | `runtime_input.gap_context["orpt_rc_timing"]` when present | Supplied by caller | Missing timing -> not applicable; `MISSING_*` -> unavailable; otherwise passed | `GapPolicyResult` | No runtime side effect | Phase 2 parity/evidence tests |
| Phase 2B missed-entry policy | `S23MissedEntryPolicyAdapter` | S23 offline decision parity | `runtime_input.gap_context["orpt_rc_timing"]` when present | Supplied by caller | `status == ENTRY_MISSED_RECALCULATED` means missed | `MissedEntryPolicyResult` | No runtime side effect | Phase 2 parity/evidence tests |
| S21 ORPT/RC | S21 strategy config and architecture doc | S21 all four folders | `entry_time=09:24:59`, `recalculation_time=09:29:59` in config | Config only | Runtime ORPT/RC applicability is not implemented/confirmed | None beyond normal `TradePlan` | None | Classified as open before operational promotion |

## S23 Recalculation Formula Inventory

Legacy helper: `src/tfis/strategy/s23_recalculation.py`.

| Branch | Classification | Recalculation rule summary | Output fields |
| --- | --- | --- | --- |
| Bull/Bull CF Call | `LEGACY_CONFIRMED` | `MIN(PRV_3DLL, recalc_spot_low)` drives strike/premium; `MIN(OPT_PRV_3DLL, recalc_option_low) - entry_discount_pct` drives entry | start, end, ideal, minimum, entry |
| Bear/Bear CF Call | `LEGACY_CONFIRMED` | `MIN(PRV_2DLL, recalc_spot_low)` drives strike/premium; `MIN(OPT_PRV_2DLL, recalc_option_low) - entry_discount_pct` drives entry | start, end, ideal, minimum, entry |
| Bull/Bull CF Put | `SPEC_CONFIRMED` with prior workbook wording correction | `MAX(PRV_2DHH, recalc_spot_high)` drives strike; `MIN(PRV_2DHH, recalc_spot_low)` drives premium; `MIN(OPT_PRV_2DLL, recalc_option_low) - entry_discount_pct` drives entry | start, end, ideal, minimum, entry |
| Bear/Bear CF Put | `SPEC_CONFIRMED` with prior workbook wording correction | `MAX(PRV_3DHH, recalc_spot_high)` drives strike; `MIN(PRV_3DHH, recalc_spot_low)` drives premium; `MIN(OPT_PRV_3DLL, recalc_option_low) - entry_discount_pct` drives entry | start, end, ideal, minimum, entry |

## State And Timing Model

Current timing observations:

- Strategy folders declare `entry_time: "09:24:59"` and
  `recalculation_time: "09:29:59"` for both S21 and S23.
- S23 recalculation constants are `ORPT=09:24:59` and `RC=09:29:59`.
- S23 current-day FSL/TRP adds `09:15:00` trigger evidence.
- Paper orchestrator can wait for `0915`, `ORPT`, and `RC` snapshots.
- Historical backtest can opt into either S23 recalculation or S23 current-day
  FSL/TRP, but not both at the same time.
- Historical backtest defaults remain unchanged when flags are not supplied.
- No future generic engine should scan runtime state or own mutable state; all
  timing observations should be supplied explicitly.

State required by a future generic engine:

- strategy identity and version
- product/family
- monthly status
- market structure references
- configured timing windows
- opening/0915 observation when applicable
- ORPT observation
- RC observation when recalculation is required
- base entry/target/stop/contract references from upstream engines
- explicit provenance and missing-input markers

## Downstream Effects

Observed downstream effects:

- S23 ORPT missed-entry recalculation can change effective lifecycle
  `start_strike`, `end_strike`, `ideal_premium`, `minimum_premium`, and
  `entry_price`.
- S23 historical recalculation filters lifecycle bars to observations after RC.
- S23 paper/live ORPT/RC audit recalculates target and stoploss in the timing
  audit when recalculation applies.
- S23 current-day FSL/TRP rows `183-186` may override entry price, which changes
  lifecycle entry timing and realized P/L in opt-in historical comparisons.
- S23 current-day rows `184`, `185`, `187`, and `188` may override stoploss/FSL.
- Unsupported current-day paths preserve the base plan and emit warnings.
- Phase 2B/2C offline decision gap/missed policies do not alter entry,
  contract, target, or MSL; they only expose evidence/status.

## Missing Evidence

- Full generic gap-up and gap-down classification formulas are not implemented.
- Normal-open classification is implicit in "base entry valid" / no overlay,
  not represented as first-class output.
- S21 missed-entry and recalculation behaviour is not implemented or confirmed.
- S21 has timing config but no confirmed runtime ORPT/RC semantics.
- The relationship between generic gap classification and S23 current-day
  FSL/TRP rows is not yet modelled.
- Captured evidence exists for S23 partial ORPT/RC sessions, but full captured
  option-chain/evidence parity is still limited.
- Current evidence packet has a gap/missed-entry section, but current Phase 2B
  adapters still carry S23 timing evidence as compatibility payload/context.

## Ambiguities And Classifications

| Ambiguity | Classification | Detail | Required action |
| --- | --- | --- | --- |
| S23 PUT missed-entry comparison differs between diagnostic detector and paper/live timing audit | `LEGACY_INCONSISTENCY` | Backtest detector uses `option_low < entry_price` for PUT; paper/live audit uses `option_high < entry_price` for PUT | Do not choose silently in Milestone 2; model observation fields and require strategy policy to define the comparison |
| Full gap-up/gap-down rules | `INSUFFICIENT_EVIDENCE` | FTAS says gap-aware behaviour exists, but current code does not implement generic gap classification | Keep gap classification generic but leave formulas to policies until workbook evidence is mapped |
| S21 ORPT/RC applicability | `USER_CLARIFICATION_REQUIRED` | S21 config includes timing, but architecture doc says runtime handling and whether S21 uses S23 timing are open | Do not implement S21 missed-entry policy without approval/evidence |
| S23 current-day row `184` mixed Call/Put formula family | `SPEC_CONFIRMED` | Existing design says user confirmation resolved row `184` as workbook-directed | Preserve in compatibility policy; do not normalize away |
| S23 rows `187-188` blank strike/premium/entry fields | `SPEC_CONFIRMED` | Existing design says FSL-only, do not infer blank fields | Preserve as partial recalculation output |
| Target override formulas for current-day rows | `INSUFFICIENT_EVIDENCE` | Existing design says no additional target override formulas were found in AB6 OS rows `162-191` | Keep target inherited unless later evidence appears |
| Combining historical `--enable-s23-recalculation` and `--enable-s23-current-day-fsl-trp` | `LEGACY_CONFIRMED` | Historical runner rejects combining both flags | Preserve as incompatible overlay modes unless explicitly redesigned |

## Proposed Engine Boundary For Milestone 2

Recommendation: model Gap and Missed Entry as one combined
`GapMissedEntryEngine` contract with internal stages, not two separate engines
yet.

Reasoning:

- Current S23 evidence couples opening/ORPT/RC observations with missed-entry
  and recalculation outputs.
- The existing Phase 3B catalog already has a single `gap` engine dependency
  before `entry`, and the gap engine provides the `GAP` capability.
- `MISSED_ENTRY` is a companion capability produced with entry/missed evidence
  today; separating it before inventory-parity may add ceremony without proven
  benefit.
- A combined contract can still expose separate typed outputs for gap
  classification, missed-entry state, and recalculation request.
- Future split remains possible after concrete parity if timing and
  recalculation policies prove independently reusable.

Boundary rules for Milestone 2:

- Generic module owns orchestration types, validation, timing/evidence shape,
  result status, quality, and failure semantics.
- Strategy-specific policies own formulas and branch mappings.
- Runtime supplies observations; the engine must not fetch broker data or scan
  runtime state.
- The engine emits downstream instructions to Entry/Contract/Risk engines but
  must not perform contract selection, target/MSL execution, or paper/live
  state mutation.

## Tests And Evidence Reviewed

Reviewed tests include:

- `tests/unit/test_s23_entry_missed.py`
- `tests/unit/test_s23_recalculation.py`
- `tests/unit/test_s23_current_day_fsl_trp.py`
- `tests/integration/test_historical_backtest_s23_recalculation_mode.py`
- `tests/integration/test_historical_backtest_s23_current_day_fsl_trp_mode.py`
- Phase 2 legacy policy parity tests
- Phase 2D.1 decision evidence packet tests
- Phase 3B business engine framework tests

No tests were run for Milestone 1 because no executable behavior was changed.

## Recommendation For Milestone 2

Proceed to Milestone 2 only after review approval.

Milestone 2 should define immutable generic contracts for:

- gap observation and classification
- timing windows
- missed-entry state
- recalculation request
- downstream entry instruction
- deterministic evidence
- failure and quality status

Milestone 2 must stop before implementing any S21/S23 compatibility policy.

Milestone 4 follow-up: offline parity and typed decision-evidence integration
are documented in
`docs/architecture/tfis_phase3c_gap_missed_entry_parity_and_evidence.md`.
