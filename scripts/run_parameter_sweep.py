from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tfis.backtest import ParameterSweepRunner, render_parameter_sweep_markdown
from tfis.backtest.backtest_runner import BacktestRunner
from tfis.execution.order_planner import OrderPlanner
from tfis.market_structure.structure_calculator import MarketStructureCalculator
from tfis.risk.risk_policy import RiskPolicy
from tfis.strategy.strategy_evaluator import StrategyEvaluator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a deterministic TFIS parameter sweep using runtime PARAM overrides."
    )
    parser.add_argument("--experiment", required=True, help="Experiment YAML path")
    parser.add_argument("--out", required=True, help="Path for JSON report output")
    parser.add_argument(
        "--markdown-out",
        required=False,
        help="Optional path for markdown summary output",
    )
    return parser


def _build_runner() -> ParameterSweepRunner:
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


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        report = _build_runner().run_experiment(args.experiment)
    except ValueError as exc:
        print(f"Parameter sweep failed: {exc}")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(_to_jsonable(report), indent=2),
        encoding="utf-8",
    )
    print(f"Parameter sweep report written to {out_path}")

    if args.markdown_out:
        markdown_path = Path(args.markdown_out)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_parameter_sweep_markdown(report),
            encoding="utf-8",
        )
        print(f"Parameter sweep markdown written to {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
