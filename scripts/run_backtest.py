from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tfis.backtest import (
    BacktestCsvError,
    BacktestInput,
    BacktestRunner,
    build_backtest_metrics,
    load_daily_bars_csv,
    load_option_levels_csv,
)
from tfis.execution.order_planner import OrderPlanner
from tfis.market_structure.ohlc import OhlcBar
from tfis.market_structure.structure_calculator import MarketStructureCalculator
from tfis.risk.risk_policy import RiskPolicy
from tfis.strategy.strategy_evaluator import StrategyEvaluator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an offline TFIS backtest over deterministic sample inputs."
    )
    parser.add_argument("--strategy-path", required=True, help="Folder-based strategy path")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use deterministic synthetic sample bars",
    )
    parser.add_argument("--daily-csv", help="Path to daily spot/reference OHLC CSV")
    parser.add_argument(
        "--option-levels-csv",
        help="Path to option reference-level CSV",
    )
    parser.add_argument("--out", required=True, help="Path for JSON report output")
    return parser


def _sample_daily_bars() -> list[OhlcBar]:
    return [
        OhlcBar(datetime(2026, 5, 19, 15, 30), 22150.0, 22300.0, 21900.0, 22250.0),
        OhlcBar(datetime(2026, 5, 20, 15, 30), 22250.0, 22400.0, 22000.0, 22350.0),
        OhlcBar(datetime(2026, 5, 21, 15, 30), 22350.0, 22500.0, 22100.0, 22420.0),
        OhlcBar(datetime(2026, 5, 22, 15, 30), 22400.0, 22450.0, 22200.0, 22380.0),
        OhlcBar(datetime(2026, 5, 23, 15, 30), 22320.0, 22400.0, 22100.0, 22310.0),
    ]


def _sample_backtest_input(strategy_path: Path) -> BacktestInput:
    return BacktestInput(
        strategy_path=strategy_path,
        daily_bars=_sample_daily_bars(),
        intraday_bars=None,
        runtime_values={
            "ENTRY": 200.0,
            "OPT_LEVELS": {
                "OPT_PRV_3DLL": 220.0,
                "OPT_PRV_2DHH": 300.0,
            },
        },
        lot_size=50,
        trades_taken_today=1,
    )


def _csv_backtest_input(
    strategy_path: Path,
    *,
    daily_csv: Path,
    option_levels_csv: Path,
) -> BacktestInput:
    return BacktestInput(
        strategy_path=strategy_path,
        daily_bars=load_daily_bars_csv(daily_csv),
        intraday_bars=None,
        runtime_values={
            "ENTRY": 200.0,
            "OPT_LEVELS": load_option_levels_csv(option_levels_csv),
        },
        lot_size=50,
        trades_taken_today=1,
    )


def _build_runner() -> BacktestRunner:
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

    strategy_path = Path(args.strategy_path)
    try:
        if args.sample:
            if args.daily_csv or args.option_levels_csv:
                parser.error("Choose either --sample mode or CSV inputs, not both")
            backtest_input = _sample_backtest_input(strategy_path)
            mode = "sample"
        elif args.daily_csv and args.option_levels_csv:
            backtest_input = _csv_backtest_input(
                strategy_path,
                daily_csv=Path(args.daily_csv),
                option_levels_csv=Path(args.option_levels_csv),
            )
            mode = "csv"
        else:
            parser.error(
                "Provide either --sample or both --daily-csv and --option-levels-csv"
            )
        result = _build_runner().run(backtest_input)
    except (ValueError, BacktestCsvError) as exc:
        print(f"Backtest refused: {exc}")
        return 1

    metrics = build_backtest_metrics([result])

    report = {
        "strategy_path": str(strategy_path),
        "mode": mode,
        "validation": _to_jsonable(result.validation),
        "result": _to_jsonable(result),
        "metrics": _to_jsonable(metrics),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Backtest report written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
