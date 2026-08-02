from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
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
    S23PaperExpiryGovernance,
    S23PaperLiveDecisionBuilder,
    S23PaperPositionStateStore,
    S23PaperPreludeSessionContext,
    S23RuntimeInputDerivationError,
    S23DecisionReferencePacket,
    S23MarketReferencePacket,
    S23MonthlyStatusReferencePacket,
)
from tfis.paper.models import UnderlyingQuoteEvent
from tfis.paper.models import SelectedContractBarEvent


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


def _session_context(day: int = 28) -> S23PaperPreludeSessionContext:
    return S23PaperPreludeSessionContext(
        session_date=date(2026, 5, day),
        timezone="Asia/Kolkata",
        generated_at=_ts(day, 9, 30, 3),
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


def _underlying_bars_live_shape(day: int = 28) -> tuple[UnderlyingHistoryBar, ...]:
    return (
        UnderlyingHistoryBar(
            symbol="NIFTY",
            bar_start=_ts(day, 9, 15),
            bar_end=_ts(day, 9, 15, 59),
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
                symbol="NIFTY_20260604_23700_PE",
                option_type=OptionType.PUT,
                strike=23700.0,
                expiry=date(2026, 6, 4),
                bid=284.0,
                ask=286.0,
                ltp=285.0,
                oi=900.0,
                volume=200.0,
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


def _collected_inputs(day: int = 28) -> S23CollectedSnapshotInputs:
    return S23CollectedSnapshotInputs(
        session_context=_session_context(day),
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
            _selected_contract_bar(day=day, minute=24, low=215.0, high=230.0, close=225.0),
            _selected_contract_bar(day=day, minute=29, low=214.0, high=228.0, close=220.0),
        ),
    )


def _collected_inputs_live_shape(day: int = 28) -> S23CollectedSnapshotInputs:
    return S23CollectedSnapshotInputs(
        session_context=_session_context(day),
        strategy_rule=_strategy_rule(),
        underlying_quote=_underlying_quote(day),
        underlying_bars=_underlying_bars_live_shape(day),
        daily_bars=_daily_bars(day),
        option_chain_snapshot=_option_chain(day),
        expiry_governance=S23PaperExpiryGovernance(
            DeterministicExpiryCalendar(
                explicit_expiries={(ExpiryType.WEEKLY, date(2026, 5, day)): date(2026, 6, 4)}
            )
        ),
        weekly_expiry=date(2026, 6, 4),
        selected_contract_bars=(
            _selected_contract_bar(day=day, minute=24, low=215.0, high=230.0, close=225.0),
            _selected_contract_bar(day=day, minute=29, low=214.0, high=228.0, close=220.0),
        ),
    )


def _selected_contract_bar(
    *,
    day: int,
    minute: int,
    low: float,
    high: float,
    close: float,
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
        symbol="NIFTY_20260604_23750_PE",
        open=close,
        high=high,
        low=low,
        close=close,
        bar_start=bar_start,
        bar_end=bar_start.replace(second=59),
        volume=100.0,
    )


def test_runtime_derivation_and_live_decision_build() -> None:
    result = S23PaperLiveDecisionBuilder().build(
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=_collected_inputs(),
    )

    assert result.summary.status == "READY"
    assert result.summary.monthly_status == "BEAR_CF"
    assert result.summary.required_market_aliases == ("PRV_3DHH",)
    assert result.summary.required_option_aliases == ("OPT_PRV_2DHH", "OPT_PRV_3DLL")
    assert result.summary.checkpoint_labels == ("0915", "ORPT", "RC")
    assert result.summary.selected_contract_symbol == "NIFTY_20260604_23750_PE"
    assert result.summary.selected_contract_oi == 1200.0
    assert result.summary.planned_entry_price == 212.75
    assert result.summary.target_price == pytest.approx(85.1)
    assert result.summary.stoploss_price == pytest.approx(258.94)
    assert result.derived_runtime_inputs.market_levels.current_day_high == 23920.0
    assert result.derived_runtime_inputs.market_levels.current_day_low == 23882.0
    assert result.explanation["monthly_status"]["status"] == "BEAR_CF"
    assert result.explanation["monthly_status"]["lookback_used"] is False
    assert result.explanation["monthly_status"]["trace"][0]["window_label"] == "current"
    assert result.explanation["monthly_status"]["source"] == "tfis_live_daily_history"
    assert result.explanation["contract_selection"]["selected_contract_symbol"] == "NIFTY_20260604_23750_PE"
    assert result.explanation["formula_evaluation"][0]["name"] == "start_strike"
    assert "ROUND_UP" in result.explanation["formula_evaluation"][0]["resolved_formula"]


def test_live_decision_recalculates_bear_put_when_orpt_entry_is_missed() -> None:
    collected_inputs = replace(
        _collected_inputs(),
        selected_contract_bars=(
            _selected_contract_bar(day=28, minute=24, low=180.0, high=200.0, close=190.0),
            _selected_contract_bar(day=28, minute=29, low=175.0, high=205.0, close=180.0),
        ),
    )

    result = S23PaperLiveDecisionBuilder().build(
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=collected_inputs,
    )

    assert result.explanation["orpt_rc_timing"]["status"] == "ENTRY_MISSED_RECALCULATED"
    assert result.summary.planned_entry_price == pytest.approx(161.875)
    assert result.summary.target_price == pytest.approx(64.75)
    assert result.summary.stoploss_price == pytest.approx(219.35)
    assert result.summary.selected_contract_symbol == "NIFTY_20260604_23750_PE"


def test_live_decision_put_missed_entry_uses_orpt_option_low_not_high() -> None:
    collected_inputs = replace(
        _collected_inputs(),
        selected_contract_bars=(
            _selected_contract_bar(day=28, minute=24, low=180.0, high=260.0, close=240.0),
            _selected_contract_bar(day=28, minute=29, low=175.0, high=205.0, close=180.0),
        ),
    )

    result = S23PaperLiveDecisionBuilder().build(
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=collected_inputs,
    )

    assert result.explanation["orpt_rc_timing"]["status"] == "ENTRY_MISSED_RECALCULATED"
    assert result.explanation["orpt_rc_timing"]["missed_rule"] == "PUT missed-entry test: ORPT option low < base entry."
    assert result.explanation["orpt_rc_timing"]["orpt_option_low"] == 180.0
    assert result.explanation["orpt_rc_timing"]["orpt_option_high"] == 260.0


def test_live_decision_missed_entry_uses_configured_target_and_sl_percentages() -> None:
    collected_inputs = replace(
        _collected_inputs(),
        selected_contract_bars=(
            _selected_contract_bar(day=28, minute=24, low=180.0, high=200.0, close=190.0),
            _selected_contract_bar(day=28, minute=29, low=175.0, high=205.0, close=180.0),
        ),
    )
    strategy_rule = _strategy_rule()
    strategy_rule = replace(
        strategy_rule,
        parameters={
            **strategy_rule.parameters,
            "target_pct": 50.0,
            "sl_entry_pct": 20.0,
        },
    )

    result = S23PaperLiveDecisionBuilder().build(
        strategy_rule=strategy_rule,
        reference_packet=_reference_packet(),
        collected_inputs=collected_inputs,
    )

    assert result.explanation["orpt_rc_timing"]["status"] == "ENTRY_MISSED_RECALCULATED"
    assert result.summary.planned_entry_price == pytest.approx(161.875)
    assert result.summary.target_price == pytest.approx(80.9375)
    assert result.summary.stoploss_price == pytest.approx(194.25)


def test_live_decision_accepts_base_entry_at_orpt_without_rc_bar() -> None:
    collected_inputs = replace(
        _collected_inputs(),
        selected_contract_bars=(
            _selected_contract_bar(day=28, minute=24, low=215.0, high=230.0, close=225.0),
        ),
    )

    result = S23PaperLiveDecisionBuilder().build(
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=collected_inputs,
        require_orpt_rc_timing_bars=True,
    )

    assert result.explanation["orpt_rc_timing"]["status"] == "BASE_ENTRY_VALID"
    assert result.summary.selected_contract_symbol == "NIFTY_20260604_23750_PE"
    assert result.summary.planned_entry_price == pytest.approx(212.75)


def test_runtime_derivation_accepts_live_fyers_0915_bar_shape() -> None:
    result = S23PaperLiveDecisionBuilder().build(
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=_collected_inputs_live_shape(),
    )

    assert result.summary.status == "READY"
    assert result.summary.checkpoint_labels == ("0915", "ORPT", "RC")
    assert result.summary.selected_contract_symbol == "NIFTY_20260604_23750_PE"


def test_live_reference_derivation_overrides_stale_packet_levels() -> None:
    packet = _reference_packet()
    stale_packet = S23DecisionReferencePacket(
        instrument_group=packet.instrument_group,
        strategy_branch=packet.strategy_branch,
        monthly_status_levels=S23MonthlyStatusReferencePacket(
            PMH=26000.0,
            PML=25000.0,
            CMH=25800.0,
            CML=24950.0,
            PWH=25750.0,
            PWL=24920.0,
            CWH=25680.0,
            CWL=24890.0,
        ),
        market_reference_levels=S23MarketReferencePacket(
            d2hh=26010.0,
            d2ll=25020.0,
            d3hh=26020.0,
            d3ll=25010.0,
            d4hh=26030.0,
            d4ll=25000.0,
        ),
        option_reference_values=packet.option_reference_values,
        lots=packet.lots,
        quantity=packet.quantity,
        source_workbook_rule=packet.source_workbook_rule,
        workbook_row_number=packet.workbook_row_number,
        fsl_price=packet.fsl_price,
    )

    result = S23PaperLiveDecisionBuilder().build(
        strategy_rule=_strategy_rule(),
        reference_packet=stale_packet,
        collected_inputs=_collected_inputs(),
    )

    assert result.summary.monthly_status == "BEAR_CF"
    assert result.summary.market_levels["d3hh"] == 24510.0


def test_live_decision_builder_writes_explainer_artifacts(tmp_path) -> None:
    builder = S23PaperLiveDecisionBuilder()
    result = builder.build(
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=_collected_inputs(),
    )

    summary_json, summary_md = builder.write_artifacts(result, output_dir=tmp_path)

    assert summary_json.exists()
    assert summary_md.exists()
    explainer_json = tmp_path / "trade_decision_explainer.json"
    explainer_md = tmp_path / "trade_decision_explainer.md"
    assert explainer_json.exists()
    assert explainer_md.exists()
    assert "S23 Trade Decision Explainer" in explainer_md.read_text(encoding="utf-8")
    assert '"contract_selection"' in explainer_json.read_text(encoding="utf-8")


def test_missing_required_option_reference_fails_closed() -> None:
    packet = _reference_packet()
    with pytest.raises(S23RuntimeInputDerivationError) as exc_info:
        S23PaperLiveDecisionBuilder().build(
            strategy_rule=_strategy_rule(),
            reference_packet=S23DecisionReferencePacket(
                instrument_group=packet.instrument_group,
                strategy_branch=packet.strategy_branch,
                monthly_status_levels=packet.monthly_status_levels,
                market_reference_levels=packet.market_reference_levels,
                option_reference_values={"OPT_PRV_3DLL": 230.0},
                lots=packet.lots,
                quantity=packet.quantity,
                source_workbook_rule=packet.source_workbook_rule,
                workbook_row_number=packet.workbook_row_number,
                fsl_price=packet.fsl_price,
                monthly_status_source=packet.monthly_status_source,
                monthly_status_threshold_version=packet.monthly_status_threshold_version,
                runtime_value_overrides=packet.runtime_value_overrides,
                monthly_status_reference_date=packet.monthly_status_reference_date,
            ),
            collected_inputs=_collected_inputs(),
        )

    assert exc_info.value.code == "MISSING_OPTION_REFERENCE_VALUES"


def test_live_decision_rejects_s23_rule_that_does_not_match_matrix() -> None:
    with pytest.raises(S23RuntimeInputDerivationError) as exc_info:
        S23PaperLiveDecisionBuilder().build(
            strategy_rule=replace(
                _strategy_rule(),
                entry_formula="OPT_PRV_3DHH - PARAM(entry_discount_pct)%",
            ),
            reference_packet=_reference_packet(),
            collected_inputs=_collected_inputs(),
        )

    assert exc_info.value.code == "S23_RULE_MATRIX_MISMATCH"
    assert "entry_formula" in str(exc_info.value)


def test_carry_forward_mode_emits_governance_summary() -> None:
    store = S23PaperPositionStateStore()
    open_position = store.create_open_position_state(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        selected_contract_symbol="NIFTY_20260604_23750_PE",
        expiry_date=date(2026, 6, 4),
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=RolloverPolicy.T_MINUS_1,
        forced_close_time=time(15, 15),
        no_carry_past_expiry=True,
        entry_date=date(2026, 5, 28),
        entry_timestamp=_ts(28, 9, 30),
        entry_price=212.75,
        lots=1,
        quantity=75,
        side="SELL",
        target_price=85.1,
        stoploss_price=258.94,
        fsl_price=258.94,
        trp_price=None,
        carry_forward_allowed=True,
        last_updated_timestamp=_ts(28, 15, 20),
        provenance_source_ids=("paper_order_intent.json",),
    )

    result = S23PaperLiveDecisionBuilder().build(
        strategy_rule=_strategy_rule(),
        reference_packet=_reference_packet(),
        collected_inputs=_collected_inputs(day=29),
        carry_forward_position=open_position,
    )

    assert result.summary.mode == "CARRY_FORWARD_RESUME"
    assert result.summary.selected_contract_symbol == "NIFTY_20260604_23750_PE"
    assert result.summary.planned_entry_price == 212.75
    assert "PAPER_POSITION_RESUMED" == result.summary.resume_event_type
    assert result.summary.governance_event_types == ()
    assert result.summary.order_placement_blocked is True
    assert result.summary.order_placement_block_reason == "OPEN_CARRY_FORWARD_POSITION"
    assert result.summary.notes == (
        "Fresh entry planning was computed while an open carry-forward position exists; config blocks fresh paper order creation until the open position exits.",
    )
    assert result.explanation["contract_selection"]["order_placement_blocked"] is True
    assert result.explanation["contract_selection"]["order_placement_block_reason"] == "OPEN_CARRY_FORWARD_POSITION"
