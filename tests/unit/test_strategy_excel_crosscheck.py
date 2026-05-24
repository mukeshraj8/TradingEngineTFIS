from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tfis.domain.market_levels import MarketLevels
from tfis.importers import load_strategy_rule
from tfis.strategy import StrategyEvaluator


ROOT = Path(__file__).resolve().parents[2]
FOLDER_S23 = (
    ROOT
    / "config"
    / "strategies"
    / "options_sell"
    / "nifty"
    / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
)
EXCEL_CROSSCHECK = FOLDER_S23 / "excel_crosscheck.yaml"


def test_folder_s23_excel_crosscheck_matches_sample_values() -> None:
    rule = load_strategy_rule(FOLDER_S23)
    with EXCEL_CROSSCHECK.open("r", encoding="utf-8") as handle:
        crosscheck = yaml.safe_load(handle)

    assert crosscheck["strategy_code"] == "S23"
    assert crosscheck["unique_code"] == "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert crosscheck["source_sheet"] == "AB6 OS"
    assert crosscheck["source_branch"] == "Bull/Bull CF Call"

    source_cells = crosscheck["source_cells"]
    assert source_cells["monthly_status"] == "D162"
    assert source_cells["option_type"] == "F162"
    assert source_cells["start_strike_formula"] == "G162"
    assert source_cells["end_strike_formula"] == "G163"
    assert source_cells["ideal_premium_formula"] == "H162"
    assert source_cells["minimum_premium_formula"] == "H163"
    assert source_cells["minimum_oi"] == "I162"
    assert source_cells["entry_formula"] == "M162"
    assert source_cells["target_formula"] == "O162"
    assert source_cells["stoploss_formula"] == "M163"

    sample = crosscheck["sample_calculation"]
    market_levels = MarketLevels(
        d3ll=float(sample["spot_levels"]["SPT_PRV_3DLL"]),
        d2hh=float(sample["spot_levels"]["SPT_PRV_2DHH"]),
        current_day_high=22400.0,
        current_day_low=22100.0,
    )
    plan = StrategyEvaluator().evaluate(
        rule,
        market_levels=market_levels,
        runtime_values={
            "ENTRY": float(sample["runtime_values"]["ENTRY"]),
            "OPT_LEVELS": {
                "OPT_PRV_3DLL": float(sample["option_levels"]["OPT_PRV_3DLL"]),
                "OPT_PRV_2DHH": float(sample["option_levels"]["OPT_PRV_2DHH"]),
            },
        },
    )

    expected = sample["expected"]
    assert plan.ideal_premium == pytest.approx(float(expected["ideal_premium"]))
    assert plan.minimum_premium == pytest.approx(float(expected["minimum_premium"]))
    assert plan.entry_price == pytest.approx(float(expected["entry_price"]))
    assert plan.target_price == pytest.approx(float(expected["target_price"]))
    assert plan.stoploss_price == pytest.approx(float(expected["stoploss_price"]))
