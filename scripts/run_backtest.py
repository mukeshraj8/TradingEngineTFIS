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
    CostModel,
    EodExitPolicy,
    HistoricalBacktestRunner,
    build_backtest_metrics,
    load_daily_bars_csv,
    load_intraday_option_bars_csv,
    load_intraday_spot_bars_csv,
    load_monthly_bars_csv,
    load_option_chain_csv,
    load_option_levels_csv,
    load_option_levels_series_csv,
    load_weekly_bars_csv,
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
    parser.add_argument("--strategy-path", help="Folder-based strategy path")
    parser.add_argument(
        "--strategy-root",
        help="Folder root containing strategy branches for monthly-status selection",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use deterministic synthetic sample bars",
    )
    parser.add_argument(
        "--historical",
        action="store_true",
        help="Evaluate every historical CSV row chronologically",
    )
    parser.add_argument("--daily-csv", help="Path to daily spot/reference OHLC CSV")
    parser.add_argument(
        "--option-levels-csv",
        help="Path to option reference-level CSV",
    )
    parser.add_argument(
        "--option-intraday-csv",
        help="Optional path to intraday option OHLC CSV for lifecycle simulation",
    )
    parser.add_argument(
        "--spot-intraday-csv",
        help="Optional path to intraday spot/index OHLC CSV for S23 recalculation sourcing",
    )
    parser.add_argument(
        "--use-monthly-status-engine",
        action="store_true",
        help="Select eligible strategy branches from --strategy-root using monthly-status inputs",
    )
    parser.add_argument(
        "--enable-s23-recalculation",
        action="store_true",
        help="Opt-in diagnostic S23 ORPT missed-entry detection and recalculation during historical backtests",
    )
    parser.add_argument(
        "--option-chain-csv",
        help="Optional path to option-chain contract CSV for opt-in contract selection realism",
    )
    parser.add_argument(
        "--enable-option-chain-selection",
        action="store_true",
        help="Opt-in option-chain contract selection within computed strike ranges during historical backtests",
    )
    parser.add_argument("--monthly-csv", help="Path to monthly reference OHLC CSV")
    parser.add_argument("--weekly-csv", help="Path to weekly reference OHLC CSV")
    parser.add_argument(
        "--eod-policy",
        choices=[policy.value for policy in EodExitPolicy],
        default=EodExitPolicy.MARK_NO_EXIT.value,
        help="End-of-day handling policy for entered trades with no target/stoploss exit",
    )
    parser.add_argument(
        "--slippage-points-per-side",
        type=float,
        default=0.0,
        help="Applied slippage points per side for completed trades",
    )
    parser.add_argument(
        "--brokerage-points-per-trade",
        type=float,
        default=0.0,
        help="Applied brokerage points per completed trade",
    )
    parser.add_argument(
        "--other-cost-points-per-trade",
        type=float,
        default=0.0,
        help="Applied additional cost points per completed trade",
    )
    parser.add_argument("--out", required=True, help="Path for JSON report output")
    parser.add_argument(
        "--markdown-out",
        help="Optional path for a markdown backtest report",
    )
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


def _build_historical_runner(
    eod_policy: EodExitPolicy,
    cost_model: CostModel,
) -> HistoricalBacktestRunner:
    return HistoricalBacktestRunner(
        _build_runner(),
        eod_policy=eod_policy,
        cost_model=cost_model,
    )


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


def _format_number(value: Any, *, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _format_percent(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _render_validation_status_historical(report: dict[str, Any]) -> str:
    evaluations = report.get("evaluations", [])
    if not evaluations:
        return "N/A"
    all_ok = True
    findings_count = 0
    for evaluation in evaluations:
        validation = evaluation.get("validation", {})
        if not validation.get("strategy_config_ok", False):
            all_ok = False
        findings_count += len(validation.get("formula_safety_findings", []))
    status = "PASS" if all_ok else "FAIL"
    if findings_count:
        return f"{status} ({findings_count} formula safety finding(s) reported)"
    return status


def _render_historical_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    evaluations = report.get("evaluations", [])
    monthly_status_skips = report.get("monthly_status_skips", [])
    cost_model = report.get("cost_model", {})
    strategy_code = evaluations[0]["strategy_code"] if evaluations else "-"
    lines = [
        "# Historical Backtest Report",
        "",
        f"- Strategy path: `{report.get('strategy_path') or '-'}`",
        f"- Strategy root: `{report.get('strategy_root') or '-'}`",
        f"- Strategy code: `{strategy_code}`",
        f"- Mode: `{report['mode']}`",
        f"- EOD policy: `{report.get('eod_policy', EodExitPolicy.MARK_NO_EXIT.value)}`",
        f"- Monthly-status engine: `{'enabled' if report.get('use_monthly_status_engine') else 'disabled'}`",
        f"- Validation status: `{_render_validation_status_historical(report)}`",
        "",
        "This is offline simulation. It does not include brokerage, slippage, liquidity, or real fill modeling yet.",
        "",
        "## Cost Assumptions",
        "",
        f"- slippage_points_per_side: `{_format_number(cost_model.get('slippage_points_per_side'))}`",
        f"- brokerage_points_per_trade: `{_format_number(cost_model.get('brokerage_points_per_trade'))}`",
        f"- other_cost_points_per_trade: `{_format_number(cost_model.get('other_cost_points_per_trade'))}`",
        "",
        "## Summary Metrics",
        "",
        f"- total_evaluations: `{metrics['total_evaluations']}`",
        f"- accepted_candidates: `{metrics['accepted_candidates']}`",
        f"- entered_trades: `{metrics['entered_trades']}`",
        f"- target_hits: `{metrics['target_hits']}`",
        f"- stoploss_hits: `{metrics['stoploss_hits']}`",
        f"- eod_square_off: `{metrics.get('eod_square_off', 0)}`",
        f"- carry_forward_pending: `{metrics.get('carry_forward_pending', 0)}`",
        f"- no_entry: `{metrics['no_entry']}`",
        f"- no_exit: `{metrics['no_exit']}`",
        f"- total_gross_pnl_points: `{_format_number(metrics.get('total_gross_pnl_points', metrics['total_pnl_points']), digits=3)}`",
        f"- total_cost_points: `{_format_number(metrics.get('total_cost_points'), digits=3)}`",
        f"- total_net_pnl_points: `{_format_number(metrics.get('total_net_pnl_points'), digits=3)}`",
        f"- total_gross_pnl_rupees: `{_format_number(metrics.get('total_gross_pnl_rupees'), digits=2)}`",
        f"- total_cost_rupees: `{_format_number(metrics.get('total_cost_rupees'), digits=2)}`",
        f"- total_net_pnl_rupees: `{_format_number(metrics.get('total_net_pnl_rupees'), digits=2)}`",
        f"- total_pnl_points: `{_format_number(metrics['total_pnl_points'], digits=3)}`",
        f"- average_pnl_points: `{_format_number(metrics['average_pnl_points'], digits=3)}`",
        f"- average_net_pnl_points: `{_format_number(metrics.get('average_net_pnl_points'), digits=3)}`",
        f"- average_net_pnl_rupees: `{_format_number(metrics.get('average_net_pnl_rupees'), digits=2)}`",
        f"- win_rate: `{_format_percent(metrics['win_rate'])}`",
        f"- loss_rate: `{_format_percent(metrics['loss_rate'])}`",
        f"- average_mfe: `{_format_number(metrics['average_mfe'], digits=2)}`",
        f"- average_mae: `{_format_number(metrics['average_mae'], digits=2)}`",
        "",
        "## Equity And Drawdown",
        "",
        f"- final_net_pnl_rupees: `{_format_number(metrics.get('final_net_pnl_rupees'), digits=2)}`",
        f"- max_drawdown_rupees: `{_format_number(metrics.get('max_drawdown_rupees'), digits=2)}`",
        f"- max_drawdown_points: `{_format_number(metrics.get('max_drawdown_points'), digits=3)}`",
        f"- best_trade_net_rupees: `{_format_number(metrics.get('best_trade_net_rupees'), digits=2)}`",
        f"- worst_trade_net_rupees: `{_format_number(metrics.get('worst_trade_net_rupees'), digits=2)}`",
        "",
    ]

    if report.get("enable_s23_recalculation"):
        lines.insert(
            8,
            "- S23 recalculation: `enabled`",
        )
    if report.get("enable_option_chain_selection"):
        lines.insert(
            9,
            "- Option-chain selection: `enabled`",
        )

    if monthly_status_skips:
        lines.extend(
            [
                "## Monthly Status Skips",
                "",
                "| Timestamp | Reason |",
                "| --- | --- |",
            ]
        )
        for skip in monthly_status_skips:
            lines.append(f"| {skip['timestamp']} | {skip['reason']} |")
        lines.append("")

    lines.extend(
        [
        "## Trade Table",
        "",
        "| Timestamp | Monthly Status | Selected Branches | Entry Price | Exit Price | Exit Reason | Gross PnL | Costs | Net PnL | Net Rupees | Cumulative Net Rupees | Drawdown Rupees | MFE | MAE | Bars Held |",
        "| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for evaluation in evaluations:
        lifecycle = evaluation.get("lifecycle_result") or {}
        lines.append(
            "| "
            f"{evaluation['timestamp']} | "
            f"{evaluation.get('monthly_status') or '-'} | "
            f"{', '.join(evaluation.get('selected_branch_unique_codes') or []) or '-'} | "
            f"{_format_number(evaluation['trade_outputs'].get('entry_price'))} | "
            f"{_format_number(lifecycle.get('exit_price'))} | "
            f"{lifecycle.get('exit_reason', '-')} | "
            f"{_format_number(lifecycle.get('gross_pnl_points', lifecycle.get('pnl_points')), digits=3)} | "
            f"{_format_number(lifecycle.get('total_cost_points'), digits=3)} | "
            f"{_format_number(lifecycle.get('net_pnl_points'), digits=3)} | "
            f"{_format_number(lifecycle.get('net_pnl_rupees'), digits=2)} | "
            f"{_format_number(lifecycle.get('cumulative_net_pnl_rupees'), digits=2)} | "
            f"{_format_number(lifecycle.get('drawdown_rupees'), digits=2)} | "
            f"{_format_number(lifecycle.get('max_favorable_excursion'), digits=2)} | "
            f"{_format_number(lifecycle.get('max_adverse_excursion'), digits=2)} | "
            f"{_format_number(lifecycle.get('bars_held'))} |"
        )

    return "\n".join(lines) + "\n"


def _render_single_result_markdown(report: dict[str, Any]) -> str:
    result = report["result"]
    trade_plan = result["trade_plan"]
    validation = report.get("validation", {})
    cost_model = report.get("cost_model", {})
    lines = [
        "# Backtest Report",
        "",
        f"- Strategy path: `{report['strategy_path']}`",
        f"- Strategy code: `{result['strategy_code']}`",
        f"- Mode: `{report['mode']}`",
        f"- EOD policy: `{report.get('eod_policy', EodExitPolicy.MARK_NO_EXIT.value)}`",
        f"- Validation status: `{'PASS' if validation.get('strategy_config_ok') else 'FAIL'}`",
        "",
        "This is offline simulation. It does not include brokerage, slippage, liquidity, or real fill modeling yet.",
        "",
        "## Cost Assumptions",
        "",
        f"- slippage_points_per_side: `{_format_number(cost_model.get('slippage_points_per_side'))}`",
        f"- brokerage_points_per_trade: `{_format_number(cost_model.get('brokerage_points_per_trade'))}`",
        f"- other_cost_points_per_trade: `{_format_number(cost_model.get('other_cost_points_per_trade'))}`",
        "",
        "## Summary Metrics",
        "",
        f"- total_evaluations: `{report['metrics']['total_candidates']}`",
        f"- accepted_candidates: `{report['metrics']['accepted_trades']}`",
        f"- entered_trades: `-`",
        f"- target_hits: `-`",
        f"- stoploss_hits: `-`",
        f"- eod_square_off: `-`",
        f"- carry_forward_pending: `-`",
        f"- no_entry: `-`",
        f"- no_exit: `-`",
        f"- total_gross_pnl_points: `-`",
        f"- total_cost_points: `-`",
        f"- total_net_pnl_points: `-`",
        f"- total_gross_pnl_rupees: `-`",
        f"- total_cost_rupees: `-`",
        f"- total_net_pnl_rupees: `-`",
        f"- total_pnl_points: `-`",
        f"- average_pnl_points: `-`",
        f"- average_net_pnl_points: `-`",
        f"- average_net_pnl_rupees: `-`",
        f"- win_rate: `-`",
        f"- loss_rate: `-`",
        f"- average_mfe: `-`",
        f"- average_mae: `-`",
        "",
        "## Equity And Drawdown",
        "",
        f"- final_net_pnl_rupees: `-`",
        f"- max_drawdown_rupees: `-`",
        f"- max_drawdown_points: `-`",
        f"- best_trade_net_rupees: `-`",
        f"- worst_trade_net_rupees: `-`",
        "",
        "## Trade Table",
        "",
        "| Timestamp | Entry Price | Exit Price | Exit Reason | Gross PnL | Costs | Net PnL | Net Rupees | Cumulative Net Rupees | Drawdown Rupees | MFE | MAE | Bars Held |",
        "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        "| "
        f"- | {_format_number(trade_plan.get('entry_price'))} | - | {result.get('reason', '-')} | - | - | - | - | - | - | - | - | - |",
    ]
    return "\n".join(lines) + "\n"


def _render_backtest_markdown(report: dict[str, Any]) -> str:
    if report["mode"] == "historical":
        return _render_historical_markdown(report)
    return _render_single_result_markdown(report)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    strategy_path = Path(args.strategy_path) if args.strategy_path else None
    strategy_root = Path(args.strategy_root) if args.strategy_root else None
    eod_policy = EodExitPolicy(args.eod_policy)
    cost_model = CostModel(
        slippage_points_per_side=float(args.slippage_points_per_side),
        brokerage_points_per_trade=float(args.brokerage_points_per_trade),
        other_cost_points_per_trade=float(args.other_cost_points_per_trade),
    )
    try:
        if args.sample:
            if args.use_monthly_status_engine:
                parser.error("--sample cannot be combined with --use-monthly-status-engine")
            if args.enable_s23_recalculation:
                parser.error("--enable-s23-recalculation is supported only with --historical")
            if args.enable_option_chain_selection:
                parser.error("--enable-option-chain-selection is supported only with --historical")
            if strategy_path is None:
                parser.error("--sample requires --strategy-path")
            if (
                args.historical
                or args.daily_csv
                or args.option_levels_csv
                or args.option_intraday_csv
                or args.spot_intraday_csv
                or args.option_chain_csv
                or args.strategy_root
                or args.monthly_csv
                or args.weekly_csv
            ):
                parser.error(
                    "Choose either --sample mode or CSV inputs, not both"
                )
            backtest_input = _sample_backtest_input(strategy_path)
            mode = "sample"
            report = None
        elif args.daily_csv and args.option_levels_csv:
            if args.historical:
                if args.use_monthly_status_engine:
                    if strategy_root is None:
                        parser.error(
                            "--use-monthly-status-engine requires --strategy-root"
                        )
                    if not args.monthly_csv or not args.weekly_csv:
                        parser.error(
                            "--use-monthly-status-engine requires --monthly-csv and --weekly-csv"
                        )
                    if strategy_path is not None:
                        parser.error(
                            "Use --strategy-root instead of --strategy-path when --use-monthly-status-engine is enabled"
                        )
                elif strategy_path is None:
                    parser.error("--historical mode requires --strategy-path")
                if args.enable_option_chain_selection and not args.option_chain_csv:
                    parser.error(
                        "--enable-option-chain-selection requires --option-chain-csv"
                    )
                daily_bars = load_daily_bars_csv(Path(args.daily_csv))
                option_levels_series = load_option_levels_series_csv(
                    Path(args.option_levels_csv)
                )
                report = _build_historical_runner(eod_policy, cost_model).run(
                    strategy_path=strategy_path,
                    strategy_root=strategy_root,
                    use_monthly_status_engine=args.use_monthly_status_engine,
                    monthly_bars=(
                        load_monthly_bars_csv(Path(args.monthly_csv))
                        if args.monthly_csv
                        else None
                    ),
                    weekly_bars=(
                        load_weekly_bars_csv(Path(args.weekly_csv))
                        if args.weekly_csv
                        else None
                    ),
                    daily_bars=daily_bars,
                    option_levels_series=option_levels_series,
                    option_intraday_bars=(
                        load_intraday_option_bars_csv(Path(args.option_intraday_csv))
                        if args.option_intraday_csv
                        else None
                    ),
                    spot_intraday_bars=(
                        load_intraday_spot_bars_csv(Path(args.spot_intraday_csv))
                        if args.spot_intraday_csv
                        else None
                    ),
                    runtime_values_base={"ENTRY": 200.0},
                    lot_size=50,
                    trades_taken_today=1,
                    enable_s23_recalculation=args.enable_s23_recalculation,
                    option_chain_contracts=(
                        load_option_chain_csv(Path(args.option_chain_csv))
                        if args.option_chain_csv
                        else None
                    ),
                    enable_option_chain_selection=args.enable_option_chain_selection,
                )
                mode = "historical"
            else:
                if args.use_monthly_status_engine:
                    parser.error(
                        "--use-monthly-status-engine is supported only with --historical"
                    )
                if args.enable_s23_recalculation:
                    parser.error(
                        "--enable-s23-recalculation is supported only with --historical"
                    )
                if args.enable_option_chain_selection:
                    parser.error(
                        "--enable-option-chain-selection is supported only with --historical"
                    )
                if strategy_path is None:
                    parser.error("CSV snapshot mode requires --strategy-path")
                if args.option_intraday_csv:
                    parser.error(
                        "--option-intraday-csv is supported only with --historical"
                    )
                if args.spot_intraday_csv:
                    parser.error(
                        "--spot-intraday-csv is supported only with --historical"
                    )
                if args.option_chain_csv:
                    parser.error(
                        "--option-chain-csv is supported only with --historical"
                    )
                backtest_input = _csv_backtest_input(
                    strategy_path,
                    daily_csv=Path(args.daily_csv),
                    option_levels_csv=Path(args.option_levels_csv),
                )
                mode = "csv"
                report = None
        else:
            parser.error(
                "Provide either --sample or both --daily-csv and --option-levels-csv"
            )
        if mode == "historical":
            result = None
        else:
            result = _build_runner().run(backtest_input)
    except (ValueError, BacktestCsvError) as exc:
        print(f"Backtest refused: {exc}")
        return 1

    if mode == "historical":
        output = {
            "strategy_path": str(report.strategy_path) if report.strategy_path is not None else None,
            "strategy_root": str(report.strategy_root) if report.strategy_root is not None else None,
            "use_monthly_status_engine": report.use_monthly_status_engine,
            "mode": mode,
            "eod_policy": eod_policy.value,
            "cost_model": _to_jsonable(cost_model),
            "evaluations": _to_jsonable(report.evaluations),
            "metrics": _to_jsonable(report.metrics),
            "monthly_status_skips": _to_jsonable(list(report.monthly_status_skips)),
        }
        if report.enable_s23_recalculation:
            output["enable_s23_recalculation"] = True
        if report.enable_option_chain_selection:
            output["enable_option_chain_selection"] = True
    else:
        metrics = build_backtest_metrics([result])
        output = {
            "strategy_path": str(strategy_path),
            "mode": mode,
            "cost_model": _to_jsonable(cost_model),
            "validation": _to_jsonable(result.validation),
            "result": _to_jsonable(result),
            "metrics": _to_jsonable(metrics),
        }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Backtest report written to {out_path}")
    if args.markdown_out:
        markdown_path = Path(args.markdown_out)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            _render_backtest_markdown(output),
            encoding="utf-8",
        )
        print(f"Backtest markdown written to {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
