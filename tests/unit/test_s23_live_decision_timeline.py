from __future__ import annotations

import json
from dataclasses import replace
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
from tfis.paper.models import SelectedContractBarEvent, UnderlyingQuoteEvent


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
        end_strike_formula="ROUND_UP(PRV_3DHH) + PARAM(strike_step)",
        ideal_premium_formula="PRV_3DHH * PARAM(ideal_premium_pct)%",
        minimum_premium_formula="PRV_3DHH * PARAM(minimum_premium_pct)%",
        minimum_oi=500,
        entry_formula="OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
        target_formula="ENTRY - PARAM(target_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
        carry_forward_allowed=True,
        parameters={
            "strike_buffer_pct": 5.0,
            "strike_step": 50.0,
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


def _daily_bars(day: int = 28) -> tuple[UnderlyingHistoryBar, ...]:
    return (
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=datetime(2026, 4, 29, 15, 15, tzinfo=IST),
            bar_end=datetime(2026, 4, 29, 15, 29, 59, tzinfo=IST),
            open=24840.0,
            high=24900.0,
            low=24690.0,
            close=24720.0,
            volume=1000.0,
            source_id="daily",
        ),
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=datetime(2026, 4, 30, 15, 15, tzinfo=IST),
            bar_end=datetime(2026, 4, 30, 15, 29, 59, tzinfo=IST),
            open=24720.0,
            high=24810.0,
            low=24580.0,
            close=24610.0,
            volume=1000.0,
            source_id="daily",
        ),
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=datetime(2026, 5, 20, 15, 15, tzinfo=IST),
            bar_end=datetime(2026, 5, 20, 15, 29, 59, tzinfo=IST),
            open=24610.0,
            high=24680.0,
            low=24490.0,
            close=24530.0,
            volume=1000.0,
            source_id="daily",
        ),
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=datetime(2026, 5, 21, 15, 15, tzinfo=IST),
            bar_end=datetime(2026, 5, 21, 15, 29, 59, tzinfo=IST),
            open=24530.0,
            high=24620.0,
            low=24390.0,
            close=24440.0,
            volume=1000.0,
            source_id="daily",
        ),
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=datetime(2026, 5, 22, 15, 15, tzinfo=IST),
            bar_end=datetime(2026, 5, 22, 15, 29, 59, tzinfo=IST),
            open=24440.0,
            high=24510.0,
            low=24220.0,
            close=24310.0,
            volume=1000.0,
            source_id="daily",
        ),
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=datetime(2026, 5, 26, 15, 15, tzinfo=IST),
            bar_end=datetime(2026, 5, 26, 15, 29, 59, tzinfo=IST),
            open=24310.0,
            high=24410.0,
            low=24180.0,
            close=24240.0,
            volume=1000.0,
            source_id="daily",
        ),
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=datetime(2026, 5, 27, 15, 15, tzinfo=IST),
            bar_end=datetime(2026, 5, 27, 15, 29, 59, tzinfo=IST),
            open=24240.0,
            high=24380.0,
            low=24010.0,
            close=24120.0,
            volume=1000.0,
            source_id="daily",
        ),
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=datetime(2026, 5, day, 9, 15, tzinfo=IST),
            bar_end=datetime(2026, 5, day, 15, 29, 59, tzinfo=IST),
            open=23900.0,
            high=23920.0,
            low=23760.0,
            close=23780.0,
            volume=1000.0,
            source_id="daily",
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
            OptionChainContract(
                symbol="NIFTY_20260604_25000_CE",
                option_type=OptionType.CALL,
                strike=25000.0,
                expiry=date(2026, 6, 4),
                bid=284.0,
                ask=286.0,
                ltp=285.0,
                oi=1200.0,
                volume=240.0,
            ),
        ),
    )


def _selected_contract_bar(
    *,
    day: int,
    minute: int,
    symbol: str = "NIFTY_20260604_23750_PE",
    low: float = 215.0,
    high: float = 230.0,
    close: float = 225.0,
) -> SelectedContractBarEvent:
    bar_start = _ts(day, 9, minute)
    return SelectedContractBarEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.SELECTED_CONTRACT_BAR,
            session_date=date(2026, 5, day),
            effective_timestamp=bar_start.replace(second=59),
            captured_at=bar_start.replace(second=59),
            timezone="Asia/Kolkata",
            source_type="unit_test",
            source_id=f"selected-contract-bar:{minute}",
            synthetic_fixture=True,
            normalized_by="unit-test",
        ),
        symbol=symbol,
        open=close,
        high=high,
        low=low,
        close=close,
        bar_start=bar_start,
        bar_end=bar_start.replace(second=59),
        volume=100.0,
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
            "OPT_PRV_2DLL": 210.0,
            "OPT_PRV_3DHH": 260.0,
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
        daily_bars=_daily_bars(day),
        option_chain_snapshot=_option_chain(day),
        expiry_governance=S23PaperExpiryGovernance(
            DeterministicExpiryCalendar(
                explicit_expiries={(ExpiryType.WEEKLY, date(2026, 5, day)): date(2026, 6, 4)}
            )
        ),
        weekly_expiry=date(2026, 6, 4),
        selected_contract_bars=(
            _selected_contract_bar(day=day, minute=24),
            _selected_contract_bar(day=day, minute=29, low=214.0, high=228.0, close=220.0),
        ),
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
    assert stage.monthly_status_lookback_used is False
    assert stage.monthly_status_trace[0]["window_label"] == "current"
    assert stage.provisional_formula_evaluation[0]["name"] == "start_strike"
    assert stage.decision_summary is None


def test_timeline_builder_writes_stage_monthly_status_artifacts(tmp_path: Path) -> None:
    builder = S23LiveDecisionTimelineBuilder()
    stage_build = builder.build_stage(
        stage_name="Opening Snapshot",
        stage_time=time(9, 16),
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=_collected_inputs(),
    )

    (
        stage_json,
        stage_markdown,
        monthly_status_json,
        monthly_status_markdown,
    ) = builder.write_stage_artifacts(
        session_date=date(2026, 5, 28),
        strategy_code="S23",
        strategy_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        stage=stage_build.stage,
        output_dir=tmp_path,
    )

    assert stage_json.exists()
    assert stage_markdown.exists()
    assert monthly_status_json.exists()
    assert monthly_status_markdown.exists()
    assert "Monthly Status: `BEAR_CF`" in monthly_status_markdown.read_text(encoding="utf-8")
    assert "window_label" in monthly_status_json.read_text(encoding="utf-8")


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


def test_timeline_builder_recovers_final_decision_from_live_references() -> None:
    mismatch_inputs = _collected_inputs(day=29)
    mismatch_inputs = S23CollectedSnapshotInputs(
        session_context=mismatch_inputs.session_context,
        strategy_rule=mismatch_inputs.strategy_rule,
        underlying_quote=_underlying_quote(29, ltp=23917.3),
        underlying_bars=mismatch_inputs.underlying_bars,
        daily_bars=mismatch_inputs.daily_bars,
            option_chain_snapshot=mismatch_inputs.option_chain_snapshot,
            expiry_governance=mismatch_inputs.expiry_governance,
            weekly_expiry=mismatch_inputs.weekly_expiry,
            selected_contract_bars=mismatch_inputs.selected_contract_bars,
        )
    stage_build = S23LiveDecisionTimelineBuilder().build_stage(
        stage_name="RC Snapshot",
        stage_time=time(9, 30),
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=mismatch_inputs,
    )

    stage = stage_build.stage
    assert stage.can_finalize_trade_decision is True
    assert stage.decision_summary is not None
    assert stage.decision_summary["monthly_status"] == "BEAR_CF"
    assert stage.decision_failure_code is None


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
            inputs = _collected_inputs(
                generated_at=_ts(28, 9, generated_minutes[idx], 0)
            )
            if idx == 2:
                inputs = replace(
                    inputs,
                    option_chain_snapshot=replace(
                        inputs.option_chain_snapshot,
                        contracts=tuple(
                            replace(contract, bid=304.0, ask=306.0, ltp=305.0)
                            if contract.symbol == "NIFTY_20260604_23700_PE"
                            else replace(contract, bid=194.0, ask=196.0, ltp=195.0)
                            if contract.symbol == "NIFTY_20260604_23750_PE"
                            else contract
                            for contract in inputs.option_chain_snapshot.contracts
                        ),
                    ),
                )
            return SimpleNamespace(
                session_directory=stage_dir,
                collected_inputs=inputs,
                summary=_summary(),
            )

        def collect_selected_contract_bars_from_files(self, **kwargs):
            return (
                _selected_contract_bar(
                    day=28,
                    minute=24,
                    symbol=kwargs["option_symbol"],
                ),
                _selected_contract_bar(
                    day=28,
                    minute=29,
                    symbol=kwargs["option_symbol"],
                    low=214.0,
                    high=228.0,
                    close=220.0,
                ),
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

    monkeypatch.setattr("tfis.paper.live_decision_timeline_runner.prepare_fyers_env_from_tfis_auth", lambda **kwargs: None)
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
        tfis_root="D:/TradingEngineTFIS",
        config_path="config.yaml",
        strategy_path="strategy",
        reference_packet_path="reference.json",
        artifact_root=tmp_path,
        dashboard_output_root=tmp_path / "dashboard",
        session_id_prefix="timeline-test",
        skip_refresh=True,
        now_provider=lambda: next(now_values),
        sleeper=lambda seconds: None,
    )

    assert len(result.stage_runs) == 3
    assert result.stage_runs[0].stage.waiting_for_checkpoint_labels == ("ORPT", "RC")
    assert result.stage_runs[1].stage.waiting_for_checkpoint_labels == ("RC",)
    assert result.stage_runs[2].stage.waiting_for_checkpoint_labels == ()
    assert Path(result.stage_runs[0].monthly_status_markdown).exists()
    assert Path(result.stage_runs[0].stage_explainer_markdown).exists()
    assert "Monthly Status" in Path(result.stage_runs[0].monthly_status_markdown).read_text(encoding="utf-8")
    assert "Opening Snapshot" in Path(result.stage_runs[0].stage_explainer_markdown).read_text(encoding="utf-8")
    assert result.final_summary_markdown is not None
    assert result.timeline_markdown.exists()
    assert (tmp_path / "dashboard" / "index.html").exists()
    assert (tmp_path / "dashboard" / "strategies" / "S23" / "index.html").exists()
    assert "09:16" in result.timeline_markdown.read_text(encoding="utf-8")
    assert "09:25" in result.timeline_markdown.read_text(encoding="utf-8")
    assert "09:30" in result.timeline_markdown.read_text(encoding="utf-8")
    assert result.branch_final_summary_json["NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"]
    summary_payload = json.loads(
        Path(result.branch_final_summary_json["NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"]).read_text(
            encoding="utf-8"
        )
    )
    assert summary_payload["explanation"]["orpt_rc_timing"]["status"] == "BASE_ENTRY_VALID"
    assert summary_payload["summary"]["selected_contract_symbol"] == "NIFTY_20260604_23750_PE"
    metadata = json.loads((result.session_directory / "scheduled_run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["branch_finalization_stage"]["NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"] == "ORPT Snapshot"
    assert metadata["branch_finalization_reason"]["NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"] == "ORPT_BASE_ENTRY_VALID"
    order_payload = json.loads(
        Path(result.branch_order_state_json["NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"]).read_text(
            encoding="utf-8"
        )
    )
    assert order_payload["order_timestamp"].startswith("2026-05-28T09:25:00")


def test_morning_supervised_runner_fans_out_shared_snapshots_to_multiple_branches(
    monkeypatch,
    tmp_path: Path,
) -> None:
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

        def collect_selected_contract_bars_from_files(self, **kwargs):
            return (
                _selected_contract_bar(
                    day=28,
                    minute=24,
                    symbol=kwargs["option_symbol"],
                ),
                _selected_contract_bar(
                    day=28,
                    minute=29,
                    symbol=kwargs["option_symbol"],
                    low=214.0,
                    high=228.0,
                    close=220.0,
                ),
            )

    def fake_strategy_rule(path):
        base = _strategy_rule()
        suffix = Path(str(path)).name.upper()
        if suffix == "BRANCH_CALL":
            return replace(
                base,
                unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
                option_type=OptionType.CALL,
                start_strike_formula="ROUND_DOWN(PRV_2DLL + PARAM(strike_buffer_pct)%)",
                end_strike_formula="ROUND_DOWN(PRV_2DLL) - PARAM(strike_step)",
                ideal_premium_formula="PRV_2DLL * PARAM(ideal_premium_pct)%",
                minimum_premium_formula="PRV_2DLL * PARAM(minimum_premium_pct)%",
                entry_formula="OPT_PRV_2DLL - PARAM(entry_discount_pct)%",
                stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_3DHH + PARAM(sl_reference_pct)%)",
                parameters={**base.parameters, "sl_reference_pct": 10.0},
            )
        return base

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

    monkeypatch.setattr("tfis.paper.live_decision_timeline_runner.prepare_fyers_env_from_tfis_auth", lambda **kwargs: None)
    monkeypatch.setattr("tfis.paper.live_decision_timeline_runner.load_strategy_rule", fake_strategy_rule)
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
        tfis_root="D:/TradingEngineTFIS",
        config_path="config.yaml",
        strategy_path="branch_put",
        strategy_paths=("branch_put", "branch_call"),
        reference_packet_path="reference.json",
        artifact_root=tmp_path,
        dashboard_output_root=None,
        session_id_prefix="timeline-test",
        skip_refresh=True,
        now_provider=lambda: next(now_values),
        sleeper=lambda seconds: None,
    )

    assert call_index["value"] == 3
    assert len(result.stage_runs) == 6
    assert {
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
    } == {stage.strategy_branch for stage in result.stage_runs}
    assert (
        result.session_directory
        / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
        / "trade_decision_explainer.md"
    ).exists()
    assert (
        result.session_directory
        / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
        / "trade_decision_explainer.md"
    ).exists()
