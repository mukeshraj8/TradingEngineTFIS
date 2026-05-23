from __future__ import annotations

import pytest

from tfis.domain.market_levels import MarketLevels
from tfis.formulas import FormulaEngine, FormulaEvaluationError


@pytest.fixture
def market_levels() -> MarketLevels:
    return MarketLevels(
        d2hh=200.0,
        d2ll=180.0,
        d3hh=195.0,
        d3ll=201.5,
        d4hh=205.0,
        d4ll=175.0,
        current_day_high=210.0,
        current_day_low=185.0,
    )


def test_formula_prv_3dll_plus_five_percent(market_levels: MarketLevels) -> None:
    value = FormulaEngine().evaluate(
        "PRV_3DLL + 5%",
        market_levels=market_levels,
    )

    assert value == pytest.approx(211.575)


def test_formula_prv_2dhh_minus_five_percent(market_levels: MarketLevels) -> None:
    value = FormulaEngine().evaluate(
        "PRV_2DHH - 5%",
        market_levels=market_levels,
    )

    assert value == pytest.approx(190.0)


def test_formula_min_with_nested_percentage_expressions(
    market_levels: MarketLevels,
) -> None:
    value = FormulaEngine().evaluate(
        "MIN(ENTRY + 60%, PRV_2DHH + 7%)",
        market_levels=market_levels,
        runtime_values={"ENTRY": 100.0},
    )

    assert value == pytest.approx(160.0)


def test_formula_max_of_market_references(market_levels: MarketLevels) -> None:
    value = FormulaEngine().evaluate(
        "MAX(PRV_3DHH, CDHH)",
        market_levels=market_levels,
    )

    assert value == pytest.approx(210.0)


def test_formula_round_down_of_percentage_expression(
    market_levels: MarketLevels,
) -> None:
    value = FormulaEngine().evaluate(
        "ROUND_DOWN(PRV_3DLL + 5%)",
        market_levels=market_levels,
    )

    assert value == 211.0


def test_invalid_formula_fails_safely(market_levels: MarketLevels) -> None:
    with pytest.raises(
        FormulaEvaluationError,
        match="Unsupported token|Unexpected|Unsupported reference",
    ):
        FormulaEngine().evaluate(
            "__import__('os')",
            market_levels=market_levels,
        )
