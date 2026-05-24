from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tfis.backtest import ParameterSweepRunner, generate_parameter_combinations
from tfis.backtest.backtest_runner import BacktestRunner
from tfis.execution.order_planner import OrderPlanner
from tfis.market_structure.structure_calculator import MarketStructureCalculator
from tfis.risk.risk_policy import RiskPolicy
from tfis.strategy.strategy_evaluator import StrategyEvaluator


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_S23 = ROOT / "config" / "experiments" / "S23_parameter_sweep.yaml"
STRATEGY_S23 = (
    ROOT
    / "config"
    / "strategies"
    / "options_sell"
    / "nifty"
    / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
)


def _runner() -> ParameterSweepRunner:
    return ParameterSweepRunner(
        BacktestRunner(
            structure_calculator=MarketStructureCalculator(),
            strategy_evaluator=StrategyEvaluator(),
            order_planner=OrderPlanner(),
            risk_policy=RiskPolicy(
                max_lots_per_trade=100,
                max_trades_per_day=3,
                allow_short_options=True,
                paper_only=True,
            ),
        )
    )


def test_generate_parameter_combinations_returns_cartesian_product() -> None:
    combinations = generate_parameter_combinations(
        {
            "strike_buffer_pct": [3.0, 5.0, 7.0],
            "target_pct": [40.0, 50.0, 60.0],
            "sl_entry_pct": [40.0, 60.0],
        }
    )

    assert len(combinations) == 18
    assert combinations[0] == {
        "strike_buffer_pct": 3.0,
        "target_pct": 40.0,
        "sl_entry_pct": 40.0,
    }
    assert combinations[-1] == {
        "strike_buffer_pct": 7.0,
        "target_pct": 60.0,
        "sl_entry_pct": 60.0,
    }


def test_parameter_sweep_runtime_overrides_affect_outputs() -> None:
    report = _runner().run_experiment(EXPERIMENT_S23)

    assert report.summary.total_variants == 18
    assert report.summary.successful_variants == 18
    assert report.summary.failed_variants == 0
    assert report.summary.accepted_trades == 18
    assert report.summary.rejected_trades == 0

    target_40 = next(
        variant
        for variant in report.variants
        if variant.parameters == {
            "strike_buffer_pct": 5.0,
            "target_pct": 40.0,
            "sl_entry_pct": 60.0,
        }
    )
    target_60 = next(
        variant
        for variant in report.variants
        if variant.parameters == {
            "strike_buffer_pct": 5.0,
            "target_pct": 60.0,
            "sl_entry_pct": 60.0,
        }
    )

    assert target_40.result is not None
    assert target_60.result is not None
    assert target_40.result.trade_plan.target_price == pytest.approx(120.0)
    assert target_60.result.trade_plan.target_price == pytest.approx(80.0)


def test_invalid_strategy_path_fails_clearly(tmp_path: Path) -> None:
    experiment_path = tmp_path / "invalid_experiment.yaml"
    experiment_path.write_text(
        yaml.safe_dump(
            {
                "base_strategy": "config/strategies/options_sell/nifty/DOES_NOT_EXIST",
                "overrides": {"target_pct": [40.0, 60.0]},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Base strategy path does not exist"):
        _runner().run_experiment(experiment_path)


def test_strategy_files_are_unchanged_after_sweep() -> None:
    before = {
        name: (STRATEGY_S23 / name).read_text(encoding="utf-8")
        for name in ("strategy.yaml", "formulas.yaml", "parameters.yaml")
    }

    report = _runner().run_experiment(EXPERIMENT_S23)

    after = {
        name: (STRATEGY_S23 / name).read_text(encoding="utf-8")
        for name in ("strategy.yaml", "formulas.yaml", "parameters.yaml")
    }

    assert report.summary.successful_variants == 18
    assert before == after
