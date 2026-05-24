"""Offline backtesting helpers for TradingEngineTFIS."""

from .backtest_runner import BacktestRunner
from .cost_model import CostModel
from .csv_loader import (
    BacktestCsvError,
    OptionLevelsSnapshot,
    load_daily_bars_csv,
    load_intraday_option_bars_csv,
    load_intraday_spot_bars_csv,
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
from .entry_missed import EntryMissedInput, EntryMissedResult, S23EntryMissedDetector
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
from .recalculation import (
    IntradaySnapshot,
    RecalculationInput,
    RecalculationResult,
    S23RecalculationEngine,
)
from .trade_lifecycle import EodExitPolicy, TradeLifecycleResult, TradeLifecycleSimulator
from .monthly_status_context import (
    HistoricalMonthlyStatusContext,
    HistoricalMonthlyStatusSkip,
    MonthlyStatusContextComputation,
    build_monthly_status_context,
    load_monthly_bars_csv,
    load_weekly_bars_csv,
)
from .option_chain import (
    OptionChainContract,
    OptionChainSelector,
    OptionSelectionRequest,
    OptionSelectionResult,
    load_option_chain_csv,
)

__all__ = [
    "BacktestInput",
    "BacktestCsvError",
    "BacktestMetrics",
    "BacktestRunner",
    "BacktestTradeResult",
    "BacktestValidation",
    "CostModel",
    "EntryMissedInput",
    "EntryMissedResult",
    "HistoricalBacktestMetrics",
    "HistoricalBacktestReport",
    "HistoricalBacktestRunner",
    "HistoricalCandidateResult",
    "HistoricalMarketSnapshot",
    "HistoricalMonthlyStatusContext",
    "HistoricalMonthlyStatusSkip",
    "IntradaySnapshot",
    "MonthlyStatusContextComputation",
    "OptionChainContract",
    "OptionChainSelector",
    "OptionLevelsSnapshot",
    "OptionSelectionRequest",
    "OptionSelectionResult",
    "EodExitPolicy",
    "S23EntryMissedDetector",
    "TradeLifecycleResult",
    "TradeLifecycleSimulator",
    "ParameterSweepReport",
    "ParameterSweepRankingEntry",
    "ParameterSweepRunner",
    "ParameterSweepSummary",
    "ParameterSweepTradeOutputs",
    "ParameterSweepVariantResult",
    "RecalculationInput",
    "RecalculationResult",
    "S23RecalculationEngine",
    "build_parameter_sweep_ranking",
    "build_backtest_metrics",
    "build_monthly_status_context",
    "load_daily_bars_csv",
    "load_intraday_option_bars_csv",
    "load_intraday_spot_bars_csv",
    "load_monthly_bars_csv",
    "load_option_levels_csv",
    "load_option_levels_series_csv",
    "load_option_chain_csv",
    "load_weekly_bars_csv",
    "calculate_risk_reward_metrics",
    "generate_parameter_combinations",
    "render_parameter_sweep_markdown",
    "sample_daily_bars",
    "sample_runtime_values",
]
