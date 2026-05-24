from __future__ import annotations

from pathlib import Path

import pytest

from tfis.domain.enums import MonthlyStatus
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


def _selected_unique_codes(status: MonthlyStatus) -> list[str]:
    rules = StrategyBranchSelector().select(BRANCH_FOLDERS, status)
    return [rule.unique_code for rule in rules]


def test_bull_selects_bull_call_and_bull_put() -> None:
    assert _selected_unique_codes(MonthlyStatus.BULL) == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    ]


def test_bull_cf_selects_bull_call_and_bull_put() -> None:
    assert _selected_unique_codes(MonthlyStatus.BULL_CF) == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    ]


def test_bear_selects_bear_call_and_bear_put() -> None:
    assert _selected_unique_codes(MonthlyStatus.BEAR) == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    ]


def test_bear_cf_selects_bear_call_and_bear_put() -> None:
    assert _selected_unique_codes(MonthlyStatus.BEAR_CF) == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    ]


def test_unknown_selects_none() -> None:
    assert _selected_unique_codes(MonthlyStatus.UNKNOWN) == []


def test_unsupported_status_selects_none() -> None:
    selector = StrategyBranchSelector()
    assert selector.select(BRANCH_FOLDERS, "NOT_A_REAL_STATUS") == []
    assert selector.last_result.normalized_status is None


def test_selector_ignores_legacy_yaml_paths() -> None:
    selected = StrategyBranchSelector().select(
        BRANCH_FOLDERS + [LEGACY_S23],
        MonthlyStatus.BULL,
    )

    assert [rule.unique_code for rule in selected] == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    ]


def test_selector_only_accepts_folder_based_strategies() -> None:
    selected = StrategyBranchSelector().select(
        BRANCH_FOLDERS + [BRANCH_FOLDERS[0] / "strategy.yaml"],
        MonthlyStatus.BULL,
    )

    assert [rule.unique_code for rule in selected] == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    ]


def test_strict_mode_raises_on_invalid_folder(tmp_path: Path) -> None:
    invalid_folder = tmp_path / "invalid_strategy_folder"
    invalid_folder.mkdir()

    selector = StrategyBranchSelector(strict=True)

    with pytest.raises(ValueError, match="missing strategy.yaml"):
        selector.select(BRANCH_FOLDERS + [invalid_folder], MonthlyStatus.BULL)


def test_non_strict_mode_skips_invalid_folder_with_metadata(tmp_path: Path) -> None:
    invalid_folder = tmp_path / "invalid_strategy_folder"
    invalid_folder.mkdir()

    selector = StrategyBranchSelector()
    with pytest.warns(UserWarning, match="missing strategy.yaml"):
        selected = selector.select(BRANCH_FOLDERS + [invalid_folder], MonthlyStatus.BULL)

    assert [rule.unique_code for rule in selected] == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    ]
    assert selector.last_result.issues
    assert selector.last_result.issues[-1].path == invalid_folder
    assert selector.last_result.issues[-1].reason == "missing strategy.yaml in strategy folder"
