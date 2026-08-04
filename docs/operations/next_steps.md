# Next Steps

This document is the execution queue for TFIS. It should be updated whenever
task ordering, blockers, or the recommended next action change in a meaningful
way.

## Immediate Next Priorities

0.67475. `USE_THE_VERIFIED_FAST_TRACK_REPORT_PATH_AS_THE_CURRENT_TIME_TRUTH_SURFACE`
   The live FYERS read-only rerun at `13:41:54 IST` already closed the
   generic executable-price normalization defect and now proves
   `S21 = PROCESSED_INTERNAL_PAPER`, `S23 = PROCESSED_INTERNAL_PAPER`, and
   `S22 RELIANCE = NO_ORDER` from truthful same-day reconstruction under
   `reports/fast_track_development/`. Treat this report pack as the current
   August 4, 2026 authoritative same-day action surface unless and until a
   newer run supersedes it.

0.6747. `RETAIN_RUN_FAST_TRACK_DEVELOPMENT_AS_THE_AUTHORIZED_SAME_DAY_RERUN_COMMAND`
   Re-execute `scripts/run_fast_track_development.py` whenever the operator
   needs a fresh same-day reconstruction plus current-time internal-paper
   action assessment without requiring a before-open supervisor start.

0.67465. `DECIDE_WHETHER_TO_GENERICIZE_S22_MULTI_STOCK_EXECUTION_PLAN_SUPPORT`
   The new fast-track slice reports `TCS` and `INFY` as development-ready
   candidates, but it does not yet activate them because the repo still lacks
   a generic source-closed S22 multi-stock execution-plan builder outside the
   RELIANCE trace path. The next decision is whether to build that reusable
   S22 stock-plan capability now or keep the current boundary explicit.

0.6746. `USE_AUGUST_4_HISTORICAL_RECONSTRUCTION_AS_THE_NEW_LATE_START_BASELINE`
   The old session-wide late-start assumption is no longer acceptable repo
   truth. Govern all restart and recovery work from
   `reports/historical_reconstruction/`, especially
   `august4_baseline_reassessment.json`,
   `reconstruction_evidence_contract.json`, and
   `historical_reconstruction_summary.md`. Today, Tuesday, August 4, 2026,
   the truthful reconstructed baseline is:
   `S21 = NORMAL_ENTRY_STILL_VALID`,
   `S22 RELIANCE = RC_ENTRY_ALREADY_MISSED`,
   `S23 = NORMAL_ENTRY_STILL_VALID`.

0.6745. `RUN_ONE_CLEAN_BEFORE_OPEN_BASELINE_ON_THE_PATCHED_LIVE_SELECTION_PATH`
   The next exact operational gate is now sharper than it was this morning:
   stop the old late-start PID `20840`, then run one fresh before-market-open
   unified supervisor session on the patched live-selection path. Governing
   evidence is now under `reports/live_contract_selection/`. S21 and S23 are
   no longer blocked by fixture contract identity in code; the remaining step
   is one clean runtime start that actually uses the new path in the operator
   session.

0.674. `MAKE_SELECTED_CONTRACTS_AUTHORITATIVE_IN_LIVE_BASELINE` Today's
   reconstruction proved that per-instance recovery works, but it also exposed
   the next hard blocker: `S21` and `S23` cannot be reconstructed honestly in
   a live baseline while their enabled strategy registry still points to
   fixture selected-contract identities. The next implementation slice should
   keep the new generic reconstruction coordinator and wire live selected-
   contract identity capture into the baseline supervisor before the next
   before-open proof.

0.6735. `KEEP_TODAY_SESSION_OBSERVATIONAL_ONLY` For the remainder of Tuesday,
   August 4, 2026, do not create new internal-paper orders from the degraded
   live baseline session. The truthful current reconstruction result is:
   `S22 RELIANCE = RC_ENTRY_ALREADY_MISSED`; `S21` and `S23` are blocked by
   insufficient live selected-option evidence. `TCS` and `INFY` stay disabled.

0.673. `RERUN_BEFORE_OPEN_BASELINE_ON_PATCHED_LATE_START_FIX` Today's Tuesday,
   August 4, 2026 baseline open-window proof failed because the running
   supervisor incorrectly classified the first `09:15` cycle as
   `LATE_START_NO_NEW_ENTRY` even though the process was already started
   before market open. The defect is now fixed in
   `src/tfis/runtime/multi_strategy/supervisor.py` with focused validation
   `17 passed`, but the current live session cannot be reused as baseline
   certification because all baseline instances were already deferred. The
   next exact gate is one fresh before-open unified session on the patched
   code path.

0.6725. `DO_NOT_ENABLE_TCS_OR_INFY_AFTER_TODAY_S_FAILED_BASELINE` Keep `TCS`
   and `INFY` disabled in `config/s22_multi_stock_registry.yaml` for the
   remainder of today's Tuesday, August 4, 2026 session. User approval remains
   recorded, but today's degraded baseline did not satisfy the required
   activation gate.

0.672. `RUN_TOMORROW_BEFORE_OPEN_FULL_UNIFIED_SESSION` The next exact critical
   path is one full unified internal-paper session from before market open on
   the patched code path. Today's after-market closure moved readiness to
   `CONDITIONAL_READY_PENDING_BEFORE_OPEN_PROOF`: the heartbeat is terminal
   `STOPPED`, the late-start session did enter `EOD_PROCESSING` at the 15:00
   boundary, the old PIDs are gone, and bounded deterministic cadence proof is
   now recorded under `reports/live_closure_20260803/`. The remaining proof is
   a fresh before-open real session only.

0.671. `USE_AUTHORITATIVE_AFTER_MARKET_CLOSURE_PACK` Govern tomorrow's operator
   startup from:
   `reports/unified_readiness/authoritative_readiness_projection.json`,
   `reports/live_closure_20260803/eod_scheduler_result.json`,
   `reports/live_closure_20260803/final_checkpoint_result.json`, and
   `reports/live_closure_20260803/fresh_supervisor_cadence_final.json`.
   Treat the old live summary `EOD_PROCESSING` terminal state as a historical
   reporting gap from the pre-fix PID, not as the current repo truth.

0.6705. `KEEP_TCS_DISABLED_UNTIL_BASELINE_CERTIFICATION` `TCS` now has
   dated live FYERS read-only metadata and remains disabled in
   `config/s22_multi_stock_registry.yaml`. The old simultaneous-acceptance
   ambiguity is closed by the global sequential-account acceptance rule:
   qualifying intents for the same account must be processed through a
   deterministic queue with per-order margin checks and reservation
   reconciliation. Focused proof now exists in
   `reports/s22_multi_stock/sequential_account_acceptance_test.json`,
   `reports/s22_multi_stock/margin_reservation_lifecycle.json`, and
   `reports/s22_multi_stock/insufficient_margin_warning_contract.json`. `TCS`
   is now explicitly approved for controlled S22 onboarding, but it remains
   disabled for the next baseline unified-session certification, not because
   business priority authority is missing.

0.6704. `KEEP_INFY_DISABLED_UNTIL_BASELINE_CERTIFICATION` `INFY` remains
   disabled in `config/s22_multi_stock_registry.yaml`, but it is no longer
   blocked by uneven strike spacing. The latest authoritative classification is
   `METADATA_READY_CONDITIONAL` / `READY_FOR_USER_APPROVAL`: read-only capture
   now proves safe actual-listed strike traversal under
   `reports/contract_selection/infy_actual_chain_selection.json`. `INFY` is
   also explicitly user-approved for controlled S22 onboarding, but it remains
   disabled for the next baseline unified-session certification.

0.67. `KEEP_TOMORROW_SCOPE_TIGHT` Keep tomorrow focused: do not add new
   strategies, keep `TCS` and `INFY` disabled until the next baseline unified
   session certification passes, and do not add external broker order authority while
   the before-open full-session proof is still pending.

0.665. `ACTIVATE_MULTI_STOCK_ONLY_AFTER_BASELINE_PASS` Keep RELIANCE as the
   only enabled S22 stock for the next baseline unified-session certification.
   `TCS` and `INFY` are now prepared as disabled candidates in
   `config/s22_multi_stock_registry.yaml` with explicit user approval already
   recorded. After the baseline unified-session certification passes, activate
   `RELIANCE`, `TCS`, and `INFY` together in one controlled S22 multi-stock
   internal-paper profile. External FYERS order authority remains `NONE`.

0.66. `NO_GO_UNTIL_CLEARED` Do not start the next full unified
   pre-market-to-EOD internal-paper session until all three gates are green:
   FYERS read-only session validation must pass, the existing late-start
   supervisor PID/lock must be cleared by graceful shutdown, and one fresh
   before-market-open run must prove the optimized continuous-supervisor cadence
   on the new code path. Treat
   `reports/runtime_performance/next_session_readiness.json` and
   `reports/production_readiness_review_20260803.md` as the governing go/no-go
   artifacts. Use
   `reports/unified_readiness/authoritative_readiness_projection.json` as the
   single operator-facing readiness file produced from those inputs; do not rely
   on older deterministic green artifacts alone.

0.65. `CONDITIONAL` Run the unified S21/S22/S23 internal-paper dashboard during
   the next eligible NSE session only after 0.66 is cleared. Use
   `.venv/Scripts/python.exe scripts/run_tfis_internal_paper.py` before the
   session to refresh deterministic certification reports, then
   `.venv/Scripts/python.exe scripts/run_tfis_dashboard.py --serve --port 8766`
   for the local read-only dashboard/API. Keep FYERS order authority `NONE`;
   the key live gaps to replace remain S22 RELIANCE opening/ORPT/RC evidence
   and fresh cadence proof for the optimized supervisor path.

0.64. `TODO` Repeat the S22 RELIANCE live-session read-only observation on the
   next eligible NSE trading session, preferably before market open. The next
   attempt must run the FYERS read-only/authentication diagnostics only after
   the session gate is eligible, persist the live PreMarketStrategyPlan before
   opening evaluation, continuously capture the selected RELIANCE option
   contract through ORPT and RC, and keep FYERS order authority `NONE`.

0.63. `BLOCKED_SESSION_WINDOW_UNAVAILABLE` Attempt the live-session RELIANCE
   read-only snapshot if S22
   reviewer acceptance requires captured opening, ORPT and RC timing evidence
   or selected-option historical references. Keep FYERS order authority
   `NONE`; use the capture only to replace deterministic supplements in the
   existing one-stock proof. Result on Sunday, August 2, 2026 at 14:20 IST:
   blocked before any FYERS live read because no NSE trading session was
   available. Reports: `reports/s22_live_observation/`.

0.62. `DONE` Implement the S22 RELIANCE one-stock offline/internal-paper proof
   from
   `tests/fixtures/s22_reliance/s22_reliance_fyers_snapshot_2026-08-02_sanitized.json`.
   Result: metadata gate passed, generic Monthly Status resolved RELIANCE as
   `BEAR_CF`, completed-session references were derived from FYERS history,
   S22 naturally selected `BEAR_CALL`, near-expiry contract selection chose
   `NSE:RELIANCE26AUG1260CE`, and the branch ran through
   PreMarketStrategyPlan, EffectiveExecutionPlan, ExecutionIntent validation,
   internal-paper order/fill, PositionCycle, lifecycle, accounting and
   dashboard projection. Verdict: `S22_RELIANCE_CONDITIONAL` because opening,
   ORPT/RC and selected-option historical references are deterministic
   supplements, not captured live-session evidence. External FYERS broker
   order authority remains `NONE`.

0.61. `DONE` FYERS authentication and S22 RELIANCE read-only capture. The
   canonical command is
   `.venv/Scripts/python.exe scripts/fyers_token_refresh.py --prepare`.
   Broker diagnostics are available through
   `.venv/Scripts/python.exe scripts/run_broker_diagnostics.py --broker fyers`.
   The dated RELIANCE capture completed and the metadata gate passed. External
   broker-order authority remains `NONE`.

0.58. `DONE` Close the S21 source-question register. Decision artifacts:
   `reports/s21_source_closure/s21_user_decision_pack.md` and
   `reports/s21_source_closure/s21_user_decision_pack.json` are retained as a
   closed audit trail. `S21-Q001` contract/expiry fallback, `S21-Q002` gap
   classification versus ORPT/RC, `S21-Q003` APS/partial exits, `S21-Q004`
   quantity and P&L unit, and `S21-Q005` rollover/expiry action are closed.
   APS is `APS_NOT_APPLICABLE` for S21/S22/S23 one-lot Option Selling. S21
   implementation readiness is `S21_SOURCE_CLOSURE_ACCEPT`. Runtime impact:
   `NONE`. Broker/paper/live authority: `NONE`.

0.57. `TODO` Preserve Monthly Status as a generic business engine before any
   S21/S22 onboarding work. The engine must accept structured instrument
   identity, evaluation timestamp, monthly candle/reference evidence, rule
   version, provenance, and data quality; return independently keyed immutable
   results with status, references, transition evidence, warnings/failures, and
   deterministic result hash; and support batch requests for NIFTY, BANKNIFTY,
   F&O stocks, and future eligible instruments. Strategy policies may map the
   typed Monthly Status result to branch/trade/block decisions, but generic
   Monthly Status code must not branch on S21, S22, S23, option-selling, or
   symbols.

0.56. `DONE` Resolve S21 source questions before any S21 implementation.
   Source inspected:
   `All_in_One_TFIS_26-12-2023_Unprotected_Copy.xlsx`, Monthly Status v1.0
   specification, and S21 workbook rows/cells recorded under
   `reports/s21_source_closure/`. The 15:00 equality behavior is closed by
   global Option Selling user clarification:
   `close > Original SL` exits and `close <= Original SL` carries forward.
   No checklist row remains `PARTIAL`; S21 source closure is accepted with
   exact questions `S21-Q001` through `S21-Q005` closed. Legacy S21 may be
   inspected only as non-authoritative discrepancy evidence during
   implementation planning.

0.55.5. `TODO` Plan the next S21 onboarding milestone from the accepted source
   closure. Treat S23 as the reference implementation, justify any generic code
   change as reusable platform capability, keep Monthly Status generic and
   strategy-independent, and do not add APS logic for S21/S22/S23 one-lot
   Option Selling. No broker, external paper, or live authority is approved.

0.55. `TODO` Continue complete-S23 internal-paper observation with additional
   naturally selected CE/PE sessions and prioritize replacing fixture-backed
   cases with captured evidence. Do not start S21 extraction, broker sandbox,
   or external paper/live planning until Phase 5C is accepted or the captured
   evidence gap is explicitly dispositioned. Capture should specifically
   include Monthly Status, option-chain/OI, selected CE and PE quotes, ORPT,
   RC, EOD, and carry evidence.

0.54. `DONE` Run focused multi-session S23 observation across naturally
   selected CE and PE sessions using the complete four-branch internal-paper
   profile. Result: all four S23 branches are naturally resolved in the
   observation set, CE/PE routing isolation, three-run determinism,
   duplicate-action audit, carry/recovery, position/protection safety, shared
   accounting, profitability observation, block funnel, performance/resource,
   reuse, readiness, and gap reports are generated under `reports/phase5c/`.
   One Put missed-entry defect was fixed: active paper live-decision now uses
   accepted `OPTION_LOW < Entry Price` authority for Put ORPT missed-entry
   instead of legacy option-high behavior.
   Verdict: `PHASE5C_M1_CONDITIONAL` because complete captured S23 evidence
   remains incomplete and the proof is still partly fixture-backed. Runtime
   impact: `MULTI-SESSION COMPLETE-S23 INTERNAL-PAPER OBSERVATION`.
   Broker/live authority: `NONE`.

0.53. `DONE` Complete Phase 5B S23 Bull Put and Bear Put end-to-end
   internal-paper onboarding. Result: Put missed-entry authority is closed as
   `AUTHORITATIVE_OPTION_LOW`; Bull Put and Bear Put source cells, gap/RC
   formulas, target/MSL/FSL/TRP evidence, EOD carry behavior, natural CE/PE
   branch selection, call-side regression, and four-branch certification are
   recorded under `reports/phase5b/`. Runtime impact:
   `COMPLETE FOUR-BRANCH S23 INTERNAL-PAPER SUPPORT`. Broker/live authority:
   `NONE`.

0.52. `TODO` After user approval of Phase 3E Milestone 4, proceed to
   Milestone 5: finalize the complete Phase 3E roadmap, critical path, user
   decisions, diagrams, and certification. Do not add paper or live authority
   in Milestone 5.

0.51. `DONE` Complete Phase 3E Milestone 4 analytics/accounting facts and
   first-10 strategy onboarding architecture. Result: defined `TradeFact`,
   `PnLFact`, product P&L unit catalog, realized/unrealized P&L rules,
   charges/tax quality, essential dimensions/metrics, win/loss classification,
   drawdown/equity method, MFE/MAE method, execution-quality facts, minimum
   read models, analytics failure isolation, future analytics extension
   boundaries, strategy inventory, first-10 selection criteria/candidates,
   onboarding gates, scorecard, batch-size guidance, and profitability review.
   Verdict: `MILESTONE_CONDITIONAL` because non-option-selling source sheets
   still require exact extraction before implementation. Runtime impact:
   `NONE`. Broker/paper/live authority: `NONE`.

0.50. `DONE` Complete Phase 3E Milestone 3 persistence, recovery, risk, and
   performance architecture. Result: defined the V1 transactional persistence
   model, entity persistence classifications, transaction boundaries,
   idempotency model, broker reconciliation classifications, restart/recovery
   sequence, risk hierarchy, kill-switch semantics, degraded modes,
   market-data/backpressure rules, coherent snapshot rules, provisional
   performance budgets, failure isolation, operational observability, audit
   evidence, P&L reliability, and Phase 4 implementation order. Runtime impact:
   `NONE`. Broker/paper/live authority: `NONE`.

0.49. `DONE` Complete Phase 3E Milestone 2 domain ownership architecture.
   Result: defined minimum production-grade ownership for
   `AccountCoordinator`, `OrderStateMachine`, `PositionCycleCoordinator`,
   `PortfolioRiskAndControlSupervisor`, `ExecutionIntent`,
   `LifecycleRequirement`, order/fill/position-cycle traceability,
   multiple-account isolation, quantity/protection invariants, failure
   isolation, and analytics fact connectivity. Runtime impact: `NONE`.
   Broker/paper/live authority: `NONE`.

0.48. `DONE` Complete Phase 3E Milestone 1 architecture checkpoint.
   Result: created the Version 1 minimum production architecture draft, first-10
   strategy roadmap draft, initial mandatory capability classification, and
   gap matrix. Runtime impact: `NONE`. Broker/paper/live authority: `NONE`.

0.47. `TODO` Connect the deterministic M15 runtime coordinator to one existing
   captured/replay market stream in shadow-only mode. Preserve the current
   authority boundary: no broker submission, no paper/live authority, no order
   modification/cancellation, no square-off execution, and no position
   mutation. Use the M15 normalized event contract, subscription routing,
   shared instrument snapshots, and checkpoint/resume evidence.

0.46. `DONE` Review and accept Phase 3D Milestone 15 runtime coordination
   before connecting captured/replay data. Result: M15 implements deterministic
   runtime-style event coordination for accepted S23 fresh-entry and
   carried-position offline flows. Shared instrument snapshot processing,
   subscription routing, critical event preservation, ordinary tick conflation,
   replay/resume checkpointing, multi-instance isolation, multi-position
   isolation, and no-authority proof are implemented in-memory and
   non-authoritatively. Reports:
   `reports/phase3d/milestone15_runtime_coordination_summary.md` and
   `reports/phase3d/milestone15_runtime_gap_matrix.json`.

0.45. `DONE` Review and accept Phase 3D Milestone 14 before selecting the next
   implementation slice. M14 is offline-only carried-position trading-day
   coordination and does not add broker, paper, live, scheduler, event-bus,
   order-modification, square-off, or position-mutation authority. Reports:
   `reports/phase3d/milestone14_carried_position_trading_day_summary.md` and
   `reports/phase3d/milestone14_carried_position_gap_matrix.json`.

0.44. `DONE` Review and accept Phase 3D Milestone 13B source closure before
   starting M14.
   Result: M14 consumed the accepted M13B equality closure. Equality at
   `15:00 close == original SL` carries forward.

0.43. `DONE` Resolve the concrete M13A user questions before M14.
   Result: M13B source closure reviewed the actual workbook files supplied in
   `TFISRulesAndSpec`; Q001, Q002, and Q003 are closed with the boundaries
   recorded in `reports/phase3d/milestone13a_questions_for_user.md`.

0.42. `DONE` Complete one offline carried-position trading-day coordination
   timeline that composes the existing M12 carried-position boundary with the
   M13 lifecycle context handoff. Keep it non-authoritative and do not add
   broker execution, order modification, square-off, paper authority, live
   authority, scheduler behavior, or a production event bus.
   Result: M14 implemented complete offline carried-position day coordination
   with position reconciliation, target-first assessment, ORPT/RC lifecycle
   states, 15:00 EOD decision, and offline lifecycle handoff.

0.41. `DONE` Implement the `PositionLifecycleContext` boundary and
   carried-position opening-gap observation model. Keep it non-authoritative
   and do not add broker execution, live authority, order management, or a
   production event bus.
   Result: immutable offline `PositionLifecycleContext`,
   `ReconciledPositionSnapshot`, carried-contract opening quote evidence,
   target/protection crossing observation, and `OfflineLifecycleHandoff` are
   implemented for S23 Call-side carried-position fixtures. Target crossed at
   open now produces offline `EXIT_REQUIRED`; adverse carried-premium gaps with
   configured lifecycle recalculation policy inputs produce offline
   `REVISED_SL_PLACEMENT_REQUIRED`; favorable carried-premium gaps continue
   normal monitoring. Lifecycle action execution, broker reconciliation engine,
   live event routing, and broker/paper/live authority remain `NONE` /
   `NOT_IMPLEMENTED`.

0.40. `DONE` Select the next approved boundary: implement
   `PositionLifecycleContext`, implement one complete offline trading-day
   state transition from pre-market plan through execution-plan handoff, or
   correct a precise `EffectiveExecutionPlan` defect found during Milestone
   11 review. Do not move to live event bus, scheduler, broker execution,
   paper authority, live authority, or shared routing yet.
   Result: one complete offline trading-day state transition from pre-market
   plan through non-authoritative execution-plan handoff is implemented for
   S23 Call-side normal/gap paths, with partial-real blocked and
   carried-position handoff-required boundaries.

0.39. `DONE` Implement offline `EffectiveExecutionPlan` composition from
   `PreMarketStrategyPlan` plus `OpeningMarketContext` for S23 Call-side only.
   Do not add event bus, scheduler, concurrency, broker execution, lifecycle,
   paper/live authority, PUT branches, S21, or futures in the same milestone.
   Result: Bull/Bear normal retained plans, Bull/Bear gap recalculated plans,
   and one M7-derived partial real insufficient-evidence plan are produced as
   immutable offline artifacts. Runtime execution authority remains `NONE`.

0.38. `DONE` Implement immutable offline `OpeningMarketContext` contract and
   builder for S23 Bull Call and Bear Call opening evidence. Bull and Bear
   fixture contexts are `COMPLETE`; the M7-derived real context is `PARTIAL`.
   Shared live event routing remains `NOT_IMPLEMENTED`; runtime execution
   authority remains `NONE`.

0.37. `DONE` Select exactly one next Milestone 10 path: implement an offline
   `OpeningMarketContext` contract and builder for S23 Call-side, replace
   legacy/synthetic pre-market plan inputs with a real captured pre-market
   packet if such data becomes available, or fix a precise
   `PreMarketStrategyPlan` gap found during review. Do not implement all
   remaining runtime objects together.

0.36. `DONE` Implement the first offline S23 Call-side
   `PreMarketStrategyPlan` builder artifact selected from the Phase 3D
   Milestone 8 gap matrix. Bull Call and Bear Call now produce immutable
   `PREPARED` pre-market plans from completed fixture/configuration inputs.
   Real captured pre-market plans remain `0`; `OpeningMarketContext`,
   `EffectiveExecutionPlan`, `PositionLifecycleContext`, runtime authority,
   broker/paper/live authority, and execution remain unimplemented.

0.35. `DONE` Define the Phase 3D Milestone 8 runtime operational model and
   gap matrix. Result: TFIS is specified as a precomputed-plan system with
   separate normal fresh-entry, Gap/Missed-Entry recalculation, and
   carried-position lifecycle-opening paths. Runtime implementation remains
   `NONE`; broker/paper/live impact remains `NONE`.

0.34. `TODO` Resolve the exact capture gaps preventing a complete real S23
   Call-side packet: authoritative S23 Call-side legacy result, pre-market S23
   plan, Monthly Status, completed historical references, ORPT
   selected-contract quote, option OI values, and recalculation inputs/results.
   Keep capture disabled in normal profiles and keep refactored execution
   authority at `NONE`.

0.33. `DONE` Attempt the first explicitly scoped real non-authoritative S23
   Call-side capture from the existing `2026-06-05` post-market TradingData
   session. Result: one `PARTIAL_CAPTURE` packet and gap matrix were produced;
   complete real packets remain `0` because the selected source does not
   contain an authoritative S23 Call-side decision output or full S23
   pre-market plan evidence. Supported S23 vertical cases: `2`. Real S23
   capture sessions attempted: `1`. Partial real packets obtained: `1`.
   Call-side captured parity cases: `0`. Capture default: `DISABLED`.
   Refactored execution authority: `NONE`. Runtime impact: `NONE`.

0.32. `DONE` Implement the smallest disabled-by-default S23 Call-side evidence
   capture hook. Capture now observes completed S23 vertical fixture results
   after the generic orchestrator returns, emits an immutable
   `S23EvaluationCapturePacket` only when an observer/sink is explicitly
   supplied, and isolates sink/serialization/observer failures from decision
   authority. Supported S23 vertical cases: `2`. Evidence classification:
   Bull Call `LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT`; Bear Call
   `LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT`. Real captured packets obtained:
   `0`. Runtime impact: `NONE`.

0.32. `DONE` Begin a captured-evidence replacement task for the two supported
   S23 Call-side vertical cases (`Bull Call`, `Bear Call`) only. Keep the same
   offline pipeline, do not change the generic orchestrator, do not add PUT
   branches, and classify any missing captured evidence explicitly rather than
   inferring rules. Result: no complete real historical Call-side packet was
   found; both Call-side cases improved from `SYNTHETIC_GOLDEN` to
   `LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT` using checked-in workbook-derived strategy configuration
   and `excel_crosscheck.yaml` evidence, with all synthetic supplements and
   missing captured fields disclosed. Supported S23 vertical cases: `2`.
   Fully captured cases: `0`; captured with derived fields: `0`; captured with
   synthetic supplement: `0`; legacy fixture cases: `2`; synthetic-only M5
   cases: `0`. Runtime impact: `NONE`.

0.31. `DONE` Extend the same Phase 3D offline vertical-slice composition to
   Bear Call. Supported S23 vertical cases: `2` (`S23 Bull Call` synthetic
   golden, `S23 Bear Call` synthetic golden). The generic orchestrator remains
   unchanged. Future capability requirements observed around expiry fallback,
   strike traversal, premium/OI phases, MIN-bounded MSL, non-positive risk
   prices, and historical lookbacks were recorded as S23 adapter/report
   evidence only; Contract Selection, Risk, Market Structure, runtime shadow,
   paper/live authority, and PUT authority remain unchanged.

0.30. `DONE` Complete the accelerated Phase 3D Milestone 3 offline S23
   vertical slice: Strategy Resolution -> Contract Selection compatibility
   adapter -> Base Entry -> Gap/Missed-Entry -> Effective Entry -> Target/MSL
   compatibility adapters -> `TFISDecision` ->
   `TFISDecisionEvidencePacket`. Supported S23 vertical cases: `1` (`S23 Bull
   Call` synthetic golden). No runtime shadow, paper authority, live authority,
   broker behavior, lifecycle, risk, execution routing, or strategy
   configuration activation was added.

0.29. `DONE` Complete Phase 3D Milestone 2 Generic Entry Engine Contract
   Design. Entry now exposes explicit Base Entry and Effective Entry contracts,
   product-aware reference identity, bounded formula-component evidence, a
   minimal generic fail-closed shell, catalog capabilities, and optional
   decision-evidence packet integration. Runtime activation remains out of
   scope.

0.28. `DONE` Phase 3D Entry contract design is complete through Milestone 2.
   Correct relationship for applicable strategies is Base Entry ->
   Gap/Missed-Entry -> Effective Entry. S23 PUT authority and S21 ORPT/RC
   applicability remain unresolved and must not be silently fixed during the
   next vertical slice.

0.27. `DONE` Complete Phase 3C Milestone 5 certification. Phase 3C is accepted
   for offline architecture and supported legacy parity with 8 cases, 8
   passing supported comparisons, 0 mismatches, and 2 intentional fail-closed
   cases. Runtime shadow, paper authority, and live-money authority remain not
   ready because S23 PUT authority, S21 ORPT/RC applicability, and full
   captured parity remain unresolved.

0.26. `DONE` Complete Phase 3C Milestone 4 full offline parity/evidence
   reporting for Gap/Missed-Entry. The generated `reports/phase3c/` artifacts
   cover 8 offline cases with 8 passing supported comparisons, 0 mismatches,
   and 2 intentional fail-closed cases, plus a typed
   `TFISDecisionEvidencePacket` fragment sample. Runtime activation remains
   deferred.

0.25. `DONE` Complete Phase 3C Milestone 3 strategy compatibility policies
   and adapters. S21 is represented by evidence-only and unresolved timing
   profiles; S23 has explicit backtest-low and paper/live-high PUT profiles,
   supported branch mapping, ORPT/RC validation, and delegated recalculation
   compatibility outputs. The new path is offline-only and does not activate
   paper/live/replay/backtest runtime behavior.

0.24. `DONE` Complete Phase 3C Milestone 2 Generic Gap and Missed-Entry Engine
   contracts. The new immutable contract module defines supplied timing
   evidence, independent gap classification, independent missed-entry
   classification, downstream recalculation instruction, typed unresolved
   semantics, and minimum decision-evidence fragment integration. The catalog
   now models the combined `gap` engine as providing both `GAP` and
   `MISSED_ENTRY`. No strategy formula or active runtime path was migrated.

0.23. `TODO` Begin Phase 3C by migrating one low-risk business capability
   behind the Phase 3B `BusinessEngine` contract, preferably Market Structure
   or Monthly Status. Keep active paper/live/replay/backtest runtime activation
   disabled until a separate reviewed change proves parity, evidence mapping,
   and operator visibility.

0.22. `DONE` Complete Phase 3B Generic Business Engine Framework. The generic
   domain now has immutable business engine context/input/result/evidence/
   validation/metrics/performance/definition/registry contracts, explicit
   capability and dependency validation, a metadata-only initial catalog for
   Market Structure, Monthly Status, Gap, Entry, Contract Selection, Risk,
   Lifecycle, and Execution Intent, architecture boundary tests, focused unit
   tests, and a generated Phase 3B report. No business logic or active runtime
   path was migrated.

0.21. `DONE` Complete Phase 3A strategy identity and configuration. Strategy
   family, definition, version, instance, resolved configuration, evaluation,
   and position-cycle identity are explicit and immutable; identity fields are
   carried through the generic runtime/decision contracts for offline flows.

0.20. `TODO` Begin Phase 2D only as captured-evidence enrichment and offline
   shadow reporting. Add saved option-chain evidence for the captured S23 Bear
   Put prelude, add saved legacy live-decision summary parity including ORPT/RC
   timing output, and add S21 captured paper evidence before claiming
   operational S21 parity. Runtime activation remains out of scope.

0.19. `DONE` Complete Phase 2C offline shadow parity foundation. The generic
   engine now has Target and MSL policy stages, S21/S23 legacy adapters
   preserve current target/MSL trade-plan evidence, external
   strategy-instance policy composition is validated from
   `config/strategy_policy_composition.yaml`, and captured S23 prelude evidence
   is inventoried as partial because it lacks option-chain data.

0.18. `DONE` Add Phase 2B behavior-preserving S21/S23 policy adapters for
   offline parity. `src/tfis/adapters/legacy_policies` now wraps current
   option-selling product resolution, `StrategyEvaluator` entry formulas, and
   existing option-chain selection behind generic policy contracts, with
   external policy-key composition and deterministic parity tests for all
   configured S21/S23 branch folders. Active runtime paths remain unchanged.

0.17. `DONE` Add the Phase 2A generic decision-orchestration foundation.
   `tfis.decision` now provides immutable typed policy inputs/results, five
   product-neutral policy protocols, explicit policy selection/registry
   composition, deterministic execution order and evidence, and a fail-closed
   `TFISDecisionEngine`. Architecture tests prohibit strategy/broker/execution
   dependencies and strategy-code branches. Active S21/S23 runtime wiring is
   unchanged.

0.16. `DONE` Centralize Windows-safe atomic text writes across active TFIS
   persistence paths. The live-state/order-state fixes from 0.15 are now
   factored into `tfis.storage.atomic_write.atomic_write_text`; paper artifact,
   review, ingress, generated-prelude, FYERS snapshot, fill/lifecycle,
   position/order, broker-order, live operator control, FYERS token, and shared
   supervisor audit writers now use unique temp files with bounded
   `PermissionError` retries instead of fixed `.tmp` names. Validation covered
   the helper directly, the July 28 crash regression paths, and the migrated
   artifact/broker/token test set.

0.15. `DONE` Clear the July 28 active-market stale warning caused by
   filesystem live-state mirror contention. The supervisor crash at 10:34 IST
   was caused by `PermissionError` during `os.replace` under
   `config/tmp/live_state`; the live-state filesystem writer now uses unique
   temp files and short replace retries. A second restart surfaced the same
   Windows contention pattern in paper order event persistence, so
   `PaperOrderStateStore` now uses the same unique-temp/retry-safe write path.
   Validation restarted only the TFIS shared supervisor, confirmed fresh
   S23/S21 heartbeats, verified the supervisor Python process stayed alive
   after multiple poll cycles, and found no new `PermissionError` traces in the
   active launch log.

0.14. `DONE` Apply and validate the July 28 shared-supervisor
   environment-ordering fix during live paper operation. The code now prepares
   provider auth/environment before constructing broker adapters in
   `run_tfis_paper_lifecycle_supervisor.py`; a controlled TFIS-only
   shared-supervisor restart was performed during the July 28 paper session
   without rerunning strategy calculations or touching non-TFIS processes.
   The restarted supervisor verified the existing FYERS token, then reported
   fresh `PAPER_POSITION_HELD` evidence for S23 and
   `PAPER_ORDER_WAITING_FOR_TRIGGER` evidence for S21.

0.12. `DONE` Close the remaining live-paper/live-money readiness gaps
   one by one, updating status docs and tests after each completed slice.
   This queue starts from the July 27, 2026 operator findings: S23/S21 can run
   in controlled paper mode with shared startup and dashboard visibility, but
   TFIS still needs stronger runtime robustness before live-money enablement.
   Ordered implementation list:
   1. `DONE` Clarify post-market dashboard stale stream/heartbeat wording.
      After the `15:30` lifecycle cutoff, stale selected-contract evidence is
      now displayed as closed/final snapshot evidence; active-market stale
      evidence still raises warnings.
   2. `DONE` Fix broker snapshot robustness for FYERS-backed morning decisions.
      Missing/malformed FYERS option-chain or quote payloads should get a
      bounded retry/failover path and clear operator evidence instead of a
      brittle one-shot startup failure. The FYERS-backed S23 snapshot
      collector now retries transient broker/normalization snapshot reads,
      records successful retry evidence in the preflight summary, and still
      fails closed with the exhausted attempt count when broker data remains
      malformed.
   3. `DONE` Make paper trade ledger writes concurrency-safe. Supervisor
      ledger writes must not crash on Windows temp-file replace collisions or
      concurrent appends. Paper trade ledger JSONL writes now append under a
      per-ledger lock file, avoid shared temp-file replace paths, remove stale
      locks, and fail clearly on lock timeout.
   4. `DONE` Clean dashboard/supervisor process reporting so Windows
      parent-child launcher pairs are shown as one logical runtime component
      where appropriate. Runtime status now keeps raw process count visible
      but reports dashboard/supervisor counts from logical components, so a
      PowerShell launcher plus Python child is not double-counted as two
      supervisors.
   5. `DONE` Add active-market shared-supervisor recovery. If the supervisor
      dies during `ACTIVE_MARKET`, TFIS should restart only the shared
      supervisor when recovery evidence is safe, without running a full reset
      or relaunching strategy calculations. The existing reset script now has
      `-RecoverSharedSupervisor`, which refuses outside active market, refuses
      if a supervisor or conflicting launch/recovery process already exists,
      checks guardrails, waiting orders, reconciliation, and order-routing
      safety, then starts only the shared supervisor with dashboard rebuild and
      auth refresh skipped.
   6. `DONE` Improve dashboard freshness and refresh semantics. The operator
      dashboard should show generated-at/data-freshness clearly and avoid
      forcing manual reset scripts for ordinary dashboard visibility. Static
      pages now show a built-at freshness strip, and the dashboard server can
      auto-rebuild stale dashboard pages on normal page requests through a
      configurable `--auto-rebuild-seconds` interval while preserving the
      manual refresh script for immediate rebuilds.
   7. `DONE` Harden S21 operational trust. `S21` now has an explicit
      controlled-paper trust audit covering its reference packet, BankNifty
      lot/strike/OI assumptions, configured monthly expiry value,
      carry-forward/no-carry-past-expiry policy, paper-only guardrails, and all
      four S21 rule folders before it is treated as operationally comparable
      with S23 in paper mode. This is intentionally not live-money approval.
   8. `DONE` Review live-money gates after the runtime fixes. The July 27,
      2026 go/no-go review is recorded at
      `docs/operations/tfis_go_no_go_review_2026-07-27.md`. Live routing
      remains `NO-GO` and disabled until broker truth, idempotency,
      kill-switch, operator approval, reconciliation, and
      websocket/broker-event ingress evidence are all proven through the
      existing live execution gate in a separate reviewed enablement change.

0.13. `TODO` Start the separate live-routing enablement track only when the
   operator is ready to supply broker-truth, broker-event/websocket ingress,
   explicit session approval, kill-switch, idempotency, and reconciliation
   evidence. This must remain a reviewed opt-in change and must route
   exclusively through `validate_live_execution_gate`.

0.0. `DONE` Correct dashboard order/trade terminology before live-money
   operation.
   The dashboard now treats a finalized order as an order, not an open trade:
   `trades/index.html` is the Active Trades Monitor for filled/open paper
   positions only, `orders/index.html` is the consolidated Orders Manager for
   waiting/actionable finalized paper orders across strategies, and strategy
   pages now show separate `Active Trades` and `Orders Finalized` sections.
   Remaining follow-up: the same vocabulary should be carried into any future
   broker-backed live execution page so broker order state, TFIS order state,
   and open positions never share one ambiguous "trade" label.

0.05. `DONE` Remove strategy-wrapper serialization from TFIS Morning Startup.
   The July 23, 2026 live-paper startup proved that launching configured
   wrappers one by one is not acceptable for multi-strategy TFIS operation:
   S21 was delayed behind S23. The current fix launches all configured morning
   wrappers concurrently after shared auth preparation, then waits for all of
   them before starting the shared lifecycle supervisor.

0.06. `DONE` Make runtime recovery status market-phase aware.
   The July 23, 2026 post-market status view exposed a misleading recovery
   signal: stale cutoff heartbeats and zero visible supervisor processes were
   reported as `ACTION_REQUIRED` even after every current waiting order had
   reached a terminal not-filled state. The status console now prints
   `MarketSessionPhase`, asks for supervisor recovery only during
   `ACTIVE_MARKET`, reports `AFTER_MARKET_IDLE` after cutoff when current
   order/reconciliation checks are clean, widens lifecycle-audit freshness
   outside market hours, and ignores missing supervisor-audit files for
   terminal historical paper orders. Follow-up: add a stronger process/runtime
   status detector so Windows venv launcher PIDs and real Python PIDs do not
   make process counts look inconsistent when the port/heartbeat evidence is
   otherwise clear.

0.07. `DONE` Strengthen Windows TFIS process/runtime detection.
   Current operator status can still show zero dashboard/supervisor processes
   even when dashboard port readiness, heartbeat owner ids, or direct host
   inspection prove TFIS components were active. Fix the shared PowerShell
   process helper so it discovers both Windows virtualenv launcher processes
   and real Python child processes consistently, keeps matching scoped to the
   TFIS repo root, and reports clearer process roles without changing runtime
   behavior. Completed on Thursday, July 23, 2026: the shared runtime process
   helper now accepts slash-normalized repo paths, carries child processes of
   directly matched TFIS launchers, classifies dashboard/supervisor/strategy/
   watcher/maintenance roles, and falls back from `Get-NetTCPConnection` to
   `netstat -ano` plus `Get-Process` for dashboard port-owner evidence.
   `show_tfis_runtime_status.ps1` now reports `DashboardPortOwnerProcesses`
   and prints `Role=dashboard_port_owner` when command-line evidence is
   unavailable; the real host status now reports `DashboardProcesses=1` for
   the listening dashboard instead of zero.

0.08. `DONE` Tighten active-market stale quote and heartbeat handling.
   During active market hours, open positions and waiting orders must not keep
   advancing lifecycle decisions on stale or ambiguous selected-contract
   market data. Identify the current freshness checks in the shared paper
   lifecycle supervisor, make stale selected-contract evidence fail closed with
   explicit heartbeat/audit/operator status, add focused tests, and keep the
   change paper-safe without altering strategy entry, target, SL, FSL, or
   rollover rules. Completed on Thursday, July 23, 2026: the shared lifecycle
   supervisor runner now has an explicit
   `--max-selected-contract-event-age-seconds` gate, defaulting to `120s`;
   successful but stale, missing, or future-dated selected-contract events are
   treated as `MARKET_DATA_UNAVAILABLE`, persisted to heartbeat/audit evidence,
   and skipped before order/position lifecycle logic can run. Focused runtime
   coverage proves stale selected-contract data does not fill waiting orders,
   does not append selected-contract market-event evidence as valid runtime
   input, and leaves the paper order unchanged.

0.09. `DONE` Prove multi-day open-position startup/resume with broker
   truth evidence.
   TFIS already has paper carry-forward state and broker-neutral live recovery
   contract models, but the next live-money-readiness gap is to make the
   startup/resume evidence explicit: open or carried positions must be checked
   against supplied broker position/order-book truth before any future live
   supervisor can manage them. Keep this as broker-neutral evidence and
   readiness logic only; do not enable live order routing. Completed on
   Friday, July 24, 2026: `validate_live_position_startup_resume` now requires
   supplied broker position truth whenever TFIS expects non-zero open/carry
   positions, delegates detailed mismatch detection to the existing broker
   reconciliation engine, and returns explicit startup/resume validation
   evidence for `PRE_STARTUP`, `AFTER_RESTART`, and other reconciliation
   scopes. Focused tests cover matching broker truth, missing broker truth,
   and broker quantity mismatch.

0.10. `DONE` Wire a deliberately disabled live execution adapter gate.
   The broker-order state, idempotency, reconciliation, live exit-protection,
   market-event ingress, startup/resume, and operator-control contracts now
   exist independently. The next live-money-readiness step is to connect those
   contracts into one broker-neutral live execution gate that remains disabled
   by default and proves no live order can be routed unless every required
   validation has passed and live routing is explicitly enabled. Completed on
   Friday, July 24, 2026: `src/tfis/broker/live_execution_gate.py` exposes
   `validate_live_execution_gate`, which blocks routing unless live routing is
   explicitly enabled, durable broker-order intent exists, idempotency
   reservation is active and non-duplicate, operator controls pass, exit
   protection passes, market-event ingress passes, startup/resume evidence
   passes, and broker reconciliation passes. The live-money boundary status
   now includes `LIVE_EXECUTION_GATE_DISABLED_BY_DEFAULT`, and focused tests
   prove the disabled path remains blocked even when every other contract
   passes.

0.11. `DONE` Complete the July 24 live-money go/no-go review.
   `docs/operations/tfis_go_no_go_review_2026-07-24.md` records the current
   decision: paper-live is `GO` for the blocked paper operating contract, live
   execution contract infrastructure is implemented but disabled, and
   live-money routing remains `NO-GO` until a separate reviewed enablement
   change routes exclusively through `validate_live_execution_gate` with
   broker truth, broker-event/websocket ingress, operator approval, kill
   switch, idempotency, and reconciliation evidence present.

0.1. `DONE` Establish one TFIS application-startup contract before
   adding any live-order capability.
   TFIS must start as one application that can manage many enabled strategies,
   not as one scheduled task per strategy racing for shared broker/runtime
   resources. Work the startup/live-readiness TODO list in this order:
   1. Update the project status docs with this ordered queue before code
      changes.
   2. Move FYERS token preparation to an application/provider-owned contract:
      validate the existing TFIS token first, refresh only when invalid or
      missing, and serialize refresh work behind one TFIS-owned lock.
   3. Correct the existing TFIS startup/reset path instead of inventing
      duplicate scripts, so one entrypoint can build and serve the dashboard,
      run all enabled morning supervised decisions with shared auth already
      prepared, and start one shared lifecycle supervisor.
   4. Replace or retire the separate S21/S23 morning scheduled-task startup
      pattern in favor of the single TFIS application startup task, while
      preserving strategy-specific wrappers as direct/manual compatibility
      tools.
   5. Make startup process handling market-phase aware: pre-market startup may
      clean stale app-owned processes, but in-market recovery must avoid
      killing active supervisor/strategy processes unless an operator passes an
      explicit force path.
   6. Generalize startup orchestration through enabled strategy config/registry
      so future S24/S25/... strategies do not require more copied scheduled
      scripts.
   7. Keep the current lifecycle path explicitly paper-safe and polling-based
      until a separate live-order execution layer is designed, implemented,
      reconciled against broker truth, and approved.
   8. Add focused unit/integration tests after each slice, run validation, then
      update `current_state.md`, `next_steps.md`, and `milestones.md` before
      marking that slice done and moving to the next item.
   Completed slices as of Wednesday, July 22, 2026:
   - documentation queue frozen in `current_state.md`, `next_steps.md`, and
     `milestones.md`
   - FYERS auth preparation now validates the existing TFIS token first,
     refreshes only when required, and serializes refresh work behind a
     TFIS-owned lock
   - existing `scripts/reset_tfis_dashboard_and_watchers.ps1` now has an
     opt-in `-MorningStartup` application path that does not stop existing
     runtime processes automatically, builds/serves the dashboard, prepares
     broker runtime auth once per configured provider from the lifecycle target
     config, launches configured morning wrappers sequentially with
     `-SkipRefresh`, and starts one shared supervisor
   - `scripts/fyers_token_refresh.py --prepare` now exposes the same
     validate-or-refresh behavior for startup use while the default command
     still forces a refresh for direct operator refresh runs
   - host Windows Task Scheduler was migrated on Wednesday, July 22, 2026:
     `TFIS Morning Startup` is enabled for weekdays at `09:08` and points to
     `scripts/reset_tfis_dashboard_and_watchers.ps1 -MorningStartup`; the old
     `TFIS S21 Morning Supervised Decision` and
     `TFIS S23 Morning Supervised Decision` tasks are disabled so they no
     longer race for auth refresh
   - the manual operator guide now documents the single app startup task and
     labels the old S21/S23 task checks/registration paths as legacy
     compatibility surfaces
   - full reset is now market-session guarded: during `09:15-15:30` on a
     trading day, `scripts/reset_tfis_dashboard_and_watchers.ps1` refuses to
     stop TFIS runtime unless the operator passes `-ForceInMarketReset`; the
     dashboard-only refresh path remains the safe in-market dashboard update
     route
   - startup orchestration no longer hardcodes one S21/S23 launch branch in the
     reset script: morning wrappers are discovered from
     `config/paper_lifecycle_supervisor_targets.yaml`, and broker auth
     preparation is grouped by configured runtime provider before wrappers are
     launched with `-SkipRefresh`
   - focused validation passed:
     `tests/unit/test_fyers_token_auth.py`,
     `tests/unit/test_fyers_token_refresh_script.py`,
     `tests/unit/test_paper_lifecycle_supervisor_runtime.py`,
     `tests/unit/test_s23_live_decision_runner.py`,
     `tests/unit/test_s23_live_decision_task.py`,
     `tests/unit/test_tfis_reset_runtime_script.py`,
     `tests/unit/test_s23_powershell_wrappers.py` at `80 passed`, plus
     `scripts/validate_project.py`
   Next slice:
   `DONE`: design the live-money execution/reconciliation boundary separately
   from the current paper polling lifecycle before any live order-routing code
   is added.
   Completed on Wednesday, July 22, 2026:
   - `docs/operations/tfis_live_money_execution_reconciliation_boundary.md`
     now records the current paper polling behavior, live-money blocked
     status, and required gates for broker order state, idempotency, broker
     reconciliation, partial fills, live exit protection, event ingress,
     multi-day recovery, and operator approval
   - `src/tfis/paper/live_money_boundary_status.py` and
     `scripts/show_tfis_live_money_boundary_status.py` expose the same
     boundary as machine-readable operator evidence
   - `scripts/pre_live_readiness.py` now includes a
     `live_money_boundary` check that passes only while live-money order
     routing remains intentionally blocked and required gates are explicit
   - validation passed:
     `tests/unit/test_live_money_boundary_status.py`,
     `tests/unit/test_pre_live_readiness_script.py`, the focused startup/
     runtime/broker-boundary pack at `95 passed`, `scripts/validate_project.py`,
     `scripts/show_tfis_live_money_boundary_status.py --json`, and
     `scripts/pre_live_readiness.py --profile prod --json`
   Next slice:
   `DONE`: re-verify paper runtime invariants for the current supported paths:
   shared supervisor startup contract, dashboard rebuild/serve, S21/S23
   waiting-order recovery rules, carry-forward-only recovery, stale
   waiting-order suppression, historical-trade separation, and operator
   dashboard consistency.
   Completed on Wednesday, July 22, 2026:
   - focused invariant pack passed at `105 passed`:
     `tests/unit/test_operator_dashboard.py`,
     `tests/unit/test_s23_captured_session_validation.py`,
     `tests/unit/test_s23_paper_watch_market_event_persistence.py`,
     `tests/unit/test_paper_lifecycle_supervisor_runtime.py`,
     `tests/unit/test_paper_lifecycle_market_events.py`,
     `tests/unit/test_s23_paper_lifecycle_supervisor.py`,
     `tests/unit/test_s23_paper_position_state.py`, and
     `tests/unit/test_selected_contract_market_events.py`
   - `scripts/build_operator_dashboard.py --output-root tmp/operator_dashboard`
     succeeded and generated index, all-trades, S21, S23, and dashboard
     manifest artifacts
   - `scripts/validate_project.py` passed
   Next slice:
   close the remaining live-money-readiness gaps in this order:
   1. strengthen Windows process/runtime detection so process counts agree
      with dashboard port readiness and heartbeat owner evidence
   2. tighten active-market stale quote and heartbeat handling so active
      positions cannot continue on ambiguous market data
   3. prove multi-day open-position startup/resume using broker-truth
      reconciliation evidence, not only TFIS paper files
   4. connect the existing broker-order/idempotency/reconciliation/approval
      contracts into a deliberately disabled live execution adapter path, with
      tests showing live routing remains blocked unless every gate passes
   5. run a final go/no-go review before any real live-order enablement

0.5. Remove the remaining S21/S23 morning startup auth race that was exposed on
   Wednesday, July 22, 2026.
   Today's market-time recovery proved that the paper runtime can be rescued,
   but it also proved the current startup design is still suboptimal: S21 and
   S23 can compete for FYERS token/auth refresh at the same startup moment.
   The wrapper retry with `--skip-refresh` is now in place as a safety net, but
   the next engineering step is now folded into item `0.1`: TFIS should
   validate or refresh auth once at the application/provider layer, then launch
   strategy workflows with refresh skipped.

0. Execute the weekend live-money-readiness track in strict order, without
   bypassing paper-safety gates.
   The repository contract still applies: TFIS must remain safe for paper
   trading and research before any live-order capability is considered.
   Therefore this weekend's goal is not to silently flip TFIS into live mode;
   it is to close the operational, architectural, observability, and recovery
   gaps that currently block a credible live-money decision. Work this list in
   order, and do not mark the system live-money ready until every gate below
   has passed:
   1. Freeze the execution track in docs before code changes. Keep
      `docs/operations/current_state.md`, this queue, and any focused status
      notes aligned so an operator can tell what weekend step is in progress.
   2. Re-verify paper runtime invariants for the current supported paths
      (shared supervisor startup, dashboard rebuild/serve, S21/S23 waiting
      order recovery rules, carry-forward-only recovery, stale waiting-order
      suppression, and historical-trade separation).
   3. Close same-day lifecycle correctness gaps that would be unacceptable in
      live money, especially duplicate supervision, stale quote handling,
      cutoff behavior, fresh-recalculation handoff after position close, and
      dashboard/operator consistency.
   4. Harden process recovery and operator control paths so reboot, reset, and
      scheduled-task restart behavior are deterministic and observable from one
      TFIS console path rather than scattered wrapper behavior.
   5. Harden broker/runtime ingress boundaries: configuration validation,
      adapter bootstrap, reconnect/failure posture, missing-stream fallback,
      and explicit preflight evidence for token/runtime readiness.
   6. `DONE` Tighten state reconciliation rules for waiting orders, open
      positions, closed positions, carry-forward positions, and historical-
      ledger promotion so no trade can appear active and historical at the
      same time.
   7. Strengthen live guardrails before any live-order consideration:
      explicit dry-run/live toggle enforcement, fail-closed startup on missing
      prerequisites, operator-visible kill/pause/recovery steps, and audit
      logging for every lifecycle transition.
   8. Re-run focused tests after each step, then re-run the broader readiness
      suite at the end of the weekend track. A step is not complete until its
      tests and operational spot-checks pass and the docs say so.
   9. Only after all prior steps pass, prepare a final go/no-go review that
      lists the remaining live-money risks, open questions, and what manual
      controls still exist.

   Update as of Tuesday, July 21, 2026:
   the shared paper naming refactor now reaches through review summaries,
   replay-bundle management, and paper-vs-historical comparison contracts.
   The next immediate action is to run the current readiness audit on that
   shared surface and fix any paper-trading blockers the audit exposes.
   Update later on Tuesday, July 21, 2026:
   the morning paper-start blocker exposed by today's scheduled run has now
   been corrected for S23: the wrapper accepts scheduler launches without an
   explicit `RunDate`, and the shared process-lock path now distinguishes a
   truly matching live process from a reused Windows PID before it blocks a
   new launch. The next immediate runtime follow-up is to review whether the
   S21 scheduled wrapper should emit more explicit completion/failure evidence
   in its task logs when the real supervised run remains alive beyond wrapper
   exit visibility.
   Update later still on Tuesday, July 21, 2026:
   the consolidated dashboard monitor now anchors waiting/not-filled trade
   visibility to the later of the current operator day and the newest
   discovered strategy session date, so stale prior-day unfilled rows no
   longer leak back into active all-trades or chart-review surfaces when a
   strategy has not yet produced a fresh session. The next immediate
   follow-up remains the broader live-money-readiness backlog rather than more
   dashboard-local active/historical row filtering. A same-day follow-up slice
   has now also aligned each strategy page to that same current-day anchor
   rule, so stale past-session waiting/not-filled rows no longer appear inside
   a strategy page's active monitor or Operator Status panel just because that
   strategy has not produced a fresh session today.
   Update on Wednesday, July 22, 2026:
   the reconciliation slice is now extended beyond positions. The
   `paper_runtime_reconciliation` check confirms persisted position states
   against trade-ledger authority and paper order states against their latest
   order-event trail, with actionable waiting-order and filled-order conflicts
   failing readiness evidence. The configured S23/S21 roots currently report
   zero conflicts, prod readiness remains PASS, and the next immediate action
   is item 7: strengthen live guardrails/operator-visible recovery before any
   live-order consideration.
   Later on Wednesday, July 22, 2026:
   the first item 7 auditability sub-slice is done. The shared supervisor now
   writes per-state `paper_lifecycle_supervisor_events.jsonl` rows for
   lock-busy skips, selected-contract market-data unavailable skips, stale
   waiting-order expiration, and emitted lifecycle steps. This improves
   recovery review without changing paper lifecycle behavior or enabling live
   routing. The next item 7 sub-slice should focus on a read-only status check
   for lifecycle-audit freshness/completeness so missing supervisor evidence
   is visible before live-order consideration.
   Later again on Wednesday, July 22, 2026:
   the lifecycle-audit status/readiness sub-slice is done. TFIS now has
   `show_paper_runtime_lifecycle_audit_status.py`, the runtime status console
   includes a `LifecycleAudit` section, and pre-live readiness includes
   `paper_runtime_lifecycle_audit`. The check fails invalid audit evidence and
   surfaces legacy missing audit evidence as `ATTENTION`. This pass also used
   the existing configured finalizer after the `2026-07-22` cutoff to close
   the two stale actionable S21 waiting orders from `2026-07-21`; current
   S21/S23 actionable stale order count is zero and prod readiness remains
   PASS. The next item 7 sub-slice should make stale actionable waiting-order
   detection an explicit readiness gate independent of the lifecycle-audit
   evidence age.
   Final Wednesday, July 22, 2026 update for this slice:
   stale actionable waiting-order detection is now its own readiness gate.
   `show_paper_runtime_waiting_order_status.py` reports current-session versus
   stale waiting paper orders per configured strategy, `show_tfis_runtime_status.ps1`
   includes `WaitingOrders`, and `pre_live_readiness.py` fails when any
   configured strategy still has a prior-session or future-dated
   `PAPER_ORDER_WAITING_FOR_TRIGGER` order. Current S21/S23 configured status
   is clean at `waiting=0/current=0/stale=0`, and prod readiness remains PASS.
   The next item 7 sub-slice should strengthen operator pause/recovery audit
   evidence and restart determinism: prove pre-live readiness and the status
   console show enough information to explain who paused/resumed TFIS, what
   scope was affected, and whether any restart/recovery action is still
   pending.
   Follow-up completed on Wednesday, July 22, 2026:
   operator pause/resume evidence now includes action, scope, strategy,
   timestamp, actor, reason, and marker path in both pre-live readiness and
   `show_tfis_runtime_status.ps1`. Active pause markers still fail readiness;
   clear latest events remain visible without failing.
   Restart/recovery status completed on Wednesday, July 22, 2026:
   `show_tfis_runtime_status.ps1` now emits `RestartRecoveryStatus`, deriving
   `RUNNING`, `ACTION_REQUIRED`, or `READY_FOR_MORNING_STARTUP` from dashboard
   port readiness, dashboard/supervisor/other TFIS process counts, and stale
   waiting-order status. The current post-market host reports
   `READY_FOR_MORNING_STARTUP` with pending action `run_morning_startup`.
   Follow-up on Thursday, July 23, 2026:
   the runtime status console is now market-phase aware. Missing supervisor
   visibility is an active-market recovery action, not an after-market restart
   demand; terminal historical paper orders no longer create missing audit
   attention; and the current post-market console reports
   `AFTER_MARKET_IDLE pending=none` with lifecycle audit, waiting orders, and
   reconciliation passing.
   Go/no-go review completed on Wednesday, July 22, 2026:
   `docs/operations/tfis_go_no_go_review_2026-07-22.md` records `GO` for the
   current blocked paper-live operating contract and `NO-GO_FOR_LIVE_MONEY`
   until the remaining 7 live execution/reconciliation gates are implemented,
   tested, documented, and explicitly approved.
   Broker order-state model completed on Wednesday, July 22, 2026:
   `src/tfis/broker/broker_order_state.py` now provides a broker-agnostic
   state/event model and JSON/JSONL store for broker order ids, exchange
   ids/statuses, acknowledgements, rejects, cancels, modifications, fills,
   timestamps, and event history. This is model/evidence only; live order
   routing remains blocked.
   Idempotent routing contract completed on Wednesday, July 22, 2026:
   `src/tfis/broker/broker_order_idempotency.py` now provides deterministic
   restart-stable client order ids, durable reservations, duplicate
   reservation suppression, explicit retry attempts, and consumed-reservation
   linkage to broker-order state. This is route-safety infrastructure only;
   live routing remains blocked.
   Broker position/order-book reconciliation completed on Wednesday,
   July 22, 2026:
   `src/tfis/broker/broker_reconciliation.py` now compares TFIS position
   expectations and persisted broker-order state with supplied broker
   position/order-book snapshots for pre-startup, during-supervision, and
   after-restart scopes. This is comparison infrastructure only; live routing
   remains blocked.
   Partial-fill/reject handling completed on Wednesday, July 22, 2026:
   broker-order state now models pending, partial-fill, filled, rejected,
   stale, cancel-failed, and modify-failed transitions with durable
   quantities, reject/failure reasons, timestamps, and shared operator-
   attention classification.
   Live exit protection completed on Wednesday, July 22, 2026:
   `src/tfis/broker/live_exit_protection.py` now validates target, stoploss,
   forced-close, emergency-exit, and kill-switch protection rules, including
   market-event-ingress and operator-approval requirements. This is
   protection-contract infrastructure only; live routing remains blocked. The
   Live market-event ingress completed on Wednesday, July 22, 2026:
   `src/tfis/broker/live_market_event_ingress.py` now validates websocket or
   broker-event mode, fresh heartbeat, required symbol subscriptions/evidence,
   duplicate-sequence rejection, and monotonic event ordering; polling-only
   evidence fails this contract.
   Multi-day live-position recovery completed on Wednesday, July 22, 2026:
   `src/tfis/broker/live_position_recovery.py` now validates overnight,
   expiry, forced-close, rollover-required, and next-day resume scenarios with
   broker truth and reconciliation required for every case.
   Operator live approval/kill-switch completed on Wednesday, July 22, 2026:
   `src/tfis/broker/live_operator_controls.py` now records expiring live-mode
   approvals, kill-switch state, and durable JSONL audit events, and validates
   that approval is explicit, unexpired, audited, and that kill switch is
   available and inactive. The eight live-money contract gates are complete.
   Live routing remains disabled until an operator approval artifact exists
   and a separate reviewed change enables broker routing.

1. Phase 1 runtime-consistency refactor, Phase 2 runtime-contract/read-model
   consolidation, and the first full Phase 3 lifecycle-supervisor cutover are
   now complete for the current scope. As of Friday, July 17, 2026, TFIS uses
   one shared paper lifecycle supervisor process across the supported S21/S23
   operational paths, compatibility launcher shims keep the older watcher
   commands usable, and the local readiness gate now validates
   `config/paper_lifecycle_supervisor_targets.yaml` in addition to dashboard
   and strategy config health. The first Phase 4 slice is also now in place:
   the shared supervisor bootstrap resolves its broker adapter and minimal
   runtime settings through `src/tfis/paper/lifecycle_runtime_config.py`
   instead of hardcoding `FyersBrokerAdapter` plus the S23 ingress config type
   directly in the runtime entrypoint. The next small Phase 4 slice is also in
   place: that same shared runtime-config layer now owns broker-runtime
   environment preparation, so the shared supervisor no longer imports FYERS
   token/bootstrap helpers directly and now prepares each provider only once
   before connecting adapters. A second additive Phase 4 slice is now also
   completed after market: TFIS has a shared
   `src/tfis/paper/lifecycle_market_events.py` selected-contract fetch-policy
   abstraction with focused tests, and the shared supervisor now uses that
   path instead of its former inline helper while preserving the same SL-reset
   bar-fetch warning behavior. The legacy S23 compatibility watcher now also
   uses that same shared fetched quote/bar policy while preserving its
   stream-tick-first fallback. The next architecture move should therefore
   stay focused on Phase 4 broker/data-source separation rather than more
   Phase 3 micro-slices. As of Saturday, July 18, 2026, the first explicit
   Step 4 ingress-health slice is also complete: TFIS now has shared live-
   state store diagnostics, pre-live readiness now fails clearly when a
   configured live-state backend is unavailable, and both the shared
   supervisor and the S23 compatibility watcher now fail closed during
   bootstrap instead of silently degrading to a null live-state store when
   Redis was configured but unreachable. As of Sunday, July 19, 2026, the
   next Step 4 slice is also complete: TFIS now supports a local filesystem
   live-state backend for the active paper configs, so supported paper startup
   no longer depends on Redis being up on the workstation, and the
   pre-live-readiness gate now verifies that each configured paper broker
   runtime can be assembled through the shared bootstrap seam, including auth
   prerequisite preparation when `--require-token` is supplied. As of Sunday,
   July 19, 2026, the next runtime-posture slice is also complete: both the
   shared supervisor and the S23 compatibility watcher now use one shared
   broker runtime connect/health helper, so actual adapter startup failures
   are reported with strategy/provider context instead of surfacing as generic
   runtime errors. The same Sunday, July 19, 2026 runtime-safety pass now
   also removes the old compatibility-watch loophole where selected-contract
   quote fetch failure could leave the S23 watcher alive without trustworthy
   evidence; if no usable stream evidence exists and the shared quote fetch
   fails, that watcher now fails closed. The next Step 4 slice should stay on
   broader market-data-trustworthiness policy plus operator-visible runtime
   health surfacing, before moving on to state-reconciliation work. The
   immediate reconnect/failure-posture sub-slice is now in place as of
   Monday, July 20, 2026: the shared lifecycle runtime rechecks broker health
   during supervisor loops, attempts one reconnect through the shared
   broker-neutral helper when an adapter reports an unhealthy state, and
   fails closed with explicit strategy/provider context if the runtime stays
   unhealthy after that reconnect. The
   S21/S23 recovery launchers now also identify
   themselves explicitly as supervisor-compatibility launchers rather than
   watcher launchers. The S23 morning wrapper has now also dropped its dead
   pre-supervisor watcher-launch fallback and updated its surviving startup
   logs to supervisor wording, so the remaining likely extraction point is
   shared wrapper/startup helper reuse rather than more watcher-era cleanup in
   that script itself. The same wrapper now also centralizes its shared-
   supervisor launch block behind one local helper, so the next likely cleanup
   is reuse across S21/S23 wrappers rather than more branch duplication inside
   the S23 wrapper alone. The S21 supervised Python entrypoint now also names
   its shared lifecycle bootstrap as supervisor startup rather than watcher
   startup, and the market-closed no-action messages for both S21 and S23 now
   say no supervisor startup was triggered. The TFIS reset/recovery script now
   also describes stale waiting-order skips, duplicate targets, and launched
   compatibility processes as supervisor recovery actions rather than watcher
   startup. The same reset/recovery script now also uses `Recovery` helper
   naming internally instead of `Watcher` helper naming for those
   compatibility-target scans and launches. Its last dead inline target-scan
   logic should now give way to the next explicit refactor seam: shared
   session/trade-state authority across finalization, dashboard rendering, and
   promotion flows wherever they still reconstruct â€œlatest authoritative
   session or latest authoritative trade stateâ€ independently beyond the new
   shared paper-session discovery helpers.
   The next small candidate inside that seam is the remaining mix of direct
   position/trade-history scans and dashboard-local sparse-artifact fallback
   truth for historical versus active trade-state authority, now that session
   discovery, active pending-order discovery, branch decision-summary
   discovery, branch-explainer path discovery, raw order-state
   candidate-path discovery, session/global trade-ledger path discovery,
   decision-summary sibling-artifact discovery, terminal-row backing truth,
   preferred supervised-stage selection, finalized-session stage-artifact path
   naming, authoritative final trade-decision artifact-directory resolution,
   shared supervised-session completion checks, session-contract symbol
   discovery, canonical paper supervised executor naming across strategy
   execution-plan plus supervisor-target loading, and selected-contract market-
   event path plus PID handling have all now been centralized as of Tuesday,
   July 21, 2026.
   branch has now also been removed, so reset once again has one narrow role:
   rebuild the dashboard, start the dashboard server, and launch the shared
   supervisor. The reset path, S21/S23 supervisor-compatibility launchers, and
   S23 morning wrapper now also share one PowerShell supervisor-launch helper,
   and the generic resumable-position filesystem scan now lives in the shared
   paper-position helper for both S21/S23 morning wrappers. Shared holiday
   calendar parsing, effective-run-date/no-run gating, shared path
   normalization, and shared Python/log bootstrap helpers are now in place
   too, and latest-session metadata lookup is now shared as well. The shared
   Python runtime now also resolves live-state store and expiry-governance
   bootstrap through generic factories, and the shared lifecycle supervisor no
   longer defaults straight to `S23PaperPositionManager()` inline. The next
   same-day waiting-order recovery in the legacy S23 watch path now also uses
   shared paper-order discovery instead of inline `paper_order_state.json`
   scanning, and the morning supervised launch path now exposes a neutral
   paper runner/checkpoint/result contract while both S21 and S23 launcher
   scripts share one market-closed no-action rule plus one process-lock path
   helper. As of Tuesday, July 21, 2026, the shared prelude builder/error/
   request/result/mode contract plus the shared snapshot-session read-models
   now also have neutral paper aliases consumed by the shared decision
   builder, timeline builder, FYERS snapshot collector, generated prelude
   dry-run runner, and operator dashboard. The next likely Phase 4 cleanup is
   the collector/preflight public surface: as of Tuesday, July 21, 2026, the
   FYERS snapshot collector/preflight artifact, error, issue, summary, and
   provenance types now also have neutral paper aliases consumed by the
   shared live-decision runner, snapshot-validation harness, and
   live-decision-check CLI. The next Tuesday, July 21, 2026 runtime-input and
   live-reference slice is now also complete: the decision-reference loader,
   decision/monthly-status/market reference packets, derived runtime inputs,
   runtime-input derivation error/deriver, and live reference derivation
   error/result/deriver now expose neutral paper aliases, and the shared
   live-decision builder, timeline builder, live-decision runner, operator
   dashboard, and S21 morning wrapper now consume those shared names directly.
   The next Tuesday, July 21, 2026 planning-foundation slice is now also
   complete: guardrail evaluator/settings, paper contract validator, paper
   session-manifest builder, paper order-plan, paper session orchestrator, and
   paper session snapshot now all expose neutral paper aliases, and the shared
   ingress dry-run plus paper-artifact surfaces now consume those planning
   aliases directly. The next Tuesday, July 21, 2026 ingress dry-run/read-
   model slice is now also complete: ingress dry-run error/readiness,
   thresholds, timing audit, ingress health metrics, selected-contract audit,
   dry-run summary/artifact-set, normalized event loader, and ingress dry-run
   runner now all expose neutral paper aliases on the shared import surface.
   The next likely Phase 4 cleanup is deciding whether the remaining S23-only
   wrapper metadata/output-review
   logic is truly generic enough to extract, while also reviewing whether the
   remaining reusable lifecycle/review/live-paper layers still expose any
   S23-shaped type names that should become neutral aliases or factories
   before adding more strategies. The lifecycle supervisor itself has now
   moved to neutral paper expiry-governance and paper position-manager
   aliases, and the legacy S23 compatibility watch no longer depends on
   `S23LivePaperIngressConfig` for bootstrap. The next likely seam is
   therefore the remaining S23-only live-ingress/live-decision bootstrap side
   rather than the already-shared supervisor core. The live-decision runner
   and morning timeline runner now already share broker-runtime environment
   preparation through the paper runtime-config layer, so the next likely seam
   is either the remaining S23-only ingress config surface itself or the last
   direct FYERS bootstrap consumers outside the shared runtime-prep path.
   The dashboard-serving helper has now also been moved onto the shared
   runtime-prep layer, and the first neutral ingress-config aliases are now in
   place too. The FYERS snapshot collector and generated-prelude dry-run
   runner now also consume the neutral `PaperLiveIngressConfig` and
   `PaperExpiryGovernance` aliases for shared runtime/config plumbing. The next
   likely seam is therefore the remaining S23-only ingress read-model and
   prelude behavior rather than another top-level bootstrap or config
   entrypoint. The reusable prelude and paper position-manager layers now also
   type their expiry-governance dependency through the neutral
   `PaperExpiryGovernance` alias. The next Tuesday, July 21, 2026 follow-
   up slice has now also moved `paper_vs_historical.py` onto the neutral
   `PaperSessionReviewer` / `PaperReviewSummary` / `PaperReviewError`
   contracts while preserving the older S23 comparison exports. The impacted
   comparison/execution/lifecycle regression pack passed at `137 passed`. The
   next Tuesday, July 21, 2026 follow-up slice has now also cut
   `expiry_governance.py` and `lifecycle_supervisor.py` over to the neutral
   shared order/position/event aliases while preserving their outward S23
   compatibility exports, and the impacted regression pack for that slice
   passed at `108 passed`. The next Tuesday, July 21, 2026 follow-up slice has
   now also moved `live_prelude.py`, `live_decision.py`,
   `live_decision_timeline.py`, and `trade_ledger.py` onto the neutral paper
   position-state aliases while preserving their outward S23 contracts, and
   the impacted regression pack for that slice passed at `116 passed`. The
   next Tuesday, July 21, 2026 follow-up slice has now also moved
   `order_finalizer.py` and `fresh_entry_promotion.py` onto the neutral
   `PaperOrderState...` aliases while preserving their outward S23 contracts,
   and the impacted regression pack for that slice passed at `115 passed`. The
   next Wednesday, July 22, 2026 follow-up slice has now also moved
   `position_manager.py` onto the neutral paper order/live-state aliases and
   `live_state_store.py` onto neutral paper-first class and factory names,
   while preserving their outward S23 compatibility aliases and wrappers. A
   same-day repair pass then completed the interrupted `position_manager.py`
   declaration cutover itself, so that module now declares
   `PaperPositionManager...` types first and keeps the S23 names as
   compatibility aliases with the focused regression pack and local `prod`
   readiness both green again. The impacted regression packs for those slices
   passed at `124 passed` and `155 passed`. The next likely Phase 4 cleanup is
   therefore the remaining generic runtime modules that still type shared
   state through direct S23 names beyond those live-decision, orchestration,
   order-state, position-state, and live-state surfaces. The same Wednesday,
   July 22, 2026 follow-up slice has now also moved `order_state.py` itself
   onto paper-first status/state/event/discovery/store names while preserving
   the outward S23 aliases, with the impacted regression pack passing at
   `143 passed` and local `prod` readiness staying green. A later Wednesday,
   July 22, 2026 slice then also moved `position_state.py` onto
   paper-first status/event-type/state/event/store names while preserving the
   outward S23 aliases, with the impacted regression pack passing at
   `131 passed` and local `prod` readiness still green. A later Wednesday,
   July 22, 2026 slice then also moved `trade_ledger.py` onto paper-first
   ledger event-type/row/store names while preserving the outward S23 aliases,
   with the impacted regression pack passing at `139 passed` and local `prod`
   readiness still green. A later Wednesday, July 22, 2026 slice then also
   moved `lifecycle_supervisor.py` onto paper-first context/step/result/
   supervisor names while preserving the outward S23 aliases, with the
   impacted regression pack passing at `139 passed` and local `prod`
   readiness still green. The clearest next shared-state follow-up is now the
   remaining generic runtime/read-model surfaces that still expose S23-first
   declarations outside these core state modules.
   `PaperExpiryGovernance` alias, so the next likely decision is how much of
   `src/tfis/paper/live_ingress.py` is truly strategy-specific behavior versus
   shared broker/data-source plumbing that should move behind a neutral seam.
   Its internal loader/preflight/helper signatures now already consume
   `PaperLiveIngressConfig`, its public runner signatures now use neutral
   `PaperLiveIngressSummary` plus `PaperLiveIngressArtifactSet`, and the
   focused ingress regression file now runs through the neutral `Paper*`
   imports rather than the S23-named ingress imports. The remaining work there
   is therefore no longer alias/config/export cleanup; it is deciding whether
   any read-model/event-shaping behavior should be extracted without
   disturbing the current S23 operational path. The ingress CLI wrapper now
   also uses the neutral paper-ingress runner/error symbols, and the operator
   dashboard now consumes shared expiry-governance behavior through
   `PaperExpiryGovernance`, so the remaining Phase 4 work is now genuinely
   about behavioral extraction rather than more safe consumer cutovers. The
   canonical class definitions for shared paper ingress and expiry governance
   are now the neutral `Paper*` types, with `S23*` names retained as
   compatibility aliases only, so the low-risk shared-surface refactor is
   complete and the next move is a deeper behavior/module extraction rather
   than another naming-layer pass.
   The `tfis.paper` package now also exports neutral `PaperBrokerPaperIngressRunner`
   and `PaperLiveIngress*` aliases over the existing S23 ingress runner and
   preflight types, and the runner now also exposes neutral
   `PaperLiveIngressSummary` plus `PaperLiveIngressArtifactSet` aliases in its
   signatures. That means the current low-risk Phase 4 naming/export cleanup is
   effectively complete; the next Phase 4 move is a behavioral extraction
   decision rather than another alias/config/export cleanup. The next Tuesday,
   July 21, 2026 shared-surface slice now also moves one more band of generic
   paper modules onto those neutral imports: shared live-decision runners,
   timeline builders, generated-prelude flow, live-ingress runner,
   TradingEngine capture ingress suite, and generic order/position entry
   helpers now consume the `Paper...` live-decision and ingress-dry-run names
   directly instead of the `S23...` names. The next likely Phase 4 move is
   therefore behavioral extraction inside the remaining truly shared live-
   ingress/live-decision logic rather than more naming churn. The next
   Tuesday, July 21, 2026 broker-bootstrap slice is now also complete:
   `src/tfis/paper/lifecycle_runtime_config.py` now exposes a broker-config-
   level adapter builder, and both the neutral live-ingress runner plus the
   FYERS snapshot collector consume that same helper instead of duplicating
   inline provider checks and fixture/live adapter construction logic. The
   focused affected regression pack passed at `110 passed`, the broader shared
   safety sweep passed at `90 passed`, and local `prod` readiness remained
   `overall_status=PASS`. The same Tuesday, July 21, 2026 bootstrap-hardening
   slice now also centralizes broker-credential readiness: the shared paper
   runtime-config layer owns provider-specific credential-availability checks,
   and both the neutral live-ingress preflight plus the FYERS snapshot
   collector now consume that one helper instead of each probing FYERS
   credentials inline. The focused affected regression pack passed at
   `112 passed`, and local `prod` readiness remained `overall_status=PASS`.
   The same Tuesday, July 21, 2026 shared-ingress wording slice now also
   removes one more public S23/FYERS-only signal from the shared paper path:
   the neutral live-ingress runner now renders generic paper-broker summary
   and preflight headings plus generic configured-broker safety wording. The
   same Tuesday, July 21, 2026 shared reviewer/state-store cutover batch is
   now also clean: generated-prelude dry runs, position discovery, position
   management, the morning timeline runner, execution journal, fill
   simulator, lifecycle simulator, ingress dry-run, and the FYERS snapshot
   collector now consume neutral `Paper...` reviewer/state-store aliases
   where those surfaces are already shared, while preserving compatibility
   symbols for older module-level monkeypatch hooks. The impacted regression
   pack passed at `190 passed`, and local `prod` readiness remained
   `overall_status=PASS`. The next likely Phase 4 move is therefore a true
   behavioral extraction inside the remaining shared live-ingress/live-
   decision flow rather than another bootstrap or naming cleanup.
2. Run the next pre-market operator checklist and supervised paper start
   against the shared supervisor path.
   The local readiness gate now has a dedicated command:
   `.\.venv\Scripts\python.exe scripts\pre_live_readiness.py --profile prod --require-token`.
   The latest local prod-paper run on Friday, July 17, 2026 returned
   `overall_status=PASS`, so the remaining work is operator-time verification
   that the scheduled wrapper (or manual wrapper) starts cleanly, the shared
   supervisor attaches to any produced orders or positions, and the dashboard
   refresh reflects same-day artifacts during market hours.
   The latest Thursday, July 16, 2026 runtime fix specifically addressed the
   case where the S23 morning wrapper encountered a stale process-lock reclaim
   message on stderr and aborted before writing a fresh same-day session.
   That proof point is now complete: the wrapper continues through the reclaim
   path, produces a fresh `2026-07-16` S23 session when no S23 position is
   open, starts fresh S23 order visibility through the shared supervisor path,
   and leaves the July 15, 2026 closed
   S23 trade in historical review rather than the live monitor.
   Before the next session, refresh the Windows scheduled-task registrations
   for both live paper candidates:
   `powershell -ExecutionPolicy Bypass -File scripts/register_s23_fyers_morning_supervised_task.ps1`
   and
   `powershell -ExecutionPolicy Bypass -File scripts/register_s21_fyers_morning_supervised_task.ps1`.
   S23 now defaults the task wrapper to `IfPast=run_now`, which matches the
   Python runner and prevents the erroneous late `09:30 has already passed`
   abort seen on 2026-07-14.
   Recovery now skips prior-session waiting orders during
   `reset_tfis_dashboard_and_watchers.ps1`; the live validation should confirm
   only true carry-forward positions are restored before 09:14, including
   carried states discovered outside the latest session metadata folder, and
   that stale waiting orders are swept or ignored by the shared supervisor
   instead of reappearing as separate watcher windows after reboot/reset.
   The same reset command now starts the local dashboard server with
   `serve_operator_dashboard.py --skip-build` after the explicit rebuild step,
   so the expected operator experience is one visible rebuild followed by the
   dashboard opening on `127.0.0.1:8765` without a second hidden startup build.
   It now also starts one shared supervisor console instead of one watcher
   window per target.
   The remaining operator-time validation is to confirm the next scheduled
   market-open run behaves the same way without manual wrapper intervention.
3. Validate S23 live ORPT/RC timing finalization during the next real market
   session. The supervised live decision path now builds a provisional base
   selection at ORPT, finalizes and places the waiting paper order from that
   ORPT selection when the selected option has not missed entry, and reserves
   RC for the missed-entry recalculation path only. The remaining work is live
   market evidence across CE/PE and near/next-expiry cases.
4. Validate S23 next-day SL reset after a 15:00 carry-forward in a real market
   session. The paper position manager now records overnight SL inactive
   carry-forward when price is not above original SL, keeps target active the
   next day, reactivates the original SL at ORPT when `09:15` high does not
   miss SL, and recalculates revised SL from RC high plus configured
   `sl_reference_pct` when the `09:15` high misses SL. Offline restart-safety
   tests now also prove that carry/resume transitions preserve the SL-reset
   metadata instead of reactivating SL by default. Remaining work is live
   evidence from FYERS quotes/bars and dashboard review of the resulting state.
   If the carried position exits after the morning fresh decision was already
   calculated and blocked, `scripts/promote_s23_blocked_fresh_order.py` is now
   available as a guarded operator path to promote that same-day blocked
   `READY` decision into a waiting paper order. It must only be used after
   confirming no active S23 paper position remains. The follow-up runtime task
   is to automate this handoff inside the watcher/position-manager flow.
5. Validate shared-supervisor current-price visibility and cutoff handling end
   to end.
   The scheduled startup wrapper now hands paper lifecycle supervision to one
   shared TFIS process instead of one watcher per produced order or open
   position. That supervisor scans the durable S21/S23 artifact roots for
   persisted open/carry-forward positions and waiting orders, appends
   selected-contract market events, and marks stale previous-session waiting
   orders or same-session cutoff misses from one shared loop. The remaining
   operational validation is to prove automatic supervisor startup, quote
   updates, fill status, dashboard rebuilds, and cutoff cleanup from live FYERS
   quotes/artifacts during market hours, and to confirm that the FYERS
   option-chain snapshot passes the new true-next-expiry verification instead
   of failing closed with `NEXT_WEEKLY_OPTION_CHAIN_UNAVAILABLE`, without
   changing strategy rules. The supervisor now persists selected-contract
   quote/bar observations to `selected_contract_market_events.jsonl`, and the
   captured-session validator can replay waiting-order fill/not-filled/waiting
   outcomes from that evidence. The validator now also replays persisted
   position threshold outcomes for target, active SL/FSL, and still-open or
   carry-forward states. The remaining validation is to prove that this stream
   is populated continuously during a real market watch. The Active Trades and
   Orders Manager dashboard surfaces now show that stream as event count,
   latest timestamp, age/staleness, watcher PID, source, and Market Events
   artifact link, so the live validation should check those fields alongside
   price and P&L. The
   captured-session validator now also recognizes expiry force-close and
   next-day SL reset replay outcomes from persisted artifacts. Improve
   TFIS-only supervisor observability so an
   operator can see branch, contract, managed directory, and last quote
   timestamp without confusing wrapper/child pairs for multiple independent
   strategy watchers. Offline unit tests now prove the watcher and
   supervised-decision PID-lock identities plus the new shared-supervisor
   launch path; remaining proof is a real Windows restart attempt with live
   process inspection. The manual operator guide now has a
   money-readiness command table for the dashboard, replay validator, focused
   tests, syntax checks, scheduled-task checks, watcher recovery, and pre-live
   readiness checks; use that table as the first human-run test checklist.
   The 2026-07-06 captured-session review gap is fixed: the dashboard and
   validator now include active monthly-status branch calculations even when a
   branch only produced `trade_decision_explainer_stage_*.json` and no final
   `trade_decision_summary.json`. The remaining live validation is evidence,
   not a known calculation-visibility blocker.
5. Validate the first controlled S21 BankNifty monthly paper-mode run.
   S21 is now enabled as an `ACTIVE_CANDIDATE` through
   `config/paper.s21.fyers_connect_test.yaml`,
   `scripts/run_s21_banknifty_0916_supervised_decision.py`, the new
   `scripts/start_s21_fyers_morning_supervised_decision.ps1` wrapper, and the
   new scheduled-task registration/check helpers. The immediate operator work
   is to refresh the S21 daily reference packet, confirm the configured
   monthly expiry and lot size, verify that the dashboard builds a separate S21
   page, and capture one real market-day paper session before broadening
   runtime support.
6. Keep monthly status as an independent service and improve its explanation/provenance output.
   Monthly-status calculation must support selected instrument, selected date, and configured price source. It must produce one of the four business statuses or `UNKNOWN` only for incomplete/error cases, and it must remain reusable by future strategies such as S21.
   S21 now has a BankNifty monthly option-selling runtime candidate, but it
   still needs confirmed BankNifty futures-continuous monthly-status sourcing
   and live evidence before it can be treated as an operationally trusted path.
7. Introduce generic strategy-registry execution for enabled strategies.
   The generic execution-plan contract now exists under
   `tfis.strategy.execution_plan`, and current S23 paper configs declare an
   enabled S23 entry with branch registry IDs and strategy paths. It can skip
   disabled strategies and fail closed for unsupported enabled executors without
   broker imports. Remaining work is wiring the supervised live-paper runner to
   consume this plan directly and call strategy modules through a shared
   interface. S23/FYERS can remain the first operational path, but not as a core
   engine assumption. S21 must wait for this generic path and BankNifty runtime
   policy confirmation before live/paper enablement.
8. Validate the new durable S23 artifact layout through the next scheduled
   market run. The morning supervised workflow, watcher, dashboard source, and
   finalizer now default to
   `data/strategies/S23/fyers_morning_supervised_decision` for option-chain,
   decision, order, position, and ledger/state artifacts, while rebuildable
   dashboard HTML and PowerShell launch logs remain under `tmp`. Remaining
   work is live-run validation and optional historical migration/backfill from
   older `tmp/s23_fyers_morning_supervised_decision` sessions after confirming
   no process is using them.
8. Decide whether TradingEngine option-quote captures can be enriched with reliable selected-contract OI before using them for TFIS ingress-only acceptance.
   The paired suite under `D:/TradingEngineTFIS/tmp/s23_tradingengine_capture_dry_runs` proved that six real captured dates can be converted, paired with TFIS preludes, and fed through the ingress-only runner without touching `D:\TradingData`, but all six sessions still ended `ABORTED` with `missing_contract_oi`. The new audit in `docs/operations/s23_tradingengine_capture_oi_audit.md` makes the blocker explicit: the six audited quote archives have `0` non-blank `oi` rows overall and `0` non-blank `oi` rows in the RC window, while `option_positioning` journal events are only near-spot summaries and not a selected-contract-safe substitute.
9. Replace the current TFIS decision reference packet with fully TFIS-native sourcing for monthly-status and prior-session reference levels.
   `src/tfis/paper/runtime_input_derivation.py` and `scripts/run_s23_fyers_live_decision_check.py` now prove that TFIS can derive `09:15`, `ORPT`, and `RC` checkpoints from normalized morning bars and build a supervised paper decision summary from live FYERS snapshots. The main remaining TFIS decision gap is the reference packet itself: monthly-status levels, `d2/d3/d4` levels, and option aliases such as `OPT_PRV_2DHH` and `OPT_PRV_3DLL` still need a TFIS-native sourcing path rather than a manual packet.
10. Broaden the supervised FYERS live-decision evidence set across more dates and branch shapes before introducing any continuous socket/session orchestration.
   The new supervised path now exists under `src/tfis/paper/runtime_input_derivation.py`, `src/tfis/paper/live_decision.py`, and `scripts/run_s23_fyers_live_decision_check.py`. The next safe step is to prove the same TFIS-native decision summary works cleanly across more market dates, more branch fixtures, and more option-chain shapes while keeping OI validation strict.
11. Broaden the broker-backed S23 ingress-only validation set across multi-date normalized archive and replay sessions before enabling any broker-backed fill or lifecycle rehearsal.
   The broker-agnostic ingress layer still exists under `src/tfis/brokers/` and `src/tfis/paper/live_ingress.py`, with FYERS as the first market-data adapter and explicit order-placement blocking. `D:/TradingEngineTFIS/tmp/s23_live_paper_dry_runs/2026-05-27/s23-ingress-validation-suite-v1` remains the first operator-grade baseline: `5` sessions, `4 PASS`, `1 WARNING`, `0 NO_GO`, `80.0%` pass rate, `100.0%` selected-contract availability, and a `LIMITED_GO` recommendation.
12. If the broader supervised decision and ingress suites stay within the close-out thresholds, run the first tightly controlled live-like S23 paper fill and same-day lifecycle rehearsal under operator sign-off.
   The operator policy now exists in `docs/operations/s23_operator_closeout_policy.md`, and the new broker-backed ingress design now exists in `docs/operations/s23_fyers_paper_ingress_design.md`. The next rehearsal should happen only after broader multi-date decision and ingress suites still preserve `0` NO_GO sessions and keep warning cases bounded and reviewed.
13. Continue extracting generic paper lifecycle pieces after S23 market
   validation. S23 and similar option-selling strategies are carry-forward
   capable before expiry. The paper runtime now has multi-day foundation
   pieces, visible watcher windows, expiry force-close governance,

## Weekend Live-Money-Readiness Checklist

Use this checklist as the active execution order for Saturday, July 18, 2026
and Sunday, July 19, 2026. Mark items complete only after code, focused tests,
and operator-facing verification all pass.

1. `DONE` Establish the guarded readiness track in docs.
   Acceptance gate:
   the contract conflict is called out clearly, the execution order is
   documented, and the current-state snapshot points to this checklist as the
   controlling queue.
2. `DONE` Audit and close remaining paper lifecycle correctness gaps.
   Scope:
   waiting-order aging rules, carry-forward recovery rules, close-to-history
   promotion, fresh-calculation handoff, stale current-price states, duplicate
   supervision, and dashboard trade classification.
   Latest slice:
   closed-trade rows are now historical-only by default in live monitors, the
   shared supervisor can trigger fresh supervised decisions from
   `PAPER_POSITION_FRESH_ENTRY_REQUIRED`, and that relaunch path is now
   idempotent per terminal session directory via a durable launch marker. The
   same shared supervisor path now also prefers promoting an already-
   calculated blocked same-day READY decision before it falls back to spawning
   a brand-new supervised run. Live rows also no longer show a concrete
   current price without selected-contract stream evidence, and stale live
   quotes are now labeled explicitly.
   Acceptance gate:
   same-day and next-day paper artifacts render one consistent story across
   strategy pages, all-trades monitor, and historical-trades page.
3. `DONE` Harden shared supervisor startup, stop, reset, and reboot recovery.
   Scope:
   slow reset paths, duplicate child windows/processes, scheduled-task restart
   semantics, and deterministic supervisor visibility after reboot or manual
   reset.
   Latest slice:
   TFIS now has one explicit operator stop command in
   `scripts\stop_tfis_runtime.ps1`, and the runtime-process detection/stop
   rules used by dashboard reset now live in one shared PowerShell helper so
   reset and manual stop use the same TFIS-only process ownership rules.
   Acceptance gate:
   one documented operator path starts TFIS cleanly, one documented operator
   path stops TFIS cleanly, and restart behavior is repeatable.
4. `DONE` Harden broker/data ingress failure handling for live-readiness.
   Scope:
   adapter bootstrap errors, token/preflight failures, missing quote evidence,
   stale stream detection, missing bar fallback policy, and fail-closed
   behavior when market data is not trustworthy.
   Latest slice:
   the shared broker-runtime connect helper now actually honors its reconnect
   and fail-closed path after the first health probe, and the shared paper
   lifecycle supervisor now re-checks broker runtime health before managing
   active targets, emitting explicit degraded/recovered logs with
   strategy/provider context instead of trusting startup health indefinitely.
   TFIS now also has one explicit opt-in broker-health probe surface:
   `scripts/pre_live_readiness.py --probe-broker-health` can actively connect
   each configured paper broker adapter and fail closed if health never
   reaches `CONNECTED`, while `scripts/show_tfis_runtime_status.ps1` can print
   the same shared probe status from its read-only operator console.
   The target loop now also fails closed when selected-contract market-event
   fetch fails for a managed order/position: it logs a contextual
   `market_data_unavailable` warning with strategy/provider/trade/contract,
   publishes a `MARKET_DATA_UNAVAILABLE` watch heartbeat, and skips lifecycle
   state transitions for that target iteration. Focused supervisor-runtime
   validation for this slice passed at `44 passed`; the broader supervisor/
   market-event/dashboard/readiness/broker-boundary pack passed at
   `101 passed`, and project validation passed.
   The heartbeat read-model now also treats a fresh
   `MARKET_DATA_UNAVAILABLE` heartbeat as `DEGRADED` instead of `OK`, carries
   the latest runtime status/reason code into the operator console, and makes
   the dashboard Operator Status panel alert on degraded market-data heartbeat
   evidence. Focused heartbeat/dashboard/runtime validation passed at
   `87 passed`.
   Readiness now includes a `paper_runtime_heartbeat` check too: degraded or
   unavailable runtime heartbeat evidence fails pre-live readiness, while
   stale prior-run heartbeat files remain visible but acceptable before
   startup. The actual prod readiness command on Wednesday, July 22, 2026
   returned `overall_status=PASS` with stale S21/S23 heartbeat evidence
   surfaced, focused readiness/runtime/dashboard validation passed at
   `91 passed`, and project validation passed.
   Acceptance gate:
   readiness and runtime paths both surface provider health explicitly and do
   not silently continue into ambiguous trade-management states.
   Design constraint:
   `D:\TradingEngineProd` may be consulted as read-only reference for proven
   socket/live-market patterns, but TFIS must not copy in unrelated code or
   modify that repository. Any reused idea must be re-expressed through TFIS
   broker-neutral interfaces with FYERS as the default configured provider,
   not as a hardcoded engine assumption.
5. `IN PROGRESS` Harden trade-state reconciliation and ledger authority.
   Scope:
   active-vs-historical classification, waiting/open/closed/carry-forward
   identity, re-entry after close, and supervisor-owned transition rules.
   Current status as of Monday, July 20, 2026:
   shared trade-ledger helpers now own latest active-row selection and latest
   historical-close selection, and the dashboard consumes those shared rules
   instead of maintaining its own duplicate per-page latest-row logic. The
   same shared-state pass now also makes waiting-order recovery explicit:
   only same-day waiting orders are watchable supervisor targets, while
   prior-session waiting orders remain review artifacts rather than live
   supervision candidates.
   Blocked fresh-entry promotion now also uses the shared position-discovery
   layer for its "positions still block new entry" gate instead of carrying a
   separate filesystem scan and predicate.
   Fresh-entry-required handoff now also runs through one shared paper helper
   that owns idempotent launch-marker behavior and promotion-first handoff
   rules, instead of keeping that decision tree in the supervisor script.
   The fresh-decision relaunch task builder now also consumes per-strategy
   runner/wrapper script metadata directly from the shared supervisor-target
   config, so the supervisor no longer keeps a hardcoded S21/S23 script map,
   and the strategy execution-plan surface now normalizes the legacy
   `s23_morning_supervised` executor label onto the generic
   `paper_morning_supervised` name while preserving compatibility with current
   configs.
   Live-trade monitor order visibility now also comes from a shared
   paper-order helper keyed by latest-session date instead of a dashboard-only
   inline filter, so the current-session boundary for waiting/not-filled paper
   orders is now owned by the same reusable order-state layer that already
   defines watchability and monitor-visible order statuses.
   The shared paper-order layer now also owns reusable order-state discovery,
   and both lifecycle-supervisor target discovery plus waiting-order
   finalization now consume that same scan path instead of each walking
   `paper_order_state.json` artifacts separately.
   The post-cutoff finalizer has now moved from an S23-only operating
   assumption to a TFIS target-config sweep while retaining the existing
   compatibility script names. The scheduled task on the host is now
   `TFIS Paper Order Finalizer` at `15:35`, the old
   `TFIS S23 Paper Order Finalizer` task is disabled, and the wrapper passes
   `config/paper_lifecycle_supervisor_targets.yaml` so S21/S23 and later
   enabled paper targets are finalized by the same application safety net.
   By default the scheduled wrapper includes prior sessions so stale waiting
   orders become terminal review artifacts instead of remaining active
   forever; live supervision still watches only same-day waiting orders.
   Focused validation passed at `19 passed`, the broader startup/runtime/
   boundary pack passed at `101 passed`, project validation passed, and a
   real-artifact dry-run for `2026-07-22` scanned `32` order states across
   the configured roots and would finalize `2` stale prior-session S21 waiting
   orders without mutating state.
   Shared position discovery now also owns the dashboard's stale-carry-forward
   override lookup through a lenient latest-terminal-position helper, so the
   strategy pages no longer keep a separate raw `paper_position_state.json`
   scan just to suppress stale carry-forward blockers after a terminal close.
   Blocked READY fresh-entry promotion now also works from shared promotion
   candidate records that carry parsed summary data plus any already-
   discovered order-state path for the branch, rather than passing raw
   summary-path tuples through the promotion loop.
   The blocked-decision promotion path now also projects eligible decision
   payloads into the strategy-neutral `PaperOrderDecisionIntent` contract
   before creating a waiting paper order. The order-state store still accepts
   existing S23 decision objects for compatibility, but its persistence logic
   now validates and stores from the neutral intent shape rather than requiring
   an `S23PaperTradeDecisionSummary`. Focused promotion/supervisor validation
   for this slice passed at `55 passed`; the broader finalizer/promotion/
   supervisor/dashboard/readiness/broker-boundary pack passed at `118 passed`,
   and project validation passed.
   The runtime side of that truth model has now tightened further too:
   pre-live readiness audits each persisted paper position state against the
   latest ledger row for the same trade and fails closed when active state,
   terminal state, or missing ledger backing disagree with the durable trade
   record. The read-only operator runtime-status command now also exposes a
   dedicated `RuntimeReconciliation` section sourced from that same helper, so
   reconciliation failures are visible during market hours without a restart.
   The same Tuesday, July 21, 2026 runtime surface now also has one shared
   fresh-entry handoff audit: readiness, the runtime-status command, and the
   dashboard Operator Status panel all consume the same helper, which accepts
   launch markers, later same-branch lifecycle rows, or later same-branch
   supervised-session artifacts as valid evidence that a fresh-entry-required
   close was handed off correctly.
   The shared live-monitor trade-row helper now also keeps prior-session
   `ORDER_NOT_FILLED` rows historical-only, closing one more active-vs-
   historical leak when a strategy has not produced a current-day session yet.
   The dashboard can now also read fresh-decision launch markers and tell the
   operator whether a fresh-entry-required close promoted an existing blocked
   READY decision or launched a new supervised runner. The remaining work is
   now narrower than basic visibility: keep shrinking the last places where
   old close/promotion artifacts can still leave confusing active-versus-
   historical evidence behind.
   The remaining work in this step is to continue lifting the last S23-shaped
   runtime/promotion adapters behind neutral contracts while preserving the
   proven S23 compatibility surface.
   Acceptance gate:
   every lifecycle state has one durable source of truth, and dashboard views
   agree with it.
6. `TODO` Add explicit live-mode guardrails and operator controls.
   Scope:
   dry-run/live configuration boundaries, manual stop/pause/recovery guidance,
   kill-switch expectations, live-order preconditions, and audit/event
   visibility.
   Latest slice:
   TFIS now has filesystem-backed global and per-strategy paper-runtime pause
   controls through `scripts/pause_tfis_runtime.ps1`,
   `scripts/resume_tfis_runtime.ps1`, and shared supervisor pause-state
   detection. The dashboard now also surfaces pause scope, paused strategies,
   stale/no-stream counts, alert text, the latest operator-control event, and
   the primary pause/resume/refresh commands in one shared Operator Status
   panel. Operator pause/resume commands now also append one shared
   `operator_control_events.jsonl` audit trail under `tmp/operator_controls`.
   TFIS also now has a read-only `scripts/show_tfis_runtime_status.ps1`
   command so operators can inspect shared-process, pause-state, and latest
   control-event truth without restarting runtime.
   Pre-live readiness now also fails closed when a lingering TFIS
   global/strategy pause marker would block supervision for the day.
   The shared lifecycle runtime now also validates one broker-neutral paper
   guardrail contract before supervisor bootstrap: paper configs must stay on
   a paper-ingress source mode with paper mode enabled, no live orders
   allowed, kill switch enabled, and session kill switch inactive.
   The dashboard now consumes that same shared guardrail helper too, so
   Operator Status surfaces a paper-guardrail PASS/FAIL badge and explicit
   alerts instead of leaving that truth hidden inside readiness/bootstrap
   checks only. The dashboard now also consumes filesystem-backed supervisor
   heartbeat truth from the shared live-state backend, so Operator Status can
   flag stale or unavailable supervision separately from selected-contract
   stream staleness. The same operator/runtime surface now also exposes a
   separate shared order-routing safety status: pre-live readiness,
   `scripts/show_tfis_runtime_status.ps1`, and the dashboard Operator Status
   panel all confirm that paper targets still keep
   `no_live_orders_allowed=true` and broker adapters still inherit the
   blocked paper-only `place_order` / `modify_order` / `cancel_order` paths.
   The heartbeat read-model now also exposes the latest persisted
   `owner_id` and `state_directory`, and the shared live-state loader accepts
   both nested `storage.live_state` / `storage.redis` config and top-level
   `live_state` / `redis` aliases, so runtime status reads and live-state
   bootstrap no longer depend on different YAML shapes.
   The shared dashboard Operator Status panel now also shows that latest
   heartbeat owner/state-directory detail directly, so operators can trace a
   stale or fresh heartbeat back to the shared supervisor identity and watched
   state directory without leaving the dashboard.
   The remaining work is to define any future live-mode-only routing controls
   separately from this paper-only safety audit and fold those controls into
   the broader live-mode audit truth.
   Acceptance gate:
   the system can fail closed safely, and an operator can understand what to
   do during partial failure without code inspection.
7. `TODO` Redesign the operator dashboard for multi-strategy operational use.
   Scope:
   strategy navigation that scales beyond S21/S23, a stable top-level operator
   home, clear entry points for live monitor, historical trades, strategy
   pages, and charts, plus operator-friendly labels and layout that stay easy
   to scan as more strategies and instruments are added.
   Latest slice:
   the dashboard now has a shared Operator Status panel on the index,
   strategy pages, and all-trades monitor for pause scope plus stream-health
   alerts. The dashboard now also has one shared operator nav strip across the
   home, strategy, all-trades, historical-trades, monthly-status, and manual
   S23 pages, so the primary operator workflows no longer depend on page-local
   back links or tool-only link clusters. A first shared chart-review page now
   also exists under `tools/charts/index.html`, surfacing active selected-
   contract market-evidence charts and a direct entry into the monthly-status
   structure chart. The remaining dashboard work is denser operator-time
   summaries, broader chart coverage, and scaling the same navigation model as
   more strategies and instruments are added. The operator home cards now also
   show per-strategy visible-trade, open-position, action-required, and
   closed-row counts from the shared live monitor, so the next dashboard work
   is less about basic summary density and more about broader chart coverage
   plus long-horizon multi-strategy scaling.
   Acceptance gate:
   an operator can move between strategies, all trades, historical review, and
   chart review without hunting through page-local links or strategy-specific
   assumptions.
8. `TODO` Add chart-review capability for selected scrips and core indices.
   Scope:
   operator-selectable chart views for a chosen tradeable scrip and NIFTY at
   minimum, designed through the same broker-agnostic market-data boundary so
   future brokers can supply the same review surface.
   Latest slice:
   the shared dashboard now exposes `tools/charts/index.html`, which renders
   persisted selected-contract market-evidence charts for active rows and
   links directly into the monthly-status chart surface for NIFTY/BANKNIFTY
   structure review. That page now also includes simple strategy/stream
   filters plus visible/evidence summary counts so the surface remains usable
   as more active rows appear, and the monthly-status tool now accepts simple
   query-string defaults so the chart page can open directly into NIFTY or
   BANKNIFTY review. The chart page now also has an instrument filter over the
   active selected-contract cards, so the remaining chart work is richer index
   review and additional cross-strategy chart summaries rather than basic
   chart narrowing.
   Acceptance gate:
   the dashboard exposes a clear charts section with navigable chart views and
   no FYERS-only assumptions leaking into the operator workflow.
9. `TODO` Run the final weekend validation pack.
   Scope:
   focused unit/integration regressions, readiness audit, dashboard rebuild,
   supervisor startup/recovery checks, and selected artifact replay or captured
   session validation where relevant.
   Acceptance gate:
   all required checks pass, documents are updated, and remaining risk is
   stated explicitly rather than implied away.
   Operator note:
   use `scripts/refresh_tfis_operator_dashboard.ps1` for in-market dashboard
   rebuilds and reserve `scripts/reset_tfis_dashboard_and_watchers.ps1` for
   full TFIS runtime restart/recovery only.
   session-only waiting-order behavior, and next-day SL reset. The next
   architecture step is to lift shared lifecycle concepts into strategy-neutral
   services only after the S23 behavior is proven in live paper operation.
14. Persist explicit final no-trade summaries for every evaluated S23 leg.
   The dashboard and validator can now reconstruct no-contract legs from the
   latest stage explainer, but the cleaner long-term artifact contract is for
   the runner to write an explicit final no-trade summary for each evaluated
   active leg, including failure code, attempted expiries, threshold inputs,
   and provisional formula audit values.
15. Broader real/archive contract-specific intraday coverage for S23.
   The deterministic fixture set is fully covered at 100.0%; the next safe step is to widen real session coverage while keeping TFIS runtime on the existing contract-intraday CSV contract.
16. If an OI-enrichment source is found, rerun the TradingEngine capture ingress suite before attempting any fill or lifecycle replay from captures.
   `scripts/run_s23_tradingengine_capture_ingress_suite.py` now proves that the raw capture path itself is operationally read-only and deterministic. The blocker is not prelude pairing, timing, or selected-contract identity alone; it is the absence of usable selected-contract `oi` in the option-quote archives at decision time.
17. Validate the TFIS-only reboot recovery path after a real operator rerun.
   `scripts/reset_tfis_dashboard_and_watchers.ps1` now waits for prior TFIS
   runtime processes to exit and skips starting an already-matching dashboard
   server or watcher target, but the remaining proof is a live Windows rerun
   after reboot or delayed dashboard startup to confirm one dashboard server
   and one watcher per persisted order/position target.

Comparison reporting note:

- the bounded S23 comparison tool is now in place for the current historical modes
- the comparison layer now records input-dataset paths, cost settings, and apples-to-apples status
- the normalized lifecycle-source runbook now compares a matched option-chain baseline against contract-specific lifecycle mode, so lifecycle-source P&L differences can be reviewed without cost or spot-input drift
- future comparison work should extend reporting depth without regressing the new file-size, trade-count, timeout, and integrity safeguards
- the row-183 `current_day_fsl_trp` loss flip seen in an older comparison was not reproduced after rerunning all six modes on one shared dataset set and one shared cost model
- the new S23 paper-vs-historical comparator now reuses the historical normalized trade summaries and compares persisted S23 paper sessions through planning, arming, dispatch, handoff, fill, and same-day lifecycle outcome with deterministic `MATCH`, `MATCH_WITH_ACCEPTABLE_DRIFT`, `PARTIAL_MATCH`, `MISMATCH`, or `UNCOMPARABLE` statuses
- the new S23 operator close-out policy now classifies ingress-only sessions as `PASS`, `WARNING`, or `NO_GO`, with `LIMITED_GO` or `GO_FOR_CONTROLLED_PAPER` reserved for aggregate suite interpretation rather than individual-session state

## Blocked / Pending Clarification

- S21 BankNifty monthly option-selling is now runnable in controlled paper mode
  as an `ACTIVE_CANDIDATE`, but it is not yet operationally trusted. Confirm
  active BankNifty lot size, strike step, near/next monthly-expiry selection,
  futures-continuous monthly-status source, ORPT/RC timing applicability,
  carry-forward behavior, forced close, and whether `minimum_oi` should be
  derived automatically from `minimum_lots * lot_size`. The current reference
  packet is a placeholder and must be refreshed before tomorrow's test.
- no workbook-backed recalculated target formulas were found in `AB6 OS` rows `162-191`; any target override work remains blocked until new workbook evidence appears
- `AB6 OS!Z183:Z186` are now implemented as workbook-backed current-day option-entry overrides for the supported `183-186` rows
- `AB6 OS!190:191` still describe 15:00 position-open process flow only in the
  older workbook, and `docs/importers/s23_position_open_1500_audit.md` found no
  linked numeric continuation-stoploss formulas there. The newer S23
  gap-up/gap-down text file now defines the 15:00 original-SL comparison rule
  implemented in paper position management.
- a deterministic applied-case fixture now exists for current-day FSL / TRP (`tests/fixtures/backtest/s23_current_day_applied/`), so future row-183 or row-185 timing investigations should start from that same apples-to-apples dataset before using any synthetic scenario variants
- if we later want to study whether current-day FSL / TRP can change lifecycle exits under broader market conditions, the next data need is wider non-synthetic intraday coverage rather than new workbook mapping assumptions
- current-day S23 FSL / TRP unsupported paths remain intentionally unchanged until the workbook confirms additional rows:
  - Bull / Bull CF Put not missed
  - Bear / Bear CF Call not missed
- the new S23 live-paper data contract and session state machine now have matching schema scaffolding, required-field validation, an in-memory orchestrator, pre-planning kill-switch and failure-handling guardrails, persisted terminal planning artifacts, replay-bundle manifests, operator-facing review summaries, an execution-journal intent shell, post-planning intent guardrails, planning-state paper-vs-historical replay comparison, later-phase execution-shell arming controls, a fillless dispatch-only shell, a final no-fill handoff boundary, execution-shell-aware parity summaries under `src/tfis/paper`, a documented MVP v1 fill-simulator design, Phase 1 fill or no-fill simulation, Phase 2 same-day lifecycle simulation with paper exit and P&L artifacts, visible watcher-window paper monitoring, expiry governance, session-only waiting-order cancellation, and a broker-agnostic live-paper ingress foundation with FYERS as the first market-data adapter; broker order placement remains blocked and multi-session carry-forward behavior still needs clean market-day validation before operational reliance
- fuller strike-availability realism still needs wider symbol/date coverage than the current fixture-backed contract-specific lifecycle foundation; the fixture gap is closed, but broader archive depth beyond the current S23 symbol/date set is still pending
- raw shared capture ingestion still needs broader normalization contracts for parquet/jsonl/session artifacts before TFIS should parse them directly at scale; the new TradingEngine capture adapter prototype is intentionally limited to one-session market-event conversion
- TradingEngine capture plus TFIS prelude ingress-only dry runs are now implemented and validated, but the first six real-date suite runs all ended `ABORTED` with `missing_contract_oi`; the new OI audit confirms this is a real source-data gap rather than a runner defect, so this path remains `NO_GO` for operational ingress acceptance and should be treated as market-data-leg timing validation only
- Re-run `scripts/reset_tfis_dashboard_and_watchers.ps1 -MorningStartup` from
  the normal operator PowerShell session with outbound FYERS access. The script
  now gets past the embedded Python quoting defect; this validation should
  prove token reuse or token refresh, dashboard serving, strategy wrapper
  startup, and shared supervisor startup in one pass.
- During the next market-hours validation, confirm that both configured morning
  wrappers produce usable FYERS quote snapshots. After-hours runs may still
  fail each wrapper with `BROKER_SNAPSHOT_FAILED`; that now reports as a
  per-strategy startup failure while dashboard/supervisor startup is still
  attempted.
- Phase 1 generic runtime contracts and the isolated Phase 2A policy engine are
  now in place. Before adding more strategies, keep Phase 2B focused on
  behavior-preserving S21/S23 policy adapters, external composition, and
  shadow/offline parity evidence.
- Certification corrections are in place through strict, future-facing adapter
  APIs and contract-only lifecycle models. The four S23 start-strike
  expectations remain pre-existing and workbook-verification pending; do not
  alter them during Phase 2B adapter extraction.
- Phase 2D captured shadow parity is implemented as an offline-only pipeline,
  but it is conditionally accepted rather than ready for runtime shadow mode.
  The next evidence priority is full S23 captured decision packets with raw
  market-structure references, option reference values, ORPT/RC timing outcome,
  option-chain snapshot, selected-contract quote, target, MSL, and final legacy
  decision in the same saved case. Do not activate runtime dual execution until
  those reports show full captured parity.
- Phase 2D.1 packet contract is accepted for offline use. The next task should
  be a reviewed, disabled-by-default post-market capture design for the
  reference implementation that can emit complete decision packets without
  changing legacy decision behavior. Do not wire packet production into active
  paper/live runtime before that design is reviewed and a full captured S23
  packet passes offline parity.
- Phase 3A strategy identity/configuration foundation is accepted for offline
  domain/config use. Phase 3B should design disabled runtime resolution and
  state-key adoption using `strategy_instance_id + trading_date +
  position_cycle_id`, without migrating active execution or changing formulas.

## Deferred

- futures rollover module for future-based strategy families
- full captured S23 parity evidence with formula inputs; current Phase 2D
  reports have 0 full captured cases and 2 partial captured cases
- post-market reference capture implementation for complete decision evidence
  packets, disabled by default and reviewed before any runtime use
- disabled runtime strategy-resolution design using Phase 3A identities before
  active paper/live paths require resolved configuration
- S21 captured decision evidence before any S21 shadow-readiness claim
- monthly option buying
- broader S21 BankNifty monthly runtime hardening beyond the current controlled
  paper-mode candidate
- BankNifty weekly live support
- multi-broker live runtime beyond the current market-data-only FYERS adapter

## Important Reading Before Any Change

- [project_rulebook.md](project_rulebook.md)
- [current_state.md](current_state.md)
- [next_steps.md](next_steps.md)
- [s23_live_paper_data_contract.md](s23_live_paper_data_contract.md)
- [s23_paper_session_state_machine.md](s23_paper_session_state_machine.md)
- [excel_ambiguity_audit.md](../importers/excel_ambiguity_audit.md)

## Operational Update Discipline

- after every meaningful task, review whether `current_state.md`,
  `next_steps.md`, and `milestones.md` need updates
- if priorities did not change, say so explicitly in the task close-out
- keep this file focused on sequencing and blockers rather than repeating all
  implementation detail

## Current Architectural Principle

`Evidence before behavior.`

## Phase 3E Completion And Phase 4A Next Step

- Phase 3E architecture is `COMPLETE`.
- Version 1 architecture is `CERTIFIED_FOR_IMPLEMENTATION`.
- First paper critical path is `DEFINED`.
- First-10 slate is `PROVISIONAL`, not full implementation approval.
- Broker, paper, live, order mutation, and position mutation authority remain
  `NONE`.

Next implementation task:

1. Phase 4A: connect the accepted M15 runtime coordinator to one existing
   captured/replay stream in shadow-only mode.
2. Prove deterministic fresh-entry and carried-position event flow with no
   broker, paper, live, order mutation, or position mutation authority.
3. Keep later source extraction for S23 Put, S21, Futures, Option Buying and
   stock/equity candidates parallel-safe but separate from the Phase 4A
   critical path.

Phase 4A Milestone 1 result:

- `PARTIAL_CAPTURED_SHADOW_CASE` was produced from the M7 `2026-06-05` S23
  Call-side packet.
- Replay determinism, checkpoint replay, multi-instance sharing and
  conflation stability are proven in shadow mode.
- Phase 4B can proceed on the broker-neutral read-only account/order/position
  boundary; the remaining capture gaps block paper authority, not the P4B
  architecture/contract work.

Phase 4B Milestone 1 result:

- broker-neutral read contracts and snapshots now exist for account/session,
  funds, margins, orders, order-history events, fills, positions, instruments,
  capabilities and aggregate account snapshots
- the concrete FYERS-shaped proof is fixture/captured-payload only; unit tests
  make no live broker calls
- reports under `reports/phase4b` show a complete redacted fixture account
  snapshot and explicit reconciliation gaps
- next priority is Phase 4C: consume the read snapshot in an offline
  reconciliation-ready persistence/reporting layer without adding broker,
  paper, live, order mutation or position mutation authority

Phase 4C Milestone 1 result:

- SQLite-backed transactional operational persistence now exists for offline
  and shadow use only
- deterministic migrations, immutable artifacts, broker observations,
  append-only events, projection versions, idempotency reservations, runtime
  checkpoints, recovery assessment, integrity scan and observational
  comparison are implemented and tested
- execution-intent, local client order, fill, position-cycle and lifecycle
  requirement persistence boundaries are schema-only/offline-only; they do not
  authorize submission or mutate PositionCycles from broker observations
- next priority is Phase 4D: build the broker/local reconciliation engine on
  top of persisted broker observations and local expected-state fixtures, still
  without broker-write authority

Phase 4D Milestone 1 result:

- broker-neutral reconciliation now compares local expected state against
  broker observed state without collapsing either truth category
- account, order, fill, position, protection, carried-position, startup and
  restart readiness classifications are implemented with immutable evidence,
  non-authoritative repair recommendations and advisory authority gates
- reconciliation results persist transactionally through the Phase 4C
  unit-of-work and remain idempotent; broker observations and local projections
  are not automatically repaired or mutated
- next priority is Phase 4E: build the `ExecutionIntent` and minimum risk
  validation boundary using Phase 4D readiness output, without order submission

Phase 4E Milestone 1 result:

- immutable broker-neutral `ExecutionIntent` exists for the first S23
  Call-side vertical purposes: `ENTRY`, `TARGET`, `ORIGINAL_SL`, `REVISED_SL`,
  `EOD_EXIT`, `RISK_EXIT`, and `OPERATOR_EXIT`
- minimum risk validation now consumes recovery and reconciliation readiness,
  enforces account/strategy/portfolio/quantity/price/timing/data-quality/
  idempotency/protection gates, and fails closed with check-level evidence
- validation results and reservations persist transactionally and remain
  explicitly `VALIDATED_NOT_SUBMITTABLE`; no `ClientOrder`, `BrokerOrder`,
  broker write, paper write or position mutation path is enabled
- next priority is Phase 4F: AccountCoordinator plus internal deterministic
  paper adapter, converting validated non-submittable intents into internal
  simulation requests only after explicit approval

Phase 4F Milestone 1 result:

- AccountCoordinator identity, internal-paper authority grant, ClientOrder,
  deterministic internal-paper adapter, order events, simulated fills,
  recovery/consistency checks and persistence records are implemented for
  internal paper simulation only
- S23 first-slice scenarios cover ENTRY, TARGET, ORIGINAL_SL, REVISED_SL,
  EOD_EXIT, partial/full fills, rejection, cancel/replace, duplicate replay and
  multi-account isolation without recalculating strategy formulas
- full-suite failures from the previous run are classified in
  `reports/phase4f/phase4f_full_suite_failure_classification.json`; two
  broker/ingress-adjacent failures remain `UNKNOWN_REQUIRES_REVIEW` before any
  external paper/broker authority, but they do not block internal deterministic
  simulation
- next priority is Phase 4H: integrate simulated fills into PositionCycle,
  because Phase 4F order behavior is sufficient for the first vertical and
  still grants no broker/live/position mutation authority

Phase 4H Milestone 1 result:

- authoritative internal-paper PositionCycle state now consumes confirmed
  deterministic `InternalPaperFill` facts from Phase 4F and owns only
  internal-paper position quantity, averages, lifecycle requirements,
  protection links/generations, exits, carry-forward, recovery, consistency,
  and P&L input facts
- S23 first Call-side scenarios cover full entry, partial entry and protection
  resize, target close, original-SL close, revised-SL replacement/fill, old-SL
  cancel/replace race evidence, EOD exit, EOD unfilled, equality carry-forward,
  next-day recovery, and multi-account isolation
- the two previously unknown full-suite failures were reviewed as legacy
  FYERS ingress/adapter blockers only; they do not import or mutate the new
  internal PositionCycle path and cannot corrupt internal-paper fill/order
  identity
- next priority is Phase 4I: project TradeFact/PnLFact from the completed
  internal-paper vertical; do not start broker/paper/live authority work from
  Phase 4H

Phase 4I Milestone 1 result:

- immutable `TradeFact` and `PnLFact` records now derive from confirmed
  internal-paper operational facts only; planned prices and acknowledgements do
  not affect P&L
- S23 short-option realized and unrealized P&L is implemented for the first
  Call-side internal-paper vertical with explicit Phase 4H confirmed-unit
  semantics, no lot-size double multiplication, conservative short-side ask
  marking, LTP fallback quality, stale-mark UNKNOWN behavior, estimated
  charges, correction/supersession, and read-only projections
- reports under `reports/phase4i` cover trade/PnL contracts, quality and metric
  catalogs, scenario outputs, daily/account/strategy/instrument/exit/path
  projections, complete traceability, rebuild equivalence, performance, and
  remaining accounting gaps
- next priority is Phase 5A-Pre complete internal-paper end-to-end
  certification; do not add broker/live authority before that certification

Phase 5A-Pre result:

- the first S23 Call-side internal-paper vertical is now certified end to end
  through an explicit runner under `src/tfis/internal_paper/end_to_end`, with
  Phase 5A-Pre S23 reporting composition under `src/tfis/adapters/phase5a_pre`
- certified scenarios cover Bull Target, Bear Original SL, gap/RC revised SL,
  partial fill, EOD exit, carry/next-day recovery, crash after ClientOrder,
  crash after partial fill, crash with protected position, duplicate replay,
  blocked reconciliation, multi-account isolation and kill-switch behavior
- reports under `reports/phase5a_pre` include the certification contract,
  scenario matrix, scenario results, complete trace, idempotency catalog,
  scorecard, performance, known failure register and gap register
- exact next recommendation is controlled one-instance internal-paper
  activation only; do not enable external broker, broker-sandbox or live write
  authority from this certification

Phase 5A Milestone 1 result:

- the `internal_paper_s23_single_instance` runtime profile is now available but
  disabled by default, with explicit operator activation required through the
  runtime API or `scripts/run_s23_internal_paper.py --enable-internal-paper`
- the controlled runtime supports preview, enabled Bull/Bear/RC/partial/EOD/
  carry sessions, blocked reconciliation, expired grant, restart/resume,
  duplicate replay, disable-new-entry protection preservation, account/global
  halt, graceful/failure-safe shutdown evidence, read-only operational
  snapshots and immutable session audit output
- reports under `reports/phase5a` document the runtime profile, activation
  contract, session results, operational snapshot, session audit, performance,
  known limitations and gap register
- exact next recommendation is repeated internal-paper observation across
  multiple captured sessions; do not recommend or enable external live
  authority from Phase 5A

Phase 5D S21 first-branch result:

- one source-closed S21 `BULL_CALL` BANKNIFTY monthly option-selling branch now
  runs through the existing generic offline/internal-paper platform without
  generic runtime changes
- reports under `reports/s21_implementation` document branch selection,
  policy composition, contract selection, premarket plan, normal Target,
  Original SL, ORPT/RC revised SL, no-contract, EOD, carry/recovery,
  accounting facts, complete trace, S23 regression guard, reuse gate and
  remaining gap register
- S21 quantity is represented as 1 configured lot and 15 exchange units using
  workbook-era BANKNIFTY metadata; APS remains not applicable for S21
- exact next recommendation is S21 reviewer acceptance of the first branch,
  then implement the remaining three S21 branches by policy/config evidence
  only; do not change generic runtime unless a reusable platform defect is
  proven

Phase 5D S21 complete-strategy result:

- all four source-verified S21 BANKNIFTY monthly option-selling branches now
  run through the existing generic offline/internal-paper platform:
  `BULL_CALL`, `BULL_PUT`, `BEAR_CALL`, and `BEAR_PUT`
- natural branch resolution is certified from generic Monthly Status, S21
  branch mapping, and branch-specific market/contract evidence; the runner does
  not accept manual Call/Put override after resolution
- reports under `reports/s21_complete` document branch inventory, contract
  selection, normal paths, ORPT/RC paths, Target, Original SL, revised SL,
  EOD/carry, carried recovery, accounting, S23 regression guard, platform reuse
  audit, validation summary and complete trace
- the generic short-option accounting version label is corrected to
  `tfis.short_option_accounting.v1`; this is a provenance correction only and
  does not change P&L formula, quantity, multiplier, charge or projection
  behavior
- exact next recommendation is begin S22 source closure and stock-universe
  audit; do not begin S22 implementation until source closure is accepted

Unified continuous-supervisor next step:

- run one complete unified S21/S22/S23 internal-paper session from before
  market open using `scripts/run_tfis_internal_paper.py --preflight-complete-session`
  followed by the continuous-supervisor operator start command
- use that single session to certify pre-market planning, market-open
  observation, ORPT/RC timing, steady-state supervisor cadence, EOD/carry
  handling, checkpoint continuity, dashboard freshness, and operator shutdown
- keep August 3, 2026 classified as a late-start observation/lifecycle-only
  day; do not create retroactive fresh internal-paper entries from a missed
  start
- keep FYERS strictly read-only and do not broaden to external paper or live
  authority from this milestone

Unified runtime performance gate:

- use `reports/runtime_performance/` as the evidence pack for cadence
  certification
- treat the August 3 live process as `BLOCKED_BY_RUNTIME_CADENCE` for
  acceptance because passive publish gaps were far above the `5s` configured
  interval
- the next approval gate is one real before-market-open run on the updated
  optimized supervisor path; do not claim readiness from fixture-only timing
  or passive code inspection alone
