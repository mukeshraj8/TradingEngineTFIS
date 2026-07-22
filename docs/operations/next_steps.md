# Next Steps

This document is the execution queue for TFIS. It should be updated whenever
task ordering, blockers, or the recommended next action change in a meaningful
way.

## Immediate Next Priorities

0.5. Remove the remaining S21/S23 morning startup auth race that was exposed on
   Wednesday, July 22, 2026.
   Today's market-time recovery proved that the paper runtime can be rescued,
   but it also proved the current startup design is still suboptimal: S21 and
   S23 can compete for FYERS token/auth refresh at the same startup moment.
   The wrapper retry with `--skip-refresh` is now in place as a safety net, but
   the next engineering step should serialize or centralize token/bootstrap
   work so the race disappears at the root.

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
   6. Tighten state reconciliation rules for waiting orders, open positions,
      closed positions, carry-forward positions, and historical-ledger
      promotion so no trade can appear active and historical at the same time.
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
   a strategy page's active "Trades Taken" monitor or Operator Status panel
   just because that strategy has not produced a fresh session today.

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
   promotion flows wherever they still reconstruct “latest authoritative
   session or latest authoritative trade state” independently beyond the new
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
   is populated continuously during a real market watch. The Trades Taken
   dashboard now surfaces that stream as event count, latest timestamp,
   age/staleness, watcher PID, source, and Market Events artifact link, so the
   live validation should check those fields alongside price and P&L. The
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
4. `TODO` Harden broker/data ingress failure handling for live-readiness.
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
   Shared position discovery now also owns the dashboard's stale-carry-forward
   override lookup through a lenient latest-terminal-position helper, so the
   strategy pages no longer keep a separate raw `paper_position_state.json`
   scan just to suppress stale carry-forward blockers after a terminal close.
   Blocked READY fresh-entry promotion now also works from shared promotion
   candidate records that carry parsed summary data plus any already-
   discovered order-state path for the branch, rather than passing raw
   summary-path tuples through the promotion loop.
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
   The remaining work in this step is to keep shrinking the last places where
   post-close fresh-entry promotion and final ledger promotion can leave
   confusing active-versus-historical evidence behind.
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

## Deferred

- futures rollover module for future-based strategy families
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
