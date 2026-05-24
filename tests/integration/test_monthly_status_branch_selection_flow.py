from __future__ import annotations

from pathlib import Path

from tfis.domain.enums import MonthlyStatus
from tfis.monthly_status import MonthlyStatusEngine, MonthlyStatusReferenceLevels
from tfis.strategy import StrategyBranchSelector


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_ROOT = ROOT / "config" / "strategies" / "options_sell" / "nifty"
LEGACY_S23 = ROOT / "config" / "strategies" / "legacy" / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml"

BRANCH_FOLDERS = [
    STRATEGY_ROOT / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
    STRATEGY_ROOT / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    STRATEGY_ROOT / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
    STRATEGY_ROOT / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
]


def _select_for_levels(levels: MonthlyStatusReferenceLevels) -> tuple:
    engine_result = MonthlyStatusEngine().classify("nifty", levels)
    selector = StrategyBranchSelector()
    selected_rules = selector.select(BRANCH_FOLDERS + [LEGACY_S23], engine_result.status)
    return engine_result, selector, [rule.unique_code for rule in selected_rules]


def test_bull_flow_selects_bull_call_and_bull_put() -> None:
    result, selector, selected = _select_for_levels(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=101.0,
        )
    )

    assert result.status == MonthlyStatus.BULL
    assert result.candidates
    assert selected == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    ]
    assert any(issue.path == LEGACY_S23 for issue in selector.last_result.issues)


def test_bull_cf_flow_selects_bull_call_and_bull_put() -> None:
    result, _, selected = _select_for_levels(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=101.6,
        )
    )

    assert result.status == MonthlyStatus.BULL_CF
    assert result.candidates
    assert selected == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    ]


def test_bear_flow_selects_bear_call_and_bear_put() -> None:
    result, _, selected = _select_for_levels(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=89.0,
        )
    )

    assert result.status == MonthlyStatus.BEAR
    assert result.candidates
    assert selected == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    ]


def test_bear_cf_flow_selects_bear_call_and_bear_put() -> None:
    result, _, selected = _select_for_levels(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=88.5,
        )
    )

    assert result.status == MonthlyStatus.BEAR_CF
    assert result.candidates
    assert selected == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    ]


def test_unknown_flow_selects_none() -> None:
    result, _, selected = _select_for_levels(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=95.0,
        )
    )

    assert result.status == MonthlyStatus.UNKNOWN
    assert result.candidates
    assert selected == []


def test_reversal_dominated_conflict_still_drives_bear_branch_selection() -> None:
    result, _, selected = _select_for_levels(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=110.0,
            PWL=104.0,
            CWH=109.0,
            CWL=103.0,
            current_price=102.0,
        )
    )

    assert result.status == MonthlyStatus.BEAR
    assert result.reversal_dominated is True
    assert result.candidates
    assert selected == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    ]
