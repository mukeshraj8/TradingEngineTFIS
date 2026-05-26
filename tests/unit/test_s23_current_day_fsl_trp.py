from __future__ import annotations

from datetime import datetime

import pytest

from tfis.backtest import (
    CurrentDaySnapshot,
    S23CurrentDayFslTrpEngine,
    S23CurrentDayFslTrpInput,
)
from tfis.domain.enums import OptionType
from tfis.domain.market_levels import MarketLevels
from tfis.domain.trade_plan import TradePlan


def _base_trade_plan(
    *,
    option_type: OptionType,
    start_strike: int = 23047,
    stoploss_price: float = 314.58,
) -> TradePlan:
    return TradePlan(
        strategy_code="S23",
        symbol="NIFTY",
        option_type=option_type,
        start_strike=start_strike,
        end_strike=21949,
        ideal_premium=263.4,
        minimum_premium=197.55,
        entry_price=197.95,
        stoploss_price=stoploss_price,
        target_price=80.0,
    )


def _snapshot(
    *,
    cutoff: datetime,
    spot_low: float,
    spot_high: float,
    option_low: float,
    option_high: float,
) -> CurrentDaySnapshot:
    return CurrentDaySnapshot(
        timestamp=cutoff,
        spot_low=spot_low,
        spot_high=spot_high,
        option_low=option_low,
        option_high=option_high,
    )


def test_row_183_bull_call_not_missed_recalculates_only_workbook_backed_fields() -> None:
    result = S23CurrentDayFslTrpEngine().apply(
        S23CurrentDayFslTrpInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
            base_trade_plan=_base_trade_plan(option_type=OptionType.CALL),
            market_levels=MarketLevels(d3ll=21950.0),
            trigger_snapshot_at_0915=_snapshot(
                cutoff=datetime(2026, 5, 18, 9, 15, 0),
                spot_low=22210.0,
                spot_high=22320.0,
                option_low=250.0,
                option_high=300.0,
            ),
            snapshot_at_orpt=_snapshot(
                cutoff=datetime(2026, 5, 18, 9, 24, 59),
                spot_low=21870.0,
                spot_high=22450.0,
                option_low=240.0,
                option_high=308.0,
            ),
            snapshot_at_recalc=_snapshot(
                cutoff=datetime(2026, 5, 18, 9, 29, 59),
                spot_low=21810.0,
                spot_high=22520.0,
                option_low=230.0,
                option_high=312.0,
            ),
        )
    )

    assert result.applied is True
    assert result.row_number == 183
    assert result.trigger_result.fsl_trp_missed is False
    assert result.effective_option_type == OptionType.CALL
    assert result.recalculated_start_strike == 22963
    assert result.recalculated_end_strike == 21869
    assert result.recalculated_ideal_premium == pytest.approx(262.44)
    assert result.recalculated_minimum_premium == pytest.approx(196.83)
    assert result.recalculated_stoploss_price is None
    assert result.lifecycle_start_after == datetime(2026, 5, 18, 9, 24, 59)
    assert result.source_rule == "AB6_OS_ROW_183"
    assert result.unsupported_fields == ("entry_price", "target_price", "stoploss_price")


def test_row_184_bull_call_missed_uses_workbook_directed_put_formula_family() -> None:
    result = S23CurrentDayFslTrpEngine().apply(
        S23CurrentDayFslTrpInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
            base_trade_plan=_base_trade_plan(option_type=OptionType.CALL),
            market_levels=MarketLevels(d2hh=22410.0),
            trigger_snapshot_at_0915=_snapshot(
                cutoff=datetime(2026, 5, 18, 9, 15, 0),
                spot_low=22210.0,
                spot_high=22320.0,
                option_low=250.0,
                option_high=320.0,
            ),
            snapshot_at_orpt=_snapshot(
                cutoff=datetime(2026, 5, 18, 9, 24, 59),
                spot_low=22150.0,
                spot_high=22480.0,
                option_low=245.0,
                option_high=325.0,
            ),
            snapshot_at_recalc=_snapshot(
                cutoff=datetime(2026, 5, 18, 9, 29, 59),
                spot_low=22120.0,
                spot_high=22650.0,
                option_low=220.0,
                option_high=330.0,
            ),
        )
    )

    assert result.applied is True
    assert result.row_number == 184
    assert result.trigger_result.fsl_trp_missed is True
    assert result.effective_option_type == OptionType.PUT
    assert result.recalculated_start_strike == 21518
    assert result.recalculated_end_strike == 22651
    assert result.recalculated_ideal_premium == pytest.approx(265.44)
    assert result.recalculated_minimum_premium == pytest.approx(199.08)
    assert result.recalculated_stoploss_price == pytest.approx(353.1)
    assert result.lifecycle_start_after == datetime(2026, 5, 18, 9, 29, 59)
    assert result.source_rule == "AB6_OS_ROW_184"
    assert result.unsupported_fields == ("entry_price", "target_price")
    assert any("Put-side Q/R/S/U/W family intentional" in note for note in result.audit_notes)


def test_row_185_bear_call_missed_recalculates_strike_premium_and_fsl() -> None:
    result = S23CurrentDayFslTrpEngine().apply(
        S23CurrentDayFslTrpInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
            base_trade_plan=_base_trade_plan(
                option_type=OptionType.CALL,
                stoploss_price=320.0,
            ),
            market_levels=MarketLevels(d2ll=22010.0),
            trigger_snapshot_at_0915=_snapshot(
                cutoff=datetime(2026, 5, 21, 9, 15, 0),
                spot_low=22310.0,
                spot_high=22410.0,
                option_low=230.0,
                option_high=330.0,
            ),
            snapshot_at_orpt=_snapshot(
                cutoff=datetime(2026, 5, 21, 9, 24, 59),
                spot_low=22220.0,
                spot_high=22420.0,
                option_low=228.0,
                option_high=332.0,
            ),
            snapshot_at_recalc=_snapshot(
                cutoff=datetime(2026, 5, 21, 9, 29, 59),
                spot_low=21920.0,
                spot_high=22550.0,
                option_low=215.0,
                option_high=340.0,
            ),
        )
    )

    assert result.applied is True
    assert result.row_number == 185
    assert result.effective_option_type == OptionType.CALL
    assert result.recalculated_start_strike == 23016
    assert result.recalculated_end_strike == 21919
    assert result.recalculated_ideal_premium == pytest.approx(263.04)
    assert result.recalculated_minimum_premium == pytest.approx(197.28)
    assert result.recalculated_stoploss_price == pytest.approx(374.0)


def test_row_186_bear_put_not_missed_recalculates_only_confirmed_fields() -> None:
    result = S23CurrentDayFslTrpEngine().apply(
        S23CurrentDayFslTrpInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
            base_trade_plan=_base_trade_plan(
                option_type=OptionType.PUT,
                start_strike=21318,
                stoploss_price=319.93,
            ),
            market_levels=MarketLevels(d3hh=22410.0),
            trigger_snapshot_at_0915=_snapshot(
                cutoff=datetime(2026, 5, 18, 9, 15, 0),
                spot_low=22230.0,
                spot_high=22340.0,
                option_low=250.0,
                option_high=300.0,
            ),
            snapshot_at_orpt=_snapshot(
                cutoff=datetime(2026, 5, 18, 9, 24, 59),
                spot_low=22120.0,
                spot_high=22510.0,
                option_low=242.0,
                option_high=306.0,
            ),
            snapshot_at_recalc=_snapshot(
                cutoff=datetime(2026, 5, 18, 9, 29, 59),
                spot_low=22080.0,
                spot_high=22620.0,
                option_low=235.0,
                option_high=310.0,
            ),
        )
    )

    assert result.applied is True
    assert result.row_number == 186
    assert result.effective_option_type == OptionType.PUT
    assert result.recalculated_start_strike == 21385
    assert result.recalculated_end_strike == 22511
    assert result.recalculated_ideal_premium == pytest.approx(265.44)
    assert result.recalculated_minimum_premium == pytest.approx(199.08)
    assert result.recalculated_stoploss_price is None


def test_rows_187_and_188_apply_only_fsl_and_do_not_infer_blank_fields() -> None:
    engine = S23CurrentDayFslTrpEngine()
    bull_result = engine.apply(
        S23CurrentDayFslTrpInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
            base_trade_plan=_base_trade_plan(
                option_type=OptionType.PUT,
                start_strike=21375,
                stoploss_price=320.0,
            ),
            market_levels=MarketLevels(d2hh=22500.0),
            trigger_snapshot_at_0915=_snapshot(
                cutoff=datetime(2026, 5, 23, 9, 15, 0),
                spot_low=22210.0,
                spot_high=22310.0,
                option_low=240.0,
                option_high=325.0,
            ),
            snapshot_at_orpt=_snapshot(
                cutoff=datetime(2026, 5, 23, 9, 24, 59),
                spot_low=22170.0,
                spot_high=22410.0,
                option_low=235.0,
                option_high=330.0,
            ),
            snapshot_at_recalc=_snapshot(
                cutoff=datetime(2026, 5, 23, 9, 29, 59),
                spot_low=22100.0,
                spot_high=22520.0,
                option_low=230.0,
                option_high=340.0,
            ),
        )
    )
    bear_result = engine.apply(
        S23CurrentDayFslTrpInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
            base_trade_plan=_base_trade_plan(
                option_type=OptionType.PUT,
                start_strike=21318,
                stoploss_price=319.93,
            ),
            market_levels=MarketLevels(d3hh=22600.0),
            trigger_snapshot_at_0915=_snapshot(
                cutoff=datetime(2026, 5, 21, 9, 15, 0),
                spot_low=22310.0,
                spot_high=22410.0,
                option_low=245.0,
                option_high=330.0,
            ),
            snapshot_at_orpt=_snapshot(
                cutoff=datetime(2026, 5, 21, 9, 24, 59),
                spot_low=22220.0,
                spot_high=22450.0,
                option_low=238.0,
                option_high=334.0,
            ),
            snapshot_at_recalc=_snapshot(
                cutoff=datetime(2026, 5, 21, 9, 29, 59),
                spot_low=22120.0,
                spot_high=22620.0,
                option_low=232.0,
                option_high=350.0,
            ),
        )
    )

    assert bull_result.row_number == 187
    assert bull_result.recalculated_stoploss_price == pytest.approx(374.0)
    assert bull_result.recalculated_start_strike is None
    assert bull_result.recalculated_ideal_premium is None
    assert "start_strike" in bull_result.unsupported_fields

    assert bear_result.row_number == 188
    assert bear_result.recalculated_stoploss_price == pytest.approx(374.5)
    assert bear_result.recalculated_end_strike is None
    assert bear_result.recalculated_minimum_premium is None
    assert "minimum_premium" in bear_result.unsupported_fields


def test_unsupported_not_missed_paths_are_not_inferred() -> None:
    result = S23CurrentDayFslTrpEngine().apply(
        S23CurrentDayFslTrpInput(
            branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
            base_trade_plan=_base_trade_plan(
                option_type=OptionType.PUT,
                start_strike=21375,
                stoploss_price=320.0,
            ),
            market_levels=MarketLevels(d2hh=22500.0),
            trigger_snapshot_at_0915=_snapshot(
                cutoff=datetime(2026, 5, 23, 9, 15, 0),
                spot_low=22210.0,
                spot_high=22310.0,
                option_low=240.0,
                option_high=300.0,
            ),
            snapshot_at_orpt=_snapshot(
                cutoff=datetime(2026, 5, 23, 9, 24, 59),
                spot_low=22170.0,
                spot_high=22410.0,
                option_low=235.0,
                option_high=305.0,
            ),
            snapshot_at_recalc=_snapshot(
                cutoff=datetime(2026, 5, 23, 9, 29, 59),
                spot_low=22100.0,
                spot_high=22520.0,
                option_low=230.0,
                option_high=306.0,
            ),
        )
    )

    assert result.applied is False
    assert result.reason == "bull_put_not_missed_not_confirmed"
    assert result.row_number is None
    assert result.recalculated_start_strike is None
    assert any("not-missed row" in note for note in result.audit_notes)
