from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from tfis.backtest.backtest_runner import BacktestRunner
from tfis.backtest.cost_model import CostModel
from tfis.backtest.csv_loader import OptionLevelsSnapshot
from tfis.backtest.models import BacktestInput
from tfis.backtest.trade_lifecycle import (
    EodExitPolicy,
    TradeLifecycleResult,
    TradeLifecycleSimulator,
)
from tfis.importers import load_strategy_rule
from tfis.market_structure.ohlc import OhlcBar


@dataclass(frozen=True, slots=True)
class HistoricalMarketSnapshot:
    d2hh: float
    d2ll: float
    d3hh: float
    d3ll: float
    d4hh: float
    d4ll: float
    current_day_high: float
    current_day_low: float
    opt_levels: dict[str, float]


@dataclass(frozen=True, slots=True)
class HistoricalCandidateResult:
    timestamp: datetime
    strategy_code: str
    accepted: bool
    rejection_reason: str
    trade_outputs: dict[str, float | int]
    parameters: dict[str, float]
    validation: dict[str, object]
    market_snapshot: HistoricalMarketSnapshot
    lifecycle_result: TradeLifecycleResult | None


@dataclass(frozen=True, slots=True)
class HistoricalBacktestMetrics:
    total_evaluations: int
    accepted_candidates: int
    rejected_candidates: int
    rejection_reason_distribution: dict[str, int]
    entered_trades: int
    target_hits: int
    stoploss_hits: int
    no_entry: int
    no_exit: int
    eod_square_off: int
    carry_forward_pending: int
    total_pnl_points: float
    average_pnl_points: float
    total_gross_pnl_points: float
    total_cost_points: float
    total_net_pnl_points: float
    average_net_pnl_points: float
    total_gross_pnl_rupees: float
    total_cost_rupees: float
    total_net_pnl_rupees: float
    average_net_pnl_rupees: float
    final_net_pnl_rupees: float
    max_drawdown_rupees: float
    max_drawdown_points: float
    best_trade_net_rupees: float
    worst_trade_net_rupees: float
    average_mfe: float
    average_mae: float
    win_rate: float
    loss_rate: float
    no_entry_rate: float
    no_exit_rate: float


@dataclass(frozen=True, slots=True)
class HistoricalBacktestReport:
    strategy_path: Path
    evaluations: list[HistoricalCandidateResult]
    metrics: HistoricalBacktestMetrics


@dataclass(frozen=True, slots=True)
class RealizedEquityCurveSummary:
    evaluations: list[HistoricalCandidateResult]
    max_drawdown_rupees: float
    max_drawdown_points: float
    best_trade_net_rupees: float
    worst_trade_net_rupees: float


def build_realized_equity_curve(
    evaluations: list[HistoricalCandidateResult],
) -> RealizedEquityCurveSummary:
    updated_evaluations = list(evaluations)
    cumulative_net_pnl_rupees = 0.0
    cumulative_net_pnl_points = 0.0
    running_peak_rupees = 0.0
    running_peak_points = 0.0
    max_drawdown_rupees = 0.0
    max_drawdown_points = 0.0
    best_trade_net_rupees: float | None = None
    worst_trade_net_rupees: float | None = None

    for index, evaluation in enumerate(updated_evaluations):
        lifecycle = evaluation.lifecycle_result
        if lifecycle is None or lifecycle.net_pnl_rupees is None or lifecycle.net_pnl_points is None:
            continue

        cumulative_net_pnl_rupees += float(lifecycle.net_pnl_rupees)
        cumulative_net_pnl_points += float(lifecycle.net_pnl_points)
        running_peak_rupees = max(running_peak_rupees, cumulative_net_pnl_rupees)
        running_peak_points = max(running_peak_points, cumulative_net_pnl_points)
        drawdown_rupees = running_peak_rupees - cumulative_net_pnl_rupees
        drawdown_points = running_peak_points - cumulative_net_pnl_points
        max_drawdown_rupees = max(max_drawdown_rupees, drawdown_rupees)
        max_drawdown_points = max(max_drawdown_points, drawdown_points)
        best_trade_net_rupees = (
            float(lifecycle.net_pnl_rupees)
            if best_trade_net_rupees is None
            else max(best_trade_net_rupees, float(lifecycle.net_pnl_rupees))
        )
        worst_trade_net_rupees = (
            float(lifecycle.net_pnl_rupees)
            if worst_trade_net_rupees is None
            else min(worst_trade_net_rupees, float(lifecycle.net_pnl_rupees))
        )
        updated_evaluations[index] = replace(
            evaluation,
            lifecycle_result=replace(
                lifecycle,
                cumulative_net_pnl_rupees=float(cumulative_net_pnl_rupees),
                drawdown_rupees=float(drawdown_rupees),
            ),
        )

    return RealizedEquityCurveSummary(
        evaluations=updated_evaluations,
        max_drawdown_rupees=float(max_drawdown_rupees),
        max_drawdown_points=float(max_drawdown_points),
        best_trade_net_rupees=float(best_trade_net_rupees or 0.0),
        worst_trade_net_rupees=float(worst_trade_net_rupees or 0.0),
    )


class HistoricalBacktestRunner:
    def __init__(
        self,
        backtest_runner: BacktestRunner,
        eod_policy: EodExitPolicy = EodExitPolicy.MARK_NO_EXIT,
        cost_model: CostModel | None = None,
        lifecycle_simulator: TradeLifecycleSimulator | None = None,
    ) -> None:
        self._backtest_runner = backtest_runner
        self._cost_model = cost_model or CostModel()
        self._lifecycle_simulator = lifecycle_simulator or TradeLifecycleSimulator(
            eod_policy=eod_policy
        )

    def run(
        self,
        *,
        strategy_path: str | Path,
        daily_bars: list[OhlcBar],
        option_levels_series: list[OptionLevelsSnapshot],
        option_intraday_bars: list[OhlcBar] | None = None,
        runtime_values_base: dict[str, object] | None = None,
        lot_size: int = 50,
        trades_taken_today: int = 1,
    ) -> HistoricalBacktestReport:
        rule = load_strategy_rule(strategy_path)
        sorted_daily = sorted(daily_bars, key=lambda bar: bar.timestamp)
        sorted_option_levels = sorted(
            option_levels_series,
            key=lambda snapshot: snapshot.timestamp,
        )
        option_levels_by_timestamp = {
            snapshot.timestamp: snapshot.opt_levels for snapshot in sorted_option_levels
        }
        intraday_by_date: dict[date, list[OhlcBar]] = {}
        for bar in sorted(option_intraday_bars or [], key=lambda item: item.timestamp):
            intraday_by_date.setdefault(bar.timestamp.date(), []).append(bar)

        evaluations: list[HistoricalCandidateResult] = []
        for index in range(len(sorted_daily)):
            window = sorted_daily[: index + 1]
            if len(window) < 5:
                continue

            current_bar = window[-1]
            opt_levels = option_levels_by_timestamp.get(current_bar.timestamp)
            if opt_levels is None:
                raise ValueError(
                    f"No option levels found for timestamp {current_bar.timestamp.isoformat()}"
                )

            runtime_values = dict(runtime_values_base or {})
            runtime_values["OPT_LEVELS"] = dict(opt_levels)
            effective_parameters = dict(rule.parameters)
            runtime_parameters = runtime_values.get("PARAMS")
            if isinstance(runtime_parameters, dict):
                for key, value in runtime_parameters.items():
                    effective_parameters[str(key)] = float(value)

            market_levels = self._backtest_runner.structure_calculator.build_market_levels(
                window,
                intraday_bars=None,
            )
            result = self._backtest_runner.run(
                BacktestInput(
                    strategy_path=Path(strategy_path),
                    daily_bars=window,
                    intraday_bars=None,
                    runtime_values=runtime_values,
                    lot_size=lot_size,
                    trades_taken_today=trades_taken_today,
                )
            )
            lifecycle_result = None
            if option_intraday_bars is not None and result.accepted:
                lifecycle_result = self._lifecycle_simulator.simulate(
                    result.trade_plan,
                    intraday_by_date.get(current_bar.timestamp.date(), []),
                )
                lifecycle_result = self._cost_model.apply_with_quantity(
                    lifecycle_result,
                    quantity=result.order_intent.quantity,
                )
            evaluations.append(
                HistoricalCandidateResult(
                    timestamp=current_bar.timestamp,
                    strategy_code=result.strategy_code,
                    accepted=result.accepted,
                    rejection_reason=result.reason,
                    trade_outputs={
                        "start_strike": result.trade_plan.start_strike,
                        "entry_price": result.trade_plan.entry_price,
                        "target_price": result.trade_plan.target_price,
                        "stoploss_price": result.trade_plan.stoploss_price,
                        "ideal_premium": result.trade_plan.ideal_premium,
                        "minimum_premium": result.trade_plan.minimum_premium,
                    },
                    parameters=effective_parameters,
                    validation={
                        "strategy_config_ok": result.validation.strategy_config_ok,
                        "formula_safety_findings": [
                            {
                                "severity": finding.severity,
                                "field_name": finding.field_name,
                                "message": finding.message,
                                "formula": finding.formula,
                            }
                            for finding in result.validation.formula_safety_findings
                        ],
                    },
                    market_snapshot=HistoricalMarketSnapshot(
                        d2hh=market_levels.d2hh,
                        d2ll=market_levels.d2ll,
                        d3hh=market_levels.d3hh,
                        d3ll=market_levels.d3ll,
                        d4hh=market_levels.d4hh,
                        d4ll=market_levels.d4ll,
                        current_day_high=market_levels.current_day_high,
                        current_day_low=market_levels.current_day_low,
                        opt_levels=dict(opt_levels),
                    ),
                    lifecycle_result=lifecycle_result,
                )
            )

        equity_curve = build_realized_equity_curve(evaluations)
        evaluations = equity_curve.evaluations

        rejection_reason_distribution: dict[str, int] = {}
        accepted_candidates = 0
        rejected_candidates = 0
        entered_trades = 0
        target_hits = 0
        stoploss_hits = 0
        no_entry = 0
        no_exit = 0
        eod_square_off = 0
        carry_forward_pending = 0
        total_pnl_points = 0.0
        total_cost_points = 0.0
        total_net_pnl_points = 0.0
        total_gross_pnl_rupees = 0.0
        total_cost_rupees = 0.0
        total_net_pnl_rupees = 0.0
        total_mfe = 0.0
        total_mae = 0.0
        closed_trades = 0
        winning_trades = 0
        losing_trades = 0
        for evaluation in evaluations:
            if evaluation.accepted:
                accepted_candidates += 1
            else:
                rejected_candidates += 1
                reason = evaluation.rejection_reason
                rejection_reason_distribution[reason] = (
                    rejection_reason_distribution.get(reason, 0) + 1
                )

            lifecycle = evaluation.lifecycle_result
            if lifecycle is None:
                continue
            if lifecycle.entered:
                entered_trades += 1
                if lifecycle.max_favorable_excursion is not None:
                    total_mfe += lifecycle.max_favorable_excursion
                if lifecycle.max_adverse_excursion is not None:
                    total_mae += lifecycle.max_adverse_excursion
            if lifecycle.exit_reason == "TARGET_HIT":
                target_hits += 1
                closed_trades += 1
                total_pnl_points += float(lifecycle.pnl_points)
                total_cost_points += float(lifecycle.total_cost_points)
                total_net_pnl_points += float(lifecycle.net_pnl_points)
                total_gross_pnl_rupees += float(lifecycle.gross_pnl_rupees)
                total_cost_rupees += float(lifecycle.cost_rupees)
                total_net_pnl_rupees += float(lifecycle.net_pnl_rupees)
                winning_trades += 1
            elif lifecycle.exit_reason == "STOPLOSS_HIT":
                stoploss_hits += 1
                closed_trades += 1
                total_pnl_points += float(lifecycle.pnl_points)
                total_cost_points += float(lifecycle.total_cost_points)
                total_net_pnl_points += float(lifecycle.net_pnl_points)
                total_gross_pnl_rupees += float(lifecycle.gross_pnl_rupees)
                total_cost_rupees += float(lifecycle.cost_rupees)
                total_net_pnl_rupees += float(lifecycle.net_pnl_rupees)
                losing_trades += 1
            elif lifecycle.exit_reason == "NO_ENTRY":
                no_entry += 1
            elif lifecycle.exit_reason == "NO_EXIT":
                no_exit += 1
            elif lifecycle.exit_reason == "EOD_SQUARE_OFF":
                eod_square_off += 1
                closed_trades += 1
                total_pnl_points += float(lifecycle.pnl_points)
                total_cost_points += float(lifecycle.total_cost_points)
                total_net_pnl_points += float(lifecycle.net_pnl_points)
                total_gross_pnl_rupees += float(lifecycle.gross_pnl_rupees)
                total_cost_rupees += float(lifecycle.cost_rupees)
                total_net_pnl_rupees += float(lifecycle.net_pnl_rupees)
                if float(lifecycle.pnl_points) > 0:
                    winning_trades += 1
                elif float(lifecycle.pnl_points) < 0:
                    losing_trades += 1
            elif lifecycle.exit_reason == "CARRY_FORWARD_PENDING":
                carry_forward_pending += 1

        average_pnl_points = (
            total_pnl_points / closed_trades if closed_trades else 0.0
        )
        average_net_pnl_points = (
            total_net_pnl_points / closed_trades if closed_trades else 0.0
        )
        average_net_pnl_rupees = (
            total_net_pnl_rupees / closed_trades if closed_trades else 0.0
        )
        average_mfe = total_mfe / entered_trades if entered_trades else 0.0
        average_mae = total_mae / entered_trades if entered_trades else 0.0
        win_rate = winning_trades / closed_trades if closed_trades else 0.0
        loss_rate = losing_trades / closed_trades if closed_trades else 0.0
        no_entry_rate = no_entry / len(evaluations) if evaluations else 0.0
        no_exit_rate = no_exit / entered_trades if entered_trades else 0.0

        return HistoricalBacktestReport(
            strategy_path=Path(strategy_path),
            evaluations=evaluations,
            metrics=HistoricalBacktestMetrics(
                total_evaluations=len(evaluations),
                accepted_candidates=accepted_candidates,
                rejected_candidates=rejected_candidates,
                rejection_reason_distribution=rejection_reason_distribution,
                entered_trades=entered_trades,
                target_hits=target_hits,
                stoploss_hits=stoploss_hits,
                no_entry=no_entry,
                no_exit=no_exit,
                eod_square_off=eod_square_off,
                carry_forward_pending=carry_forward_pending,
                total_pnl_points=float(total_pnl_points),
                average_pnl_points=float(average_pnl_points),
                total_gross_pnl_points=float(total_pnl_points),
                total_cost_points=float(total_cost_points),
                total_net_pnl_points=float(total_net_pnl_points),
                average_net_pnl_points=float(average_net_pnl_points),
                total_gross_pnl_rupees=float(total_gross_pnl_rupees),
                total_cost_rupees=float(total_cost_rupees),
                total_net_pnl_rupees=float(total_net_pnl_rupees),
                average_net_pnl_rupees=float(average_net_pnl_rupees),
                final_net_pnl_rupees=float(total_net_pnl_rupees),
                max_drawdown_rupees=equity_curve.max_drawdown_rupees,
                max_drawdown_points=equity_curve.max_drawdown_points,
                best_trade_net_rupees=equity_curve.best_trade_net_rupees,
                worst_trade_net_rupees=equity_curve.worst_trade_net_rupees,
                average_mfe=float(average_mfe),
                average_mae=float(average_mae),
                win_rate=float(win_rate),
                loss_rate=float(loss_rate),
                no_entry_rate=float(no_entry_rate),
                no_exit_rate=float(no_exit_rate),
            ),
        )
