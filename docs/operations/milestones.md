# Milestones

## Current Snapshot

- offline TFIS architecture and backtest foundation is in place
- strategy and workbook normalization work is established for the S23 family
- reference materials are now indexed and reviewable through archive metadata
- deterministic monthly-status classification is implemented for the confirmed threshold rules
- optional monthly-status-driven branch selection is available in historical backtests
- opt-in S23 missed-entry detection and recalculation is available in historical backtests
- opt-in S23 current-day FSL / TRP missed / not-missed handling is available in historical backtests
- dedicated spot intraday sourcing is available for the opt-in S23 recalculation path
- S23 put-side recalculated strike wording is resolved as a confirmed workbook correction
- S23 option rollover is clarified as not applicable
- `AB6 OS` current-day FSL / TRP rows `183-188` are now cell-audited and implemented only within their confirmed workbook-backed scope
- a broader `AB6 OS` recalculation audit across rows `162-191` is now captured, confirming no extra target override formulas in that block and identifying `Z183:Z186` as workbook-backed current-day entry cells
- workbook-backed current-day option-entry overrides from `AB6 OS!Z183:Z186` are now implemented for supported rows `183-186`
- expiry-day lifecycle review is available in historical reports when selected contract expiry metadata exists
- opt-in option-chain contract selection realism is available in historical backtests
- opt-in contract-specific lifecycle pricing is available when symbol-keyed intraday bars exist for the selected contract
- contract-specific lifecycle provenance now records selected symbol, bar availability, fallback reason, and actual lifecycle price source per trade
- a normalized apples-to-apples lifecycle-source report pair is now in place; on the current fixture set it now isolates 10 trades using real selected-contract bars, 0 explicit fallback, 100.0% lifecycle coverage, and one lifecycle-source-only P&L delta
- a dedicated S23 contract archive ingestion plan is now documented so the next realism step can move from deterministic fixtures toward normalized real/archive contract bars without changing S23 logic
- an S23-only paper-trading readiness audit is now documented, and the current readiness conclusion is explicitly `NO-GO` until paper-runtime data, execution, visibility, and failure-handling gaps are closed
- S23 live-paper normalized data contract and session state-machine blueprints are now documented, defining the next safe implementation boundary for paper runtime scaffolding
- S23 live-paper schema scaffolding and required-field validation are now implemented under `src/tfis/paper`, including normalized event models, no-trade or abort validation results, and session manifest building
- S23 paper-session orchestrator skeleton is now implemented under `src/tfis/paper/orchestrator.py`, with deterministic transitions through `ORDER_PLANNED`, `NO_TRADE`, and `ABORTED`
- S23 paper-session persistent artifacts and journaling shell are now implemented under `src/tfis/paper/artifacts.py`
- S23 paper kill-switch and failure-handling guardrails are now implemented under `src/tfis/paper/guardrails.py` and integrated before `ORDER_PLANNED`
- S23 paper replayable session bundles are now implemented under `src/tfis/paper/replay_bundle.py`
- S23 paper operator-facing review summaries are now implemented under `src/tfis/paper/review.py` and `scripts/review_paper_session.py`
- S23 paper order-intent and execution-journal shell is now implemented under `src/tfis/paper/execution_journal.py`
- S23 paper post-planning failure handling and kill-switch controls are now implemented over the intent shell
- S23 paper-vs-historical replay comparison over the persisted intent shell is now implemented under `src/tfis/paper/paper_vs_historical.py` and `scripts/compare_paper_to_historical.py`
- S23 later-phase execution-shell controls beyond `INTENT_READY` are now implemented over the persisted intent shell
- S23 paper-vs-historical replay comparison is now execution-shell-aware, so it can distinguish planning parity from later pre-execution readiness outcomes
- S23 fillless dispatch shell beyond `EXECUTION_ARMED` is now implemented, and replay comparison now distinguishes later dispatch readiness from earlier arming readiness
- S23 final no-fill execution handoff boundary after `ORDER_INTENT_DISPATCHED` is now implemented, and replay comparison now distinguishes later handoff readiness from earlier execution-shell and dispatch-shell outcomes
- S23 Paper Trading MVP v1 fill simulator and lifecycle-loop design is now documented, so the no-fill shell has a reviewed implementation target instead of an open-ended future phase
- S23 Paper Trading MVP v1 Phase 1 fill simulator is now implemented, so the paper shell can record deterministic `filled`, `not filled`, or `aborted` outcomes without yet opening a paper position
- S23 Paper Trading MVP v1 Phase 2 same-day lifecycle loop is now implemented, so a filled paper order can now open a paper-only position, close on target or stoploss, square off at EOD, or abort explicitly on lifecycle-time data failure
- a broker-agnostic live-paper ingress foundation is now implemented, with `src/tfis/brokers/base.py` defining the adapter boundary, `src/tfis/brokers/fyers.py` providing the first FYERS market-data adapter, and `src/tfis/paper/live_ingress.py` reusing the normalized S23 paper ingress path without exposing S23 to raw broker payloads
- the first broker-backed S23 ingress runner now persists `broker_health.json`, `normalized_events.jsonl`, `ingress_summary.json`, and `no_trade_or_order_plan_summary.json`, while still blocking any broker order placement and stopping at planning by default
- the FYERS ingress runner now also has a strict `--preflight-only` mode plus a dedicated live runbook, so a local operator can validate credentials, paper-only scope, kill-switch posture, and required prelude snapshots before any broker connection attempt
- a read-only TradingEngine capture adapter audit plus prototype now exists, proving that `ticks_context.csv` and `NIFTY50_option_quotes_YYYYMMDD.csv` can feed the S23 market-data leg as normalized TFIS events while still requiring TFIS-side prelude inputs for monthly status and workbook trade plans
- a paired TradingEngine capture plus TFIS prelude ingress-only suite now exists, and the first six real-date run showed that the capture timing path is operationally sound but still `NO_GO` because the raw option quote archives carry blank `oi` at decision time
- read-only shared captured-data adapter is available for normalized CSV roots
- comparison reporting across historical backtest modes is available as a read-only reporting tool
- S23 mode comparison reporting is now bounded, deterministic, and summary-based rather than relying on unbounded raw JSON comparison
- S23 mode comparison now records input-dataset paths, cost settings, and apples-to-apples status; the earlier row-183 `current_day_fsl_trp` exit flip did not reproduce after rerunning all six modes on one shared dataset set
- quality snapshot:
  - tests passing: `426`
  - `python scripts/validate_project.py`: passed

## Completed

- S23 15:00 position-open continuation audited as process-only; numeric continuation rule remains blocked pending new workbook evidence.
- broker-agnostic architecture
- strategy folder layout
- S23 all four branches
- Excel cross-checks
- formula safety validation
- branch selector
- strategy registry governance
- strategy registry enforcement
- shared market-data direction
- reference materials indexed
- review workflow added
- archive governance added
- historical lifecycle backtesting
- EOD policies
- cost and slippage model
- rupee P&L reporting
- equity curve and drawdown reporting
- monthly-status thresholds
- monthly-status decision table
- monthly-status engine
- optional monthly-status-driven historical branch selection
- monthly-status CLI report
- monthly-status manual scenarios
- S23 missed-entry detection foundation
- opt-in S23 historical recalculation mode
- dedicated spot intraday sourcing for opt-in S23 recalculation
- opt-in S23 current-day FSL / TRP missed / not-missed handling
- opt-in option-chain contract selection realism foundation
- opt-in contract-specific lifecycle pricing foundation
- contract-specific lifecycle provenance now records selected symbol, bar availability, fallback reason, and actual lifecycle price source per trade
- a normalized apples-to-apples lifecycle-source report pair is now in place; on the current fixture set it now isolates 10 trades using real selected-contract bars, 0 explicit fallback, 100.0% lifecycle coverage, and one lifecycle-source-only P&L delta
- read-only shared captured-data adapter foundation
- S23 option rollover clarified as not applicable
- expiry-day lifecycle review and audit for selected contracts
- cell-level audit for S23 current-day FSL / TRP rows `183-188`
- comparison reporting across historical backtest modes
- bounded and deterministic S23 historical mode comparison reporting
- apples-to-apples S23 mode comparison rerun with shared datasets and shared cost settings
- deterministic apples-to-apples applied-case fixture added for S23 current-day FSL / TRP row-183 validation
- broader `AB6 OS` rows `162-191` recalculation audit completed, confirming no workbook-backed target overrides in that block and flagging `Z183:Z186` as workbook-backed current-day entry cells
- workbook-backed current-day option-entry overrides from `AB6 OS!Z183:Z186` implemented for supported rows `183-186`
- S23 live-paper normalized data contract blueprint documented
- S23 paper-session state-machine blueprint documented
- S23 live-paper schema scaffolding and required-field validation implemented
- S23 paper-session orchestrator skeleton implemented through `ORDER_PLANNED` / `NO_TRADE` / `ABORTED`
- S23 paper-session persistent artifacts and journaling shell implemented
- S23 paper kill-switch and failure-handling guardrails implemented before planning
- S23 paper replay-bundle manifests, validation, and readback summaries implemented
- S23 paper operator-facing review summaries implemented
- S23 paper order-intent and execution-journal shell implemented
- S23 paper post-planning failure handling and kill-switch controls implemented
- S23 paper-vs-historical replay comparison over the persisted intent shell implemented
- S23 later-phase execution-shell controls beyond `INTENT_READY` implemented
- S23 paper-vs-historical replay comparison extended through the execution-shell readiness layer
- S23 fillless dispatch shell beyond `EXECUTION_ARMED` implemented
- S23 final no-fill execution handoff boundary after `ORDER_INTENT_DISPATCHED` implemented
- S23 Paper Trading MVP v1 fill simulator and lifecycle-loop design documented
- S23 Paper Trading MVP v1 Phase 1 fill simulator implemented
- S23 Paper Trading MVP v1 Phase 2 same-day lifecycle loop implemented
- broker-agnostic live-paper ingress foundation implemented with FYERS as the first market-data adapter
- S23 FYERS live-paper preflight-only safety gate and local runbook implemented
- read-only TradingEngine capture audit and market-event adapter prototype implemented for one-session S23 dry-run inputs
- TradingEngine capture plus TFIS prelude ingress-only suite implemented and exercised across six real captured dates; all six sessions ended `ABORTED` with `missing_contract_oi`, confirming that this path is currently limited by raw option-quote OI completeness rather than by timing or selected-contract discovery

## Next Recommended Priorities

- run the first real local FYERS market-data-only ingress session under the new preflight runbook during market hours
- broaden the broker-backed S23 ingress-only validation set across more normalized archive and replay sessions
- decide whether TradingEngine option-quote captures can be enriched with reliable OI before using them for ingress-only acceptance
- run the first tightly controlled broker-backed live-like fill and same-day lifecycle rehearsal only after ingress thresholds stay green
- broader real/archive contract-specific coverage pilot
- raw shared capture-format adapters beyond normalized CSV roots

## Explicitly Pending

- tighter same-day S23 paper lifecycle parity policy and operator close-out rules
- first real local FYERS market-data-only ingress session under operator sign-off
- fuller strike-availability realism and broader contract-specific archive coverage
- OI-enriched TradingEngine capture path if we want those sessions to qualify for ingress-only acceptance rather than market-data-leg validation only
- raw shared capture-format adapters beyond normalized CSV roots
- futures rollover lifecycle module
- monthly option buying engine
- broad multi-broker live runtime beyond the current market-data-only FYERS adapter

## Notes

- The current project is strong on offline rule validation, workbook tracing, and structural backtesting.
- Production-grade runtime behavior is intentionally deferred until broader broker-backed ingress evidence, operator close-out enforcement, and controlled live-like paper rehearsals are clarified.
