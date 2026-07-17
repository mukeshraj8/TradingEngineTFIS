from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.paper import (
    CalendarContextEvent,
    CostSlippageSettingsEvent,
    EventEnvelope,
    MonthlyStatusInputEvent,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    PaperSessionConfigEvent,
    PaperTradePlanEvent,
    S23PaperExecutionJournalWriter,
    S23PaperFillSimulator,
    S23PaperFillStatus,
    S23PaperGuardrailSettings,
    S23PaperReplayBundleManager,
    S23PaperSessionArtifactWriter,
    S23PaperSessionOrchestrator,
    S23PaperSessionReviewer,
    SelectedContractQuoteEvent,
    SnapshotLabel,
    UnderlyingQuoteEvent,
    UnderlyingSnapshotEvent,
    compare_paper_session_to_historical,
)


IST = ZoneInfo("Asia/Kolkata")
CONTRACT_SYMBOL = "NIFTY_20260528_22400_PE"
BRANCH = "S23_BEAR_PUT"


def _ts(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, 27, hour, minute, second, tzinfo=IST)


def _envelope(
    event_type: PaperEventType,
    *,
    effective_timestamp: datetime,
    source_id: str | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        session_date=effective_timestamp.date(),
        effective_timestamp=effective_timestamp,
        captured_at=effective_timestamp + timedelta(seconds=1),
        timezone="Asia/Kolkata",
        source_type="paper_fixture",
        source_id=source_id or f"{event_type.value.lower()}-fixture",
        synthetic_fixture=True,
        normalized_by="test-fixture",
    )


def _calendar_context() -> CalendarContextEvent:
    return CalendarContextEvent(
        envelope=_envelope(
            PaperEventType.CALENDAR_CONTEXT,
            effective_timestamp=_ts(9, 0),
        ),
        is_holiday=False,
        is_expiry_day=False,
        weekly_expiry=date(2026, 5, 28),
        market_open=time(9, 15),
        market_close=time(15, 30),
    )


def _monthly_status() -> MonthlyStatusInputEvent:
    return MonthlyStatusInputEvent(
        envelope=_envelope(
            PaperEventType.MONTHLY_STATUS_INPUT,
            effective_timestamp=_ts(9, 1),
        ),
        monthly_status=MonthlyStatus.BEAR,
        status_source="monthly_status_engine",
        reference_date=date(2026, 5, 27),
        threshold_version="v1",
    )


def _paper_config() -> PaperSessionConfigEvent:
    return PaperSessionConfigEvent(
        envelope=_envelope(
            PaperEventType.PAPER_SESSION_CONFIG,
            effective_timestamp=_ts(9, 2),
        ),
        strategy_code="S23",
        paper_mode_enabled=True,
        same_day_square_off_only=True,
        allow_recalculation=False,
        allow_current_day_fsl_trp=True,
        kill_switch_enabled=False,
        operator_id="operator-1",
    )


def _cost_settings() -> CostSlippageSettingsEvent:
    return CostSlippageSettingsEvent(
        envelope=_envelope(
            PaperEventType.COST_SLIPPAGE_SETTINGS,
            effective_timestamp=_ts(9, 3),
        ),
        brokerage_per_lot=20.0,
        slippage_entry_points=1.0,
        slippage_exit_points=1.0,
        spread_buffer_policy="bid_ask_guard",
        version_label="paper-cost-v1",
    )


def _snapshot(label: SnapshotLabel) -> UnderlyingSnapshotEvent:
    timestamp = {
        SnapshotLabel.AT_0915: _ts(9, 15),
        SnapshotLabel.ORPT: _ts(9, 24, 59),
        SnapshotLabel.RC: _ts(9, 29, 59),
    }[label]
    return UnderlyingSnapshotEvent(
        envelope=_envelope(
            PaperEventType.UNDERLYING_SNAPSHOT,
            effective_timestamp=timestamp,
        ),
        snapshot_label=label,
        open=22320.0,
        high=22380.0,
        low=22310.0,
        close=22350.0,
        bar_start=timestamp - timedelta(minutes=1),
        bar_end=timestamp,
        complete=True,
    )


def _underlying_quote() -> UnderlyingQuoteEvent:
    return UnderlyingQuoteEvent(
        envelope=_envelope(
            PaperEventType.UNDERLYING_QUOTE,
            effective_timestamp=_ts(9, 29, 59),
        ),
        symbol="NIFTY",
        ltp=22345.0,
        bid=22344.5,
        ask=22345.5,
        volume=1000.0,
    )


def _option_chain_snapshot() -> OptionChainSnapshotEvent:
    return OptionChainSnapshotEvent(
        envelope=_envelope(
            PaperEventType.OPTION_CHAIN_SNAPSHOT,
            effective_timestamp=_ts(9, 24, 59),
        ),
        underlying_symbol="NIFTY",
        expiry=date(2026, 5, 28),
        contracts=(
            OptionChainContract(
                symbol=CONTRACT_SYMBOL,
                option_type=OptionType.PUT,
                strike=22400.0,
                expiry=date(2026, 5, 28),
                bid=198.0,
                ask=201.0,
                ltp=199.5,
                oi=1200.0,
                volume=250.0,
            ),
        ),
    )


def _selected_contract_quote(
    *,
    effective_timestamp: datetime,
    symbol: str = CONTRACT_SYMBOL,
    bid: float | None = 201.0,
    ask: float | None = 202.0,
    ltp: float | None = 201.5,
) -> SelectedContractQuoteEvent:
    return SelectedContractQuoteEvent(
        envelope=_envelope(
            PaperEventType.SELECTED_CONTRACT_QUOTE,
            effective_timestamp=effective_timestamp,
            source_id=f"selected-contract-{symbol}",
        ),
        symbol=symbol,
        option_type=OptionType.PUT,
        strike=22400.0,
        expiry=date(2026, 5, 28),
        bid=bid,
        ask=ask,
        ltp=ltp,
        oi=1200.0,
        volume=250.0,
    )


def _trade_plan_input() -> PaperTradePlanEvent:
    return PaperTradePlanEvent(
        envelope=_envelope(
            PaperEventType.TRADE_PLAN_INPUT,
            effective_timestamp=_ts(9, 29, 59),
        ),
        strategy_branch=BRANCH,
        order_side="SELL",
        lots=2,
        quantity=100,
        planned_entry_price=199.5,
        target_price=80.0,
        stoploss_price=320.0,
        order_reference_time=_ts(9, 24, 59),
        order_reference_label="ORPT",
        start_strike=21470.0,
        end_strike=22601.0,
        ideal_premium=271.2,
        minimum_premium=203.4,
        source_workbook_rule="AB6_OS_Z184",
        workbook_row_number=184,
        fsl_price=352.0,
    )


def _planned_snapshot():
    orchestrator = S23PaperSessionOrchestrator()
    for event in (
        _calendar_context(),
        _monthly_status(),
        _paper_config(),
        _cost_settings(),
        _snapshot(SnapshotLabel.AT_0915),
        _snapshot(SnapshotLabel.ORPT),
        _snapshot(SnapshotLabel.RC),
        _underlying_quote(),
        _option_chain_snapshot(),
        _selected_contract_quote(effective_timestamp=_ts(9, 29, 59)),
        _trade_plan_input(),
    ):
        orchestrator.ingest_event(event, now=event.envelope.captured_at)
    return orchestrator.finalize(now=_ts(9, 30, 10))


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_session(snapshot, root: Path, *, session_id: str) -> Path:
    artifact_writer = S23PaperSessionArtifactWriter(root / "paper_sessions")
    artifact_set = artifact_writer.write_snapshot(snapshot, session_id=session_id)
    bundle_manager = S23PaperReplayBundleManager()
    bundle_manager.create_bundle(
        artifact_set.session_directory,
        created_at=_ts(9, 31, 0),
        source_artifact_root=artifact_set.session_directory.parent.parent,
    )
    return artifact_set.session_directory


def _write_historical_comparison_artifact(session_dir: Path) -> Path:
    path = session_dir / "paper_vs_historical_comparison.json"
    payload = {
        "artifact_version": 1,
        "status": "MATCH",
        "go_no_go": "GO: the persisted paper intent matches the expected historical trade-plan decision.",
        "comparison_reason": "Paper and historical planning fields matched.",
        "session_id": session_dir.name,
        "session_date": "2026-05-27",
        "strategy_code": "S23",
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _handoff_ready_session(root: Path, *, session_id: str = "phase1-fill") -> Path:
    session_dir = _write_session(_planned_snapshot(), root, session_id=session_id)
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    journal_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=_write_historical_comparison_artifact(session_dir),
        created_at=_ts(9, 30, 40),
    )
    journal_writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 50),
    )
    journal_writer.mark_execution_handoff_ready_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 55),
    )
    return session_dir


def _historical_report_path(tmp_path: Path) -> Path:
    path = tmp_path / "historical_report.json"
    payload = {
        "mode": "historical",
        "strategy_path": "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "strategy_root": None,
        "cost_model": {
            "slippage_points_per_side": 1.0,
            "brokerage_points_per_trade": 0.5,
            "other_cost_points_per_trade": 0.5,
        },
        "input_metadata": {
            "datasets": {},
            "synthetic_fixture_data_used": True,
            "project_fixture_data_used": True,
        },
        "use_monthly_status_engine": True,
        "enable_s23_recalculation": False,
        "enable_s23_current_day_fsl_trp": True,
        "enable_option_chain_selection": True,
        "enable_contract_specific_lifecycle": False,
        "eod_policy": "square_off_at_close",
        "metrics": {
            "total_evaluations": 1,
            "accepted_candidates": 1,
            "rejected_candidates": 0,
            "entered_trades": 1,
            "target_hits": 0,
            "stoploss_hits": 0,
            "eod_square_off": 0,
            "no_entry": 0,
            "no_exit": 0,
            "total_net_pnl_points": 0.0,
            "total_net_pnl_rupees": 0.0,
            "average_net_pnl_rupees": 0.0,
            "max_drawdown_rupees": 0.0,
            "win_rate": 0.0,
            "loss_rate": 0.0,
            "expiry_day_candidates": 0,
            "expiry_day_exit_satisfied": 0,
            "expiry_day_exit_pending": 0,
            "rejection_reason_distribution": {},
        },
        "evaluations": [
            {
                "timestamp": "2026-05-27T15:30:00",
                "strategy_code": "S23",
                "accepted": True,
                "rejection_reason": "Approved",
                "trade_outputs": {
                    "start_strike": 21470.0,
                    "end_strike": 22601.0,
                    "ideal_premium": 271.2,
                    "minimum_premium": 203.4,
                    "entry_price": 199.5,
                    "stoploss_price": 320.0,
                    "target_price": 80.0,
                },
                "lifecycle_result": {
                    "exit_price": 120.0,
                    "net_pnl_points": 0.0,
                    "net_pnl_rupees": 0.0,
                },
                "monthly_status": "BEAR",
                "monthly_status_trigger": "BEAR_A_THRESHOLD",
                "selected_branch_unique_codes": [BRANCH],
                "validation": {
                    "s23_current_day_fsl_trp": {
                        "applied": True,
                        "branch_unique_code": BRANCH,
                        "base_trade_plan": {
                            "symbol": "NIFTY",
                            "option_type": "PUT",
                        },
                        "effective_trade_plan": {
                            "symbol": "NIFTY",
                            "option_type": "PUT",
                        },
                        "result": {
                            "row_number": 184,
                            "source_rule": "AB6_OS_Z184",
                        },
                    },
                    "option_chain_selection": {
                        "selected": True,
                        "selected_contract": {
                            "symbol": CONTRACT_SYMBOL,
                            "option_type": "PUT",
                            "strike": 22400,
                            "expiry": "2026-05-28",
                            "bid": 198.0,
                            "ask": 201.0,
                            "ltp": 199.5,
                            "oi": 1200,
                            "volume": 250,
                        },
                    },
                },
            }
        ],
        "monthly_status_skips": [],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def test_tradable_sell_quote_produces_paper_order_filled(tmp_path: Path) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="filled")
    simulator = S23PaperFillSimulator()

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                bid=201.0,
                ask=202.0,
            ),
        ),
        created_at=_ts(9, 30, 57),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_ORDER_FILLED"
    assert summary["fill_status"] == "PAPER_ORDER_FILLED"
    assert summary["fill_price"] == 200.0
    assert summary["fill_simulated"] is True
    assert summary["position_opened"] is False
    assert artifact_set.paper_fill_path is not None
    assert (session_dir / "paper_position.json").exists() is False
    assert (session_dir / "paper_pnl_summary.json").exists() is False


def test_missing_market_data_produces_paper_order_not_filled(tmp_path: Path) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="no-quote")
    simulator = S23PaperFillSimulator()

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(),
        created_at=_ts(9, 31, 0),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_ORDER_NOT_FILLED"
    assert summary["fill_reason_code"] == "missing_selected_contract_market_data"
    assert artifact_set.paper_no_fill_path is not None


def test_fill_simulation_uses_runtime_shell_when_summary_shell_fields_missing(
    tmp_path: Path,
) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="shell-fallback")
    simulator = S23PaperFillSimulator()

    execution_summary_path = session_dir / "execution_summary.json"
    execution_summary = _read_json(execution_summary_path)
    execution_summary.pop("handoff_shell_status", None)
    execution_summary.pop("execution_shell_status", None)
    execution_summary.pop("dispatch_shell_status", None)
    execution_summary.pop("historical_comparison_status", None)
    execution_summary_path.write_text(
        json.dumps(execution_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                bid=201.0,
                ask=202.0,
            ),
        ),
        created_at=_ts(9, 30, 57),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_ORDER_FILLED"
    assert summary["fill_status"] == "PAPER_ORDER_FILLED"


def test_stale_quote_produces_paper_order_not_filled(tmp_path: Path) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="stale-quote")
    simulator = S23PaperFillSimulator()

    stale_quote = _selected_contract_quote(effective_timestamp=_ts(9, 30, 56))
    stale_quote = SelectedContractQuoteEvent(
        envelope=EventEnvelope(
            event_type=stale_quote.envelope.event_type,
            session_date=stale_quote.envelope.session_date,
            effective_timestamp=stale_quote.envelope.effective_timestamp,
            captured_at=stale_quote.envelope.effective_timestamp + timedelta(minutes=2),
            timezone=stale_quote.envelope.timezone,
            source_type=stale_quote.envelope.source_type,
            source_id=stale_quote.envelope.source_id,
            synthetic_fixture=stale_quote.envelope.synthetic_fixture,
            normalized_by=stale_quote.envelope.normalized_by,
        ),
        symbol=stale_quote.symbol,
        option_type=stale_quote.option_type,
        strike=stale_quote.strike,
        expiry=stale_quote.expiry,
        bid=stale_quote.bid,
        ask=stale_quote.ask,
        ltp=stale_quote.ltp,
        oi=stale_quote.oi,
        volume=stale_quote.volume,
    )

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(stale_quote,),
        created_at=_ts(9, 31, 0),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_ORDER_NOT_FILLED"
    assert summary["fill_reason_code"] == "selected_contract_quote_stale_before_fill"


def test_selected_contract_mismatch_produces_fill_aborted(tmp_path: Path) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="mismatch")
    simulator = S23PaperFillSimulator()

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                symbol="NIFTY_20260528_22300_PE",
            ),
        ),
        created_at=_ts(9, 30, 57),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_FILL_ABORTED"
    assert summary["guardrail_code"] == "selected_contract_mismatch_before_fill"
    assert artifact_set.paper_fill_abort_summary_path is not None


def test_wide_spread_produces_paper_order_not_filled(tmp_path: Path) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="wide-spread")
    simulator = S23PaperFillSimulator(
        guardrail_settings=S23PaperGuardrailSettings(
            max_selected_contract_spread_points=2.0,
        )
    )

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                bid=200.0,
                ask=204.5,
            ),
        ),
        created_at=_ts(9, 30, 57),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_ORDER_NOT_FILLED"
    assert summary["fill_reason_code"] == "selected_contract_spread_too_wide_before_fill"


def test_duplicate_fill_attempt_is_blocked(tmp_path: Path) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="duplicate-fill")
    simulator = S23PaperFillSimulator()
    simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                bid=201.0,
                ask=202.0,
            ),
        ),
        created_at=_ts(9, 30, 57),
    )

    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 58),
                bid=202.0,
                ask=203.0,
            ),
        ),
        created_at=_ts(9, 30, 59),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_FILL_ABORTED"
    assert summary["guardrail_code"] == "duplicate_fill_attempt"


def test_review_shows_fill_status(tmp_path: Path) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="review-fill")
    simulator = S23PaperFillSimulator()
    simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                bid=201.0,
                ask=202.0,
            ),
        ),
        created_at=_ts(9, 30, 57),
    )

    reviewer = S23PaperSessionReviewer()
    review_summary = reviewer.review_session(session_dir, bundle_directory=session_dir)
    markdown = reviewer.render_review_markdown(review_summary)

    assert review_summary.fill_phase is not None
    assert review_summary.fill_phase.status == "PAPER_ORDER_FILLED"
    assert review_summary.runtime_contracts.fill is not None
    assert review_summary.runtime_contracts.fill.status == "PAPER_ORDER_FILLED"
    assert review_summary.runtime_contracts.fill.selected_contract_symbol == "NIFTY_20260528_22400_PE"
    assert "## Fill Phase 1" in markdown
    assert "PAPER_ORDER_FILLED" in markdown
    assert "no target/SL lifecycle monitoring occurred yet" in markdown


def test_review_uses_fill_artifacts_when_execution_summary_fields_missing(
    tmp_path: Path,
) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="review-fill-fallback")
    simulator = S23PaperFillSimulator()
    artifact_set = simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                bid=201.0,
                ask=202.0,
            ),
        ),
        created_at=_ts(9, 30, 57),
    )

    execution_summary = _read_json(artifact_set.execution_summary_path)
    execution_summary.pop("fill_status", None)
    execution_summary.pop("fill_reason_code", None)
    execution_summary.pop("fill_message", None)
    execution_summary.pop("fill_price", None)
    execution_summary.pop("fill_timestamp", None)
    execution_summary.pop("fill_source_kind", None)
    execution_summary.pop("fill_source_type", None)
    execution_summary.pop("fill_source_id", None)
    execution_summary.pop("fill_source_effective_timestamp", None)
    execution_summary.pop("fill_spread_points", None)
    execution_summary.pop("fill_slippage_entry_points", None)
    artifact_set.execution_summary_path.write_text(
        json.dumps(execution_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    reviewer = S23PaperSessionReviewer()
    review_summary = reviewer.review_session(session_dir, bundle_directory=session_dir)

    assert review_summary.fill_phase is not None
    assert review_summary.fill_phase.status == "PAPER_ORDER_FILLED"
    assert review_summary.fill_phase.fill_price == 200.0
    assert review_summary.fill_phase.source_type == "paper_fixture"
    assert review_summary.runtime_contracts.fill is not None
    assert review_summary.runtime_contracts.fill.status == "PAPER_ORDER_FILLED"
    assert review_summary.runtime_contracts.fill.fill_price == 200.0


def test_paper_vs_historical_includes_fill_status(tmp_path: Path) -> None:
    session_dir = _handoff_ready_session(tmp_path, session_id="historical-fill")
    simulator = S23PaperFillSimulator()
    simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                bid=201.0,
                ask=202.0,
            ),
        ),
        created_at=_ts(9, 30, 57),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        _historical_report_path(tmp_path),
        bundle_directory=session_dir,
    )

    assert summary.status.value == "PARTIAL_MATCH"
    assert summary.paper_fill_status == "PAPER_ORDER_FILLED"
    assert "fill" in summary.no_execution_disclaimer.lower()
