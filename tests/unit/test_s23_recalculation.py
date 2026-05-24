from __future__ import annotations

from datetime import datetime

import pytest

from tfis.backtest import (
    IntradaySnapshot,
    RecalculationInput,
    S23RecalculationEngine,
)
from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.domain.market_levels import MarketLevels
from tfis.domain.trade_plan import TradePlan


def _base_trade_plan(option_type: OptionType) -> TradePlan:
    return TradePlan(
        strategy_code="S23",
        symbol="NIFTY",
        option_type=option_type,
        start_strike=23100,
        end_strike=21999,
        ideal_premium=264.0,
        minimum_premium=198.0,
        entry_price=203.5,
        stoploss_price=320.0,
        target_price=80.0,
    )


def _snapshots() -> tuple[IntradaySnapshot, IntradaySnapshot]:
    orpt = IntradaySnapshot(
        timestamp=datetime(2026, 5, 23, 9, 24, 59),
        spot_low=22120.0,
        spot_high=22380.0,
        option_low=214.0,
        option_high=228.0,
    )
    recalc = IntradaySnapshot(
        timestamp=datetime(2026, 5, 23, 9, 29, 59),
        spot_low=21850.0,
        spot_high=22620.0,
        option_low=210.0,
        option_high=232.0,
    )
    return orpt, recalc


def test_bull_call_recalculation_matches_expected_values() -> None:
    orpt, recalc = _snapshots()
    result = S23RecalculationEngine().recalculate(
        RecalculationInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
            option_type=OptionType.CALL,
            monthly_status=MonthlyStatus.BULL,
            base_trade_plan=_base_trade_plan(OptionType.CALL),
            market_levels=MarketLevels(d3ll=22000.0),
            option_levels={"OPT_PRV_3DLL": 220.0},
            intraday_snapshot_at_orpt=orpt,
            intraday_snapshot_at_recalc=recalc,
            entry_missed=True,
        )
    )

    assert result.recalculated is True
    assert result.reason == "s23_bull_call_recalculated"
    assert result.recalculated_start_strike == 22942
    assert result.recalculated_end_strike == 21849
    assert result.recalculated_ideal_premium == pytest.approx(262.2)
    assert result.recalculated_minimum_premium == pytest.approx(196.65)
    assert result.recalculated_entry_price == pytest.approx(194.25)
    assert result.source_rule == "S23_BULL_CALL_RECALC_V1"


def test_bear_call_recalculation_matches_expected_values() -> None:
    orpt, recalc = _snapshots()
    result = S23RecalculationEngine().recalculate(
        RecalculationInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
            option_type=OptionType.CALL,
            monthly_status=MonthlyStatus.BEAR,
            base_trade_plan=_base_trade_plan(OptionType.CALL),
            market_levels=MarketLevels(d2ll=22100.0),
            option_levels={"OPT_PRV_2DLL": 215.0},
            intraday_snapshot_at_orpt=orpt,
            intraday_snapshot_at_recalc=IntradaySnapshot(
                timestamp=recalc.timestamp,
                spot_low=21950.0,
                spot_high=recalc.spot_high,
                option_low=205.0,
                option_high=recalc.option_high,
            ),
            entry_missed=True,
        )
    )

    assert result.recalculated is True
    assert result.reason == "s23_bear_call_recalculated"
    assert result.recalculated_start_strike == 23047
    assert result.recalculated_end_strike == 21949
    assert result.recalculated_ideal_premium == pytest.approx(263.4)
    assert result.recalculated_minimum_premium == pytest.approx(197.55)
    assert result.recalculated_entry_price == pytest.approx(189.625)
    assert result.source_rule == "S23_BEAR_CALL_RECALC_V1"


def test_put_branches_recalculate_expected_strike_premium_and_entry_values() -> None:
    orpt, recalc = _snapshots()
    engine = S23RecalculationEngine()

    bull_put = engine.recalculate(
        RecalculationInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
            option_type=OptionType.PUT,
            monthly_status=MonthlyStatus.BULL_CF,
            base_trade_plan=_base_trade_plan(OptionType.PUT),
            market_levels=MarketLevels(d2hh=22500.0),
            option_levels={"OPT_PRV_2DLL": 208.0},
            intraday_snapshot_at_orpt=orpt,
            intraday_snapshot_at_recalc=IntradaySnapshot(
                timestamp=recalc.timestamp,
                spot_low=recalc.spot_low,
                spot_high=22620.0,
                option_low=202.0,
                option_high=recalc.option_high,
            ),
            entry_missed=True,
        )
    )
    bear_put = engine.recalculate(
        RecalculationInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
            option_type=OptionType.PUT,
            monthly_status=MonthlyStatus.BEAR_CF,
            base_trade_plan=_base_trade_plan(OptionType.PUT),
            market_levels=MarketLevels(d3hh=22600.0),
            option_levels={"OPT_PRV_3DLL": 214.0},
            intraday_snapshot_at_orpt=orpt,
            intraday_snapshot_at_recalc=IntradaySnapshot(
                timestamp=recalc.timestamp,
                spot_low=recalc.spot_low,
                spot_high=22710.0,
                option_low=206.0,
                option_high=recalc.option_high,
            ),
            entry_missed=True,
        )
    )

    assert bull_put.reason == "s23_bull_put_recalculated"
    assert bull_put.recalculated_start_strike == 21489
    assert bull_put.recalculated_end_strike == 22621
    assert bull_put.recalculated_ideal_premium == pytest.approx(262.2)
    assert bull_put.recalculated_minimum_premium == pytest.approx(196.65)
    assert bull_put.recalculated_entry_price == pytest.approx(186.85)
    assert bull_put.source_rule == "S23_BULL_PUT_RECALC_V1"
    assert any(
        "MAX(PRV_2DHH, recalc_spot_high)" in note for note in bull_put.audit_notes
    )
    assert not any("unresolved" in note.lower() for note in bull_put.audit_notes)

    assert bear_put.reason == "s23_bear_put_recalculated"
    assert bear_put.recalculated_start_strike == 21575
    assert bear_put.recalculated_end_strike == 22711
    assert bear_put.recalculated_ideal_premium == pytest.approx(262.2)
    assert bear_put.recalculated_minimum_premium == pytest.approx(196.65)
    assert bear_put.recalculated_entry_price == pytest.approx(190.55)
    assert bear_put.source_rule == "S23_BEAR_PUT_RECALC_V1"
    assert any(
        "MAX(PRV_3DHH, recalc_spot_high)" in note for note in bear_put.audit_notes
    )
    assert not any("unresolved" in note.lower() for note in bear_put.audit_notes)


def test_no_recalculation_when_entry_was_not_missed() -> None:
    orpt, recalc = _snapshots()
    result = S23RecalculationEngine().recalculate(
        RecalculationInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
            option_type=OptionType.CALL,
            monthly_status=MonthlyStatus.BULL,
            base_trade_plan=_base_trade_plan(OptionType.CALL),
            market_levels=MarketLevels(d3ll=22000.0),
            option_levels={"OPT_PRV_3DLL": 220.0},
            intraday_snapshot_at_orpt=orpt,
            intraday_snapshot_at_recalc=recalc,
            entry_missed=False,
        )
    )

    assert result.recalculated is False
    assert result.reason == "entry_not_missed"
    assert result.recalculated_start_strike is None
    assert result.recalculated_entry_price is None
    assert result.source_rule is None
