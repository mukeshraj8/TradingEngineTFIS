"""Offline backtesting helpers for TradingEngineTFIS."""

from .backtest_runner import BacktestRunner
from .cost_model import CostModel
from .csv_loader import (
    BacktestCsvError,
    OptionLevelsSnapshot,
    load_daily_bars_csv,
    load_intraday_option_bars_csv,
    load_option_levels_csv,
    load_option_levels_series_csv,
)
from .historical_runner import (
    HistoricalBacktestMetrics,
    HistoricalBacktestReport,
    HistoricalBacktestRunner,
    HistoricalCandidateResult,
    HistoricalMarketSnapshot,
)
from .metrics import build_backtest_metrics
from .models import BacktestInput, BacktestMetrics, BacktestTradeResult, BacktestValidation
from .parameter_sweep import (
    ParameterSweepRankingEntry,
    ParameterSweepReport,
    ParameterSweepRunner,
    ParameterSweepSummary,
    ParameterSweepTradeOutputs,
    ParameterSweepVariantResult,
    build_parameter_sweep_ranking,
    calculate_risk_reward_metrics,
    generate_parameter_combinations,
    render_parameter_sweep_markdown,
    sample_daily_bars,
    sample_runtime_values,
)
from .trade_lifecycle import EodExitPolicy, TradeLifecycleResult, TradeLifecycleSimulator

__all__ = [
    "BacktestInput",
    "BacktestCsvError",
    "BacktestMetrics",
    "BacktestRunner",
    "BacktestTradeResult",
    "BacktestValidation",
    "CostModel",
    "HistoricalBacktestMetrics",
    "HistoricalBacktestReport",
    "HistoricalBacktestRunner",
    "HistoricalCandidateResult",
    "HistoricalMarketSnapshot",
    "OptionLevelsSnapshot",
    "EodExitPolicy",
    "TradeLifecycleResult",
    "TradeLifecycleSimulator",
    "ParameterSweepReport",
    "ParameterSweepRankingEntry",
    "ParameterSweepRunner",
    "ParameterSweepSummary",
    "ParameterSweepTradeOutputs",
    "ParameterSweepVariantResult",
    "build_parameter_sweep_ranking",
    "build_backtest_metrics",
    "load_daily_bars_csv",
    "load_intraday_option_bars_csv",
    "load_option_levels_csv",
    "load_option_levels_series_csv",
    "calculate_risk_reward_metrics",
    "generate_parameter_combinations",
    "render_parameter_sweep_markdown",
    "sample_daily_bars",
    "sample_runtime_values",
]
