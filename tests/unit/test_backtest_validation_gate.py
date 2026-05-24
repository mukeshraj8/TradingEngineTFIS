from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from tfis.backtest import BacktestInput, BacktestRunner
from tfis.execution.order_planner import OrderPlanner
from tfis.market_structure.ohlc import OhlcBar
from tfis.market_structure.structure_calculator import MarketStructureCalculator
from tfis.risk.risk_policy import RiskPolicy
from tfis.strategy.strategy_evaluator import StrategyEvaluator


ROOT = Path(__file__).resolve().parents[2]
FOLDER_S23 = (
    ROOT
    / "config"
    / "strategies"
    / "options_sell"
    / "nifty"
    / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
)


def _daily_bars() -> list[OhlcBar]:
    return [
        OhlcBar(datetime(2026, 5, 19, 15, 30), 22150.0, 22300.0, 21900.0, 22250.0),
        OhlcBar(datetime(2026, 5, 20, 15, 30), 22250.0, 22400.0, 22000.0, 22350.0),
        OhlcBar(datetime(2026, 5, 21, 15, 30), 22350.0, 22500.0, 22100.0, 22420.0),
        OhlcBar(datetime(2026, 5, 22, 15, 30), 22400.0, 22450.0, 22200.0, 22380.0),
        OhlcBar(datetime(2026, 5, 23, 15, 30), 22320.0, 22400.0, 22100.0, 22310.0),
    ]


def _runner() -> BacktestRunner:
    return BacktestRunner(
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


def _runtime_values() -> dict[str, object]:
    return {
        "ENTRY": 200.0,
        "OPT_LEVELS": {
            "OPT_PRV_3DLL": 220.0,
            "OPT_PRV_2DHH": 300.0,
        },
    }


def _copy_strategy_dir(tmp_path: Path, folder_name: str) -> Path:
    destination = tmp_path / folder_name
    shutil.copytree(FOLDER_S23, destination)
    return destination


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_valid_s23_folder_runs_with_clean_validation() -> None:
    result = _runner().run(
        BacktestInput(
            strategy_path=FOLDER_S23,
            daily_bars=_daily_bars(),
            intraday_bars=None,
            runtime_values=_runtime_values(),
            lot_size=50,
            trades_taken_today=1,
        )
    )

    assert result.accepted is True
    assert result.validation.strategy_config_ok is True
    assert result.validation.formula_safety_findings == []


def test_unsafe_options_entry_formula_is_refused_before_backtest(
    tmp_path: Path,
) -> None:
    strategy_dir = _copy_strategy_dir(tmp_path, "unsafe_s23")
    formulas_path = strategy_dir / "formulas.yaml"
    formulas = _load_yaml(formulas_path)
    formulas["entry_formula"] = "PRV_3DLL - PARAM(entry_discount_pct)%"
    _write_yaml(formulas_path, formulas)

    with pytest.raises(
        ValueError,
        match="Strategy folder validation failed: entry_formula",
    ):
        _runner().run(
            BacktestInput(
                strategy_path=strategy_dir,
                daily_bars=_daily_bars(),
                intraday_bars=None,
                runtime_values=_runtime_values(),
                lot_size=50,
                trades_taken_today=1,
            )
        )


def test_formula_safety_warnings_do_not_fail_backtest(tmp_path: Path) -> None:
    strategy_dir = _copy_strategy_dir(tmp_path, "warning_s23")
    formulas_path = strategy_dir / "formulas.yaml"
    crosscheck_path = strategy_dir / "excel_crosscheck.yaml"

    formulas = _load_yaml(formulas_path)
    formulas["entry_formula"] = "PRV_3DLL - PARAM(entry_discount_pct)%"
    _write_yaml(formulas_path, formulas)

    crosscheck = _load_yaml(crosscheck_path)
    sample = crosscheck["sample_calculation"]
    sample.pop("option_levels", None)
    _write_yaml(crosscheck_path, crosscheck)

    result = _runner().run(
        BacktestInput(
            strategy_path=strategy_dir,
            daily_bars=_daily_bars(),
            intraday_bars=None,
            runtime_values=_runtime_values(),
            lot_size=50,
            trades_taken_today=1,
        )
    )

    assert result.accepted is True
    assert result.validation.strategy_config_ok is True
    assert len(result.validation.formula_safety_findings) == 1
    finding = result.validation.formula_safety_findings[0]
    assert finding.severity == "WARN"
    assert finding.field_name == "entry_formula"

