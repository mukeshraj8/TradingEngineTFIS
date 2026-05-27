from __future__ import annotations

import json
import subprocess
import sys
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
    S23PaperGuardrailSettings,
    S23PaperReplayBundleManager,
    S23PaperSessionArtifactWriter,
    S23PaperSessionOrchestrator,
    SelectedContractQuoteEvent,
    SnapshotLabel,
    UnderlyingQuoteEvent,
    UnderlyingSnapshotEvent,
)


IST = ZoneInfo("Asia/Kolkata")


def _ts(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, 27, hour, minute, second, tzinfo=IST)


def _envelope(
    event_type: PaperEventType,
    *,
    effective_timestamp: datetime | None = None,
) -> EventEnvelope:
    effective = effective_timestamp or _ts(9, 15)
    return EventEnvelope(
        event_type=event_type,
        session_date=effective.date(),
        effective_timestamp=effective,
        captured_at=effective + timedelta(seconds=1),
        timezone="Asia/Kolkata",
        source_type="paper_fixture",
        source_id=f"{event_type.value.lower()}-source",
        synthetic_fixture=True,
        normalized_by="test-fixture",
    )


def _bundle_dir(tmp_path: Path) -> Path:
    orchestrator = S23PaperSessionOrchestrator()
    events = (
        CalendarContextEvent(
            envelope=_envelope(PaperEventType.CALENDAR_CONTEXT, effective_timestamp=_ts(9, 0)),
            is_holiday=False,
            is_expiry_day=False,
            weekly_expiry=date(2026, 5, 28),
            market_open=time(9, 15),
            market_close=time(15, 30),
        ),
        MonthlyStatusInputEvent(
            envelope=_envelope(PaperEventType.MONTHLY_STATUS_INPUT, effective_timestamp=_ts(9, 1)),
            monthly_status=MonthlyStatus.BEAR,
            status_source="monthly_status_engine",
            reference_date=date(2026, 5, 27),
            threshold_version="v1",
        ),
        PaperSessionConfigEvent(
            envelope=_envelope(PaperEventType.PAPER_SESSION_CONFIG, effective_timestamp=_ts(9, 2)),
            strategy_code="S23",
            paper_mode_enabled=True,
            same_day_square_off_only=True,
            allow_recalculation=False,
            allow_current_day_fsl_trp=True,
            kill_switch_enabled=False,
            operator_id="operator-1",
        ),
        CostSlippageSettingsEvent(
            envelope=_envelope(PaperEventType.COST_SLIPPAGE_SETTINGS, effective_timestamp=_ts(9, 3)),
            brokerage_per_lot=20.0,
            slippage_entry_points=1.0,
            slippage_exit_points=1.0,
            spread_buffer_policy="bid_ask_guard",
            version_label="paper-cost-v1",
        ),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)

    for label in (SnapshotLabel.AT_0915, SnapshotLabel.ORPT, SnapshotLabel.RC):
        timestamp = {
            SnapshotLabel.AT_0915: _ts(9, 15),
            SnapshotLabel.ORPT: _ts(9, 24, 59),
            SnapshotLabel.RC: _ts(9, 29, 59),
        }[label]
        orchestrator.ingest_event(
            UnderlyingSnapshotEvent(
                envelope=_envelope(PaperEventType.UNDERLYING_SNAPSHOT, effective_timestamp=timestamp),
                snapshot_label=label,
                open=22320.0,
                high=22380.0,
                low=22310.0,
                close=22350.0,
                bar_start=timestamp - timedelta(minutes=1),
                bar_end=timestamp,
                complete=True,
            ),
            now=timestamp + timedelta(seconds=1),
        )

    orchestrator.ingest_event(
        UnderlyingQuoteEvent(
            envelope=_envelope(PaperEventType.UNDERLYING_QUOTE, effective_timestamp=_ts(9, 29, 59)),
            symbol="NIFTY",
            ltp=22345.0,
            bid=22344.5,
            ask=22345.5,
            volume=1000.0,
        ),
        now=_ts(9, 30, 0),
    )
    contract = OptionChainContract(
        symbol="NIFTY_20260528_22400_PE",
        option_type=OptionType.PUT,
        strike=22400.0,
        expiry=date(2026, 5, 28),
        bid=198.0,
        ask=201.0,
        ltp=199.5,
        oi=1200.0,
        volume=250.0,
    )
    orchestrator.ingest_event(
        OptionChainSnapshotEvent(
            envelope=_envelope(PaperEventType.OPTION_CHAIN_SNAPSHOT, effective_timestamp=_ts(9, 24, 59)),
            underlying_symbol="NIFTY",
            expiry=date(2026, 5, 28),
            contracts=(contract,),
        ),
        now=_ts(9, 25, 0),
    )
    orchestrator.ingest_event(
        SelectedContractQuoteEvent(
            envelope=_envelope(PaperEventType.SELECTED_CONTRACT_QUOTE, effective_timestamp=_ts(9, 29, 59)),
            symbol="NIFTY_20260528_22400_PE",
            option_type=OptionType.PUT,
            strike=22400.0,
            expiry=date(2026, 5, 28),
            bid=198.0,
            ask=201.0,
            ltp=199.5,
            oi=1200.0,
            volume=250.0,
        ),
        now=_ts(9, 30, 0),
    )
    orchestrator.ingest_event(
        PaperTradePlanEvent(
            envelope=_envelope(PaperEventType.TRADE_PLAN_INPUT, effective_timestamp=_ts(9, 29, 59)),
            strategy_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
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
            source_workbook_rule="AB6_OS_Z186",
            workbook_row_number=186,
        ),
        now=_ts(9, 30, 0),
    )

    snapshot = orchestrator.finalize(now=_ts(9, 30, 10))
    artifact_writer = S23PaperSessionArtifactWriter(tmp_path / "paper_sessions")
    artifact_set = artifact_writer.write_snapshot(snapshot, session_id="cli-paper-compare")
    bundle_manager = S23PaperReplayBundleManager()
    bundle_manager.create_bundle(artifact_set.session_directory, created_at=_ts(9, 31, 0))
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(
        artifact_set.session_directory,
        bundle_directory=artifact_set.session_directory,
        created_at=_ts(9, 30, 20),
    )
    comparison_path = artifact_set.session_directory / "paper_vs_historical_comparison.json"
    comparison_path.write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "status": "MATCH",
                "go_no_go": "GO: the persisted paper intent matches the expected historical trade-plan decision.",
                "comparison_reason": "Paper and historical planning fields matched.",
                "session_id": "cli-paper-compare",
                "session_date": "2026-05-27",
                "strategy_code": "S23",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    armed_writer = S23PaperExecutionJournalWriter(
        guardrail_settings=S23PaperGuardrailSettings(
            require_operator_review_completed_before_execution=True,
            operator_review_completed=True,
        )
    )
    armed_writer.arm_execution_from_session(
        artifact_set.session_directory,
        bundle_directory=artifact_set.session_directory,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 40),
    )
    armed_writer.dispatch_order_intent_from_session(
        artifact_set.session_directory,
        bundle_directory=artifact_set.session_directory,
        created_at=_ts(9, 30, 50),
    )
    armed_writer.mark_execution_handoff_ready_from_session(
        artifact_set.session_directory,
        bundle_directory=artifact_set.session_directory,
        created_at=_ts(9, 30, 55),
    )
    return artifact_set.session_directory


def _historical_report_path(tmp_path: Path) -> Path:
    path = tmp_path / "historical_cli.json"
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
            "target_hits": 1,
            "stoploss_hits": 0,
            "eod_square_off": 0,
            "no_entry": 0,
            "no_exit": 0,
            "total_net_pnl_points": 119.5,
            "total_net_pnl_rupees": 5975.0,
            "average_net_pnl_rupees": 5975.0,
            "max_drawdown_rupees": 0.0,
            "win_rate": 1.0,
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
                    "net_pnl_points": 76.5,
                    "net_pnl_rupees": 3825.0,
                },
                "monthly_status": "BEAR",
                "monthly_status_trigger": "BEAR_A_THRESHOLD",
                "selected_branch_unique_codes": ["NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"],
                "validation": {
                    "s23_current_day_fsl_trp": {
                        "applied": True,
                        "branch_unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
                        "base_trade_plan": {"symbol": "NIFTY", "option_type": "PUT"},
                        "effective_trade_plan": {"symbol": "NIFTY", "option_type": "PUT"},
                        "result": {
                            "row_number": 186,
                            "source_rule": "AB6_OS_Z186",
                        },
                    },
                    "option_chain_selection": {
                        "selected": True,
                        "selected_contract": {
                            "symbol": "NIFTY_20260528_22400_PE",
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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_compare_paper_to_historical_cli_writes_outputs(tmp_path: Path) -> None:
    session_dir = _bundle_dir(tmp_path)
    historical_report = _historical_report_path(tmp_path)
    out_json = tmp_path / "paper_vs_historical.json"
    out_md = tmp_path / "paper_vs_historical.md"
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "compare_paper_to_historical.py"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--bundle-dir",
            str(session_dir),
            "--historical-report",
            str(historical_report),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")

    assert payload["status"] == "MATCH"
    assert payload["paper_execution_shell_status"] == "EXECUTION_ARMED"
    assert payload["paper_dispatch_shell_status"] == "ORDER_INTENT_DISPATCHED"
    assert payload["paper_handoff_shell_status"] == "PAPER_EXECUTION_HANDOFF_READY"
    assert payload["bundle_valid"] is True
    assert "Execution-Shell Readiness" in markdown
    assert "Handoff Shell Status" in markdown
    assert "GO:" in markdown
    assert "No order was placed, no fill was simulated" in markdown
