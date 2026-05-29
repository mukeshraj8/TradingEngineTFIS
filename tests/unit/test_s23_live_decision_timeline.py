from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from tfis.domain import StrategyExpiryPolicy, StrategyRule
from tfis.domain.enums import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment
from tfis.market_data import UnderlyingHistoryBar
from tfis.paper import (
    DeterministicExpiryCalendar,
    EventEnvelope,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    S23CollectedSnapshotInputs,
    S23DecisionReferencePacket,
    S23FyersSnapshotPreflightSummary,
    S23LiveDecisionTimelineBuilder,
    S23MarketReferencePacket,
    S23MonthlyStatusReferencePacket,
    S23PaperExpiryGovernance,
    S23PaperPreludeSessionContext,
    run_s23_morning_supervised_decision,
)
from tfis.paper.models import UnderlyingQuoteEvent


IST = ZoneInfo("Asia/Kolkata")


def _ts(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, minute, second, tzinfo=IST)


def _strategy_rule() -> StrategyRule:
    return StrategyRule(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        segment=Segment.OPTIONS_SELL,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
            forced_close_time=time(15, 15),
            no_carry_past_expiry=True,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        option_type=OptionType.PUT,
        entry_time=time(9, 24, 59),
        recalculation_time=time(9, 29, 59),
        start_strike_formula="ROUND_UP(PRV_3DHH - PARAM(strike_buffer_pct)%)",
        end_strike_formula="ROUND_UP(PRV_3DHH) + 1",
        ideal_premium_formula="PRV_3DHH * PARAM(ideal_premium_pct)%",
        minimum_premium_formula="PRV_3DHH * PARAM(minimum_premium_pct)%",
        minimum_oi=500,
        entry_formula="OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
        target_formula="ENTRY - PARAM(target_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
        carry_forward_allowed=True,
        parameters={
            "strike_buffer_pct": 5.0,
            "ideal_premium_pct": 1.2,
            "minimum_premium_pct": 0.9,
            "entry_discount_pct": 7.5,
            "target_pct": 60.0,
            "sl_entry_pct": 60.0,
            "sl_reference_pct": 7.0,
        },
    )


def _session_context(day: int = 28, *, generated_at: datetime | None = None) -> S23PaperPreludeSessionContext:
    return S23PaperPreludeSessionContext(
        session_date=date(2026, 5, day),
        timezone="Asia/Kolkata",
        generated_at=generated_at or _ts(day, 9, 30, 3),
    )


def _underlying_quote(day: int = 28, *, ltp: float = 23780.0) -> UnderlyingQuoteEvent:
    return UnderlyingQuoteEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.UNDERLYING_QUOTE,
            session_date=date(2026, 5, day),
            effective_timestamp=_ts(day, 9, 30, 1),
            captured_at=_ts(day, 9, 30, 2),
            timezone="Asia/Kolkata",
            source_type="unit_test",
            source_id="quote",
            synthetic_fixture=True,
            normalized_by="unit-test",
        ),
        symbol="NIFTY",
        ltp=ltp,
        bid=ltp - 0.5,
        ask=ltp + 0.5,
        volume=1000.0,
    )


def _underlying_bars(day: int = 28) -> tuple[UnderlyingHistoryBar, ...]:
    return (
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=_ts(day, 9, 14),
            bar_end=_ts(day, 9, 14, 59),
            open=23895.0,
            high=23910.0,
            low=23882.0,
            close=23902.0,
            volume=100.0,
            source_id="hist",
        ),
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=_ts(day, 9, 24),
            bar_end=_ts(day, 9, 24, 59),
            open=23902.0,
            high=23918.0,
            low=23890.0,
            close=23912.0,
            volume=120.0,
            source_id="hist",
        ),
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=_ts(day, 9, 29),
            bar_end=_ts(day, 9, 29, 59),
            open=23912.0,
            high=23920.0,
            low=23896.0,
            close=23907.0,
            volume=140.0,
            source_id="hist",
        ),
    )


def _option_chain(day: int = 28) -> OptionChainSnapshotEvent:
    return OptionChainSnapshotEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
            session_date=date(2026, 5, day),
            effective_timestamp=_ts(day, 9, 30, 1),
            captured_at=_ts(day, 9, 30, 2),
            timezone="Asia/Kolkata",
            source_type="unit_test",
            source_id="chain",
            synthetic_fixture=True,
            normalized_by="unit-test",
        ),
        underlying_symbol="NIFTY",
        expiry=date(2026, 6, 4),
        contracts=(
            OptionChainContract(
                symbol="NIFTY_20260604_23650_PE",
                option_type=OptionType.PUT,
                strike=23650.0,
                expiry=date(2026, 6, 4),
                bid=220.0,
                ask=222.0,
                ltp=221.0,
                oi=400.0,
                volume=100.0,
            ),
            OptionChainContract(
                symbol="NIFTY_20260604_23750_PE",
                option_type=OptionType.PUT,
                strike=23750.0,
                expiry=date(2026, 6, 4),
                bid=299.0,
                ask=301.0,
                ltp=300.0,
                oi=1200.0,
                volume=240.0,
            ),
        ),
    )


def _reference_packet() -> S23DecisionReferencePacket:
    return S23DecisionReferencePacket(
        instrument_group="NIFTY",
        strategy_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        monthly_status_levels=S23MonthlyStatusReferencePacket(
            PMH=24900.0,
            PML=24000.0,
            CMH=24750.0,
            CML=23950.0,
            PWH=24680.0,
            PWL=23840.0,
            CWH=24550.0,
            CWL=23820.0,
        ),
        market_reference_levels=S23MarketReferencePacket(
            d2hh=24680.0,
            d2ll=23820.0,
            d3hh=24875.0,
            d3ll=23790.0,
            d4hh=24920.0,
            d4ll=23740.0,
        ),
        option_reference_values={
            "OPT_PRV_2DHH": 242.0,
            "OPT_PRV_3DLL": 230.0,
        },
        lots=1,
        quantity=75,
        source_workbook_rule="AB6_OS_Z186",
        workbook_row_number=186,
        fsl_price=258.94,
    )


def _collected_inputs(day: int = 28, *, generated_at: datetime | None = None) -> S23CollectedSnapshotInputs:
    return S23CollectedSnapshotInputs(
        session_context=_session_context(day, generated_at=generated_at),
        strategy_rule=_strategy_rule(),
        underlying_quote=_underlying_quote(day),
        underlying_bars=_underlying_bars(day),
        option_chain_snapshot=_option_chain(day),
        expiry_governance=S23PaperExpiryGovernance(
            DeterministicExpiryCalendar(
                explicit_expiries={(ExpiryType.WEEKLY, date(2026, 5, day)): date(2026, 6, 4)}
            )
        ),
        weekly_expiry=date(2026, 6, 4),
    )


def _summary() -> S23FyersSnapshotPreflightSummary:
    return S23FyersSnapshotPreflightSummary(
        artifact_version=1,
        provider="fyers",
        session_id="unit",
        session_date=date(2026, 5, 28),
        config_path="config.yaml",
        strategy_path="strategy",
        runtime_fixture_path=None,
        expected_session_directory="tmp",
        artifact_root="tmp",
        uses_payload_fixture=False,
        will_connect_to_broker=False,
        strategy_code="S23",
        strategy_branch_reference="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        contract_cycle="WEEKLY",
        mode="paper",
        paper_mode_enabled=True,
        no_live_orders_allowed=True,
        kill_switch_enabled=True,
        session_kill_switch_active=False,
        weekly_expiry=date(2026, 6, 4),
        underlying_quote_collected=True,
        option_chain_collected=True,
        option_chain_contract_count=2,
        option_chain_has_complete_oi=True,
        dry_run_build_prelude_requested=False,
        prelude_generated=False,
        preflight_status="READY",
        can_run=True,
        issues=(),
        explicit_disclaimer="unit test",
    )


def test_timeline_builder_marks_0916_as_partial() -> None:
    stage_build = S23LiveDecisionTimelineBuilder().build_stage(
        stage_name="Opening Snapshot",
        stage_time=time(9, 16),
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=_collected_inputs(),
    )

    stage = stage_build.stage
    assert stage.available_checkpoint_labels == ("0915",)
    assert stage.waiting_for_checkpoint_labels == ("ORPT", "RC")
    assert stage.can_finalize_trade_decision is False
    assert stage.current_day_high_so_far == 23910.0
    assert stage.current_day_low_so_far == 23882.0
    assert stage.provisional_formula_evaluation[0]["name"] == "start_strike"
    assert stage.decision_summary is None


def test_timeline_builder_marks_0930_as_finalizable() -> None:
    stage_build = S23LiveDecisionTimelineBuilder().build_stage(
        stage_name="RC Snapshot",
        stage_time=time(9, 30),
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=_collected_inputs(),
    )

    stage = stage_build.stage
    assert stage.available_checkpoint_labels == ("0915", "ORPT", "RC")
    assert stage.waiting_for_checkpoint_labels == ()
    assert stage.can_finalize_trade_decision is True
    assert stage.decision_summary is not None
    assert stage.decision_summary["selected_contract_symbol"] == "NIFTY_20260604_23750_PE"
    assert stage.decision_summary["planned_entry_price"] == 212.75


def test_morning_supervised_runner_collects_all_three_stages(monkeypatch, tmp_path: Path) -> None:
    call_index = {"value": 0}

    class FakeCollector:
        def __init__(self, *, artifact_root, prelude_builder=None, position_state_store=None) -> None:
            self._artifact_root = Path(artifact_root)

        def collect_from_files(self, **kwargs):
            idx = call_index["value"]
            call_index["value"] += 1
            session_id = kwargs["session_id"]
            stage_dir = self._artifact_root / date(2026, 5, 28).isoformat() / session_id
            stage_dir.mkdir(parents=True, exist_ok=True)
            generated_minutes = (16, 25, 30)
            return SimpleNamespace(
                session_directory=stage_dir,
                collected_inputs=_collected_inputs(
                    generated_at=_ts(28, 9, generated_minutes[idx], 0)
                ),
                summary=_summary(),
            )

    now_values = iter(
        (
            _ts(28, 9, 16, 0),
            _ts(28, 9, 16, 0),
            _ts(28, 9, 25, 0),
            _ts(28, 9, 25, 0),
            _ts(28, 9, 30, 0),
            _ts(28, 9, 30, 0),
        )
    )

    monkeypatch.setattr("tfis.paper.live_decision_timeline_runner.prepare_fyers_env_from_tradingengine", lambda **kwargs: None)
    monkeypatch.setattr("tfis.paper.live_decision_timeline_runner.load_strategy_rule", lambda path: _strategy_rule())
    monkeypatch.setattr(
        "tfis.paper.live_decision_timeline_runner.load_s23_decision_reference_packet",
        lambda path: _reference_packet(),
    )
    monkeypatch.setattr(
        "tfis.paper.live_decision_timeline_runner.S23LivePaperIngressConfig.from_yaml",
        lambda path: SimpleNamespace(market=SimpleNamespace(selected_contract_symbol="NIFTY_20260604_23750_PE")),
    )
    monkeypatch.setattr("tfis.paper.live_decision_timeline_runner.S23FyersSnapshotCollector", FakeCollector)

    result = run_s23_morning_supervised_decision(
        tradingengine_root="D:/TradingEngineProd",
        config_path="config.yaml",
        strategy_path="strategy",
        reference_packet_path="reference.json",
        artifact_root=tmp_path,
        session_id_prefix="timeline-test",
        skip_refresh=True,
        now_provider=lambda: next(now_values),
        sleeper=lambda seconds: None,
    )

    assert len(result.stage_runs) == 3
    assert result.stage_runs[0].stage.waiting_for_checkpoint_labels == ("ORPT", "RC")
    assert result.stage_runs[1].stage.waiting_for_checkpoint_labels == ("RC",)
    assert result.stage_runs[2].stage.waiting_for_checkpoint_labels == ()
    assert result.final_summary_markdown is not None
    assert result.timeline_markdown.exists()
    assert "09:16" in result.timeline_markdown.read_text(encoding="utf-8")
    assert "09:25" in result.timeline_markdown.read_text(encoding="utf-8")
    assert "09:30" in result.timeline_markdown.read_text(encoding="utf-8")
