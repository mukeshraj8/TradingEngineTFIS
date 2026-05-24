from __future__ import annotations

import pytest

from tfis.domain.market_levels import MarketLevels
from tfis.formulas import FormulaEngine, FormulaEvaluationError


@pytest.fixture
def market_levels() -> MarketLevels:
    return MarketLevels(
        d2hh=22500.0,
        d2ll=21800.0,
        d3hh=22400.0,
        d3ll=22000.0,
        d4hh=22600.0,
        d4ll=21700.0,
        current_day_high=22450.0,
        current_day_low=22100.0,
    )


def test_parameterized_formula_prv_3dll_plus_param_percent(
    market_levels: MarketLevels,
) -> None:
    value = FormulaEngine().evaluate(
        "PRV_3DLL + PARAM(strike_buffer_pct)%",
        market_levels=market_levels,
        parameters={"strike_buffer_pct": 5.0},
    )

    assert value == pytest.approx(23100.0)


def test_parameterized_formula_entry_minus_param_percent(
    market_levels: MarketLevels,
) -> None:
    value = FormulaEngine().evaluate(
        "ENTRY - PARAM(target_pct)%",
        market_levels=market_levels,
        runtime_values={"ENTRY": 200.0},
        parameters={"target_pct": 60.0},
    )

    assert value == pytest.approx(80.0)


def test_parameterized_formula_min_with_nested_param_percent(
    market_levels: MarketLevels,
) -> None:
    value = FormulaEngine().evaluate(
        "MIN(ENTRY + PARAM(sl_entry_pct)%, PRV_2DHH + PARAM(sl_reference_pct)%)",
        market_levels=market_levels,
        runtime_values={"ENTRY": 200.0},
        parameters={"sl_entry_pct": 60.0, "sl_reference_pct": 7.0},
    )

    assert value == pytest.approx(320.0)


def test_spt_and_opt_aliases_resolve_separately(
    market_levels: MarketLevels,
) -> None:
    engine = FormulaEngine()

    spot_value = engine.evaluate(
        "PRV_3DLL",
        market_levels=market_levels,
    )
    option_value = engine.evaluate(
        "OPT_PRV_3DLL",
        market_levels=market_levels,
        runtime_values={"OPT_LEVELS": {"OPT_PRV_3DLL": 220.0}},
    )

    assert spot_value == pytest.approx(22000.0)
    assert option_value == pytest.approx(220.0)


def test_missing_opt_alias_fails_closed(market_levels: MarketLevels) -> None:
    with pytest.raises(FormulaEvaluationError, match="Missing option reference: OPT_PRV_3DLL"):
        FormulaEngine().evaluate(
            "OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
            market_levels=market_levels,
            parameters={"entry_discount_pct": 7.5},
        )


def test_parameterized_formula_multiplication_percent_behavior(
    market_levels: MarketLevels,
) -> None:
    engine = FormulaEngine()

    ideal = engine.evaluate(
        "PRV_3DLL * PARAM(ideal_premium_pct)%",
        market_levels=market_levels,
        parameters={"ideal_premium_pct": 1.20},
    )
    minimum = engine.evaluate(
        "PRV_3DLL * PARAM(minimum_premium_pct)%",
        market_levels=market_levels,
        parameters={"minimum_premium_pct": 0.90},
    )

    assert ideal == pytest.approx(264.0)
    assert minimum == pytest.approx(198.0)


def test_parameterized_formula_uses_opt_alias_for_entry_and_stoploss_reference(
    market_levels: MarketLevels,
) -> None:
    engine = FormulaEngine()
    runtime_values = {
        "ENTRY": 200.0,
        "OPT_LEVELS": {
            "OPT_PRV_3DLL": 220.0,
            "OPT_PRV_2DHH": 300.0,
        },
    }

    entry_value = engine.evaluate(
        "OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
        market_levels=market_levels,
        runtime_values=runtime_values,
        parameters={"entry_discount_pct": 7.5},
    )
    stoploss_value = engine.evaluate(
        "MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
        market_levels=market_levels,
        runtime_values=runtime_values,
        parameters={"sl_entry_pct": 60.0, "sl_reference_pct": 7.0},
    )

    assert entry_value == pytest.approx(203.5)
    assert stoploss_value == pytest.approx(320.0)


def test_missing_parameter_fails_closed(market_levels: MarketLevels) -> None:
    with pytest.raises(FormulaEvaluationError, match="Missing parameter: strike_buffer_pct"):
        FormulaEngine().evaluate(
            "PRV_3DLL + PARAM(strike_buffer_pct)%",
            market_levels=market_levels,
        )


def test_existing_non_parameter_formula_still_passes(
    market_levels: MarketLevels,
) -> None:
    value = FormulaEngine().evaluate(
        "ROUND_DOWN(PRV_3DLL + 5%)",
        market_levels=market_levels,
    )

    assert value == pytest.approx(23100.0)


def test_runtime_params_override_rule_parameters(market_levels: MarketLevels) -> None:
    value = FormulaEngine().evaluate(
        "ENTRY - PARAM(target_pct)%",
        market_levels=market_levels,
        runtime_values={"ENTRY": 200.0, "PARAMS": {"target_pct": 50.0}},
        parameters={"target_pct": 60.0},
    )

    assert value == pytest.approx(100.0)
