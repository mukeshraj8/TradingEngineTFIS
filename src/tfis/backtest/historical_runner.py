from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from tfis.backtest.backtest_runner import BacktestRunner
from tfis.backtest.cost_model import CostModel
from tfis.backtest.csv_loader import OptionLevelsSnapshot
from tfis.backtest.entry_missed import EntryMissedInput, S23EntryMissedDetector
from tfis.backtest.monthly_status_context import (
    HistoricalMonthlyStatusSkip,
    build_monthly_status_context,
)
from tfis.backtest.models import BacktestInput
from tfis.backtest.option_chain import (
    OptionChainContract,
    OptionChainSelector,
    OptionSelectionRequest,
    OptionSelectionResult,
)
from tfis.backtest.recalculation import (
    IntradaySnapshot,
    RecalculationInput,
    S23RecalculationEngine,
)
from tfis.backtest.trade_lifecycle import (
    EodExitPolicy,
    TradeLifecycleResult,
    TradeLifecycleSimulator,
)
from tfis.domain.strategy_rule import StrategyRule
from tfis.importers import load_strategy_rule
from tfis.market_structure.ohlc import OhlcBar


PROJECT_ROOT = Path(__file__).resolve().parents[3]
IMPORTER_OPEN_QUESTIONS_PATH = PROJECT_ROOT / "config" / "importer_open_questions.yaml"
S23_RECALC_ORPT_TIME = time(9, 24, 59)
S23_RECALC_RC_TIME = time(9, 29, 59)
S23_RECALC_SUPPORTED_UNIQUE_CODES = {
    "NIFTY_OP_SELL_WK_DIFF_2D_3D",
    "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
    "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
}
S23_RECALC_OPEN_QUESTION_IDS = {
    "s23_put_recalc_strike_ll_vs_high",
}


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
    monthly_status: str | None = None
    monthly_status_trigger: str | None = None
    reversal_dominated: bool | None = None
    selected_branch_unique_codes: tuple[str, ...] = ()
    monthly_status_candidates: tuple[dict[str, object], ...] = ()


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
    strategy_path: Path | None
    evaluations: list[HistoricalCandidateResult]
    metrics: HistoricalBacktestMetrics
    strategy_root: Path | None = None
    use_monthly_status_engine: bool = False
    enable_s23_recalculation: bool = False
    enable_option_chain_selection: bool = False
    monthly_status_skips: tuple[HistoricalMonthlyStatusSkip, ...] = ()


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
        self._entry_missed_detector = S23EntryMissedDetector()
        self._recalculation_engine = S23RecalculationEngine()
        self._option_chain_selector = OptionChainSelector()

    def run(
        self,
        *,
        strategy_path: str | Path | None = None,
        strategy_root: str | Path | None = None,
        use_monthly_status_engine: bool = False,
        monthly_bars: list[OhlcBar] | None = None,
        weekly_bars: list[OhlcBar] | None = None,
        daily_bars: list[OhlcBar],
        option_levels_series: list[OptionLevelsSnapshot],
        option_intraday_bars: list[OhlcBar] | None = None,
        spot_intraday_bars: list[OhlcBar] | None = None,
        option_chain_contracts: list[OptionChainContract] | None = None,
        runtime_values_base: dict[str, object] | None = None,
        lot_size: int = 50,
        trades_taken_today: int = 1,
        enable_s23_recalculation: bool = False,
        enable_option_chain_selection: bool = False,
    ) -> HistoricalBacktestReport:
        if use_monthly_status_engine:
            if strategy_root is None:
                raise ValueError(
                    "Historical monthly-status mode requires strategy_root"
                )
            if monthly_bars is None or weekly_bars is None:
                raise ValueError(
                    "Historical monthly-status mode requires monthly_bars and weekly_bars"
                )
            strategy_root_path = Path(strategy_root)
            instrument_group = strategy_root_path.name.lower()
            rule = None
        else:
            if strategy_path is None:
                raise ValueError("Historical backtest requires strategy_path")
            rule = load_strategy_rule(strategy_path)
            strategy_root_path = None
            instrument_group = None
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
        spot_intraday_by_date: dict[date, list[OhlcBar]] = {}
        for bar in sorted(spot_intraday_bars or [], key=lambda item: item.timestamp):
            spot_intraday_by_date.setdefault(bar.timestamp.date(), []).append(bar)

        evaluations: list[HistoricalCandidateResult] = []
        monthly_status_skips: list[HistoricalMonthlyStatusSkip] = []
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
            market_levels = self._backtest_runner.structure_calculator.build_market_levels(
                window,
                intraday_bars=None,
            )
            if use_monthly_status_engine:
                monthly_status_context = build_monthly_status_context(
                    instrument_group=instrument_group,
                    current_timestamp=current_bar.timestamp,
                    monthly_bars=monthly_bars,
                    weekly_bars=weekly_bars,
                    strategy_root=strategy_root_path,
                )
                if monthly_status_context.skip is not None:
                    monthly_status_skips.append(monthly_status_context.skip)
                    continue
                context = monthly_status_context.context
                assert context is not None
                selected_rule_entries = self._select_rules_for_monthly_status(
                    strategy_root_path,
                    context.selected_branch_unique_codes,
                )
                if not selected_rule_entries:
                    monthly_status_skips.append(
                        HistoricalMonthlyStatusSkip(
                            timestamp=current_bar.timestamp,
                            reason=(
                                "no eligible strategy branches for monthly status "
                                f"{context.status_result.status.value}"
                            ),
                        )
                    )
                    continue
                for selected_strategy_path, selected_rule in selected_rule_entries:
                    evaluations.append(
                        self._evaluate_strategy_step(
                            strategy_path=selected_strategy_path,
                            rule=selected_rule,
                            window=window,
                            runtime_values=runtime_values,
                            lot_size=lot_size,
                            trades_taken_today=trades_taken_today,
                            opt_levels=opt_levels,
                            intraday_bars=intraday_by_date.get(
                                current_bar.timestamp.date(),
                                [],
                            ),
                            spot_intraday_bars=spot_intraday_by_date.get(
                                current_bar.timestamp.date(),
                                [],
                            ),
                            option_chain_contracts=option_chain_contracts or [],
                            market_levels=market_levels,
                            enable_s23_recalculation=enable_s23_recalculation,
                            enable_option_chain_selection=enable_option_chain_selection,
                            monthly_status=context.status_result.status.value,
                            monthly_status_trigger=context.status_result.trigger_name,
                            reversal_dominated=context.status_result.reversal_dominated,
                            selected_branch_unique_codes=context.selected_branch_unique_codes,
                            monthly_status_candidates=tuple(
                                {
                                    "candidate_status": candidate.candidate_status.value,
                                    "trigger_name": candidate.trigger_name,
                                    "threshold_value": candidate.threshold_value,
                                    "condition_met": candidate.condition_met,
                                    "confidence": candidate.confidence,
                                    "notes": candidate.notes,
                                }
                                for candidate in context.status_result.candidates
                            ),
                        )
                    )
            else:
                assert strategy_path is not None
                evaluations.append(
                    self._evaluate_strategy_step(
                        strategy_path=Path(strategy_path),
                        rule=rule,
                        window=window,
                        runtime_values=runtime_values,
                        lot_size=lot_size,
                        trades_taken_today=trades_taken_today,
                        opt_levels=opt_levels,
                        intraday_bars=intraday_by_date.get(
                            current_bar.timestamp.date(),
                            [],
                        ),
                        spot_intraday_bars=spot_intraday_by_date.get(
                            current_bar.timestamp.date(),
                            [],
                        ),
                        option_chain_contracts=option_chain_contracts or [],
                        market_levels=market_levels,
                        enable_s23_recalculation=enable_s23_recalculation,
                        enable_option_chain_selection=enable_option_chain_selection,
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
            strategy_path=Path(strategy_path) if strategy_path is not None else None,
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
            strategy_root=strategy_root_path,
            use_monthly_status_engine=use_monthly_status_engine,
            enable_s23_recalculation=enable_s23_recalculation,
            enable_option_chain_selection=enable_option_chain_selection,
            monthly_status_skips=tuple(monthly_status_skips),
        )

    def _evaluate_strategy_step(
        self,
        *,
        strategy_path: Path,
        rule: StrategyRule,
        window: list[OhlcBar],
        runtime_values: dict[str, object],
        lot_size: int,
        trades_taken_today: int,
        opt_levels: dict[str, float],
        intraday_bars: list[OhlcBar],
        spot_intraday_bars: list[OhlcBar],
        option_chain_contracts: list[OptionChainContract],
        market_levels,
        enable_s23_recalculation: bool = False,
        enable_option_chain_selection: bool = False,
        monthly_status: str | None = None,
        monthly_status_trigger: str | None = None,
        reversal_dominated: bool | None = None,
        selected_branch_unique_codes: list[str] | None = None,
        monthly_status_candidates: tuple[dict[str, object], ...] = (),
    ) -> HistoricalCandidateResult:
        effective_parameters = dict(rule.parameters)
        runtime_parameters = runtime_values.get("PARAMS")
        if isinstance(runtime_parameters, dict):
            for key, value in runtime_parameters.items():
                effective_parameters[str(key)] = float(value)

        result = self._backtest_runner.run(
            BacktestInput(
                strategy_path=strategy_path,
                daily_bars=window,
                intraday_bars=None,
                runtime_values=runtime_values,
                lot_size=lot_size,
                trades_taken_today=trades_taken_today,
            )
        )
        effective_trade_plan = result.trade_plan
        lifecycle_intraday_bars = intraday_bars
        recalculation_audit: dict[str, object] | None = None
        option_chain_audit: dict[str, object] | None = None
        if enable_s23_recalculation:
            (
                effective_trade_plan,
                lifecycle_intraday_bars,
                recalculation_audit,
            ) = self._apply_s23_recalculation_if_needed(
                rule=rule,
                base_trade_plan=result.trade_plan,
                market_levels=market_levels,
                option_levels=opt_levels,
                intraday_bars=intraday_bars,
                spot_intraday_bars=spot_intraday_bars,
                monthly_status=monthly_status,
            )
        accepted = result.accepted
        rejection_reason = result.reason
        if enable_option_chain_selection:
            if (
                rule.option_type is None
                or effective_trade_plan.start_strike is None
                or effective_trade_plan.end_strike is None
                or effective_trade_plan.ideal_premium is None
                or effective_trade_plan.minimum_premium is None
            ):
                selection_result = OptionSelectionResult(
                    selected=False,
                    selected_contract=None,
                    selection_reason=(
                        "Option-chain selection requires option_type, strike range, "
                        "ideal premium, and minimum premium."
                    ),
                    candidate_count=0,
                )
            else:
                selection_result = self._option_chain_selector.select(
                    OptionSelectionRequest(
                        option_type=rule.option_type,
                        start_strike=effective_trade_plan.start_strike,
                        end_strike=effective_trade_plan.end_strike,
                        ideal_premium=effective_trade_plan.ideal_premium,
                        minimum_premium=effective_trade_plan.minimum_premium,
                        minimum_oi=rule.minimum_oi,
                        timestamp=window[-1].timestamp,
                    ),
                    option_chain_contracts,
                )
            option_chain_audit = self._option_selection_result_to_dict(selection_result)
            option_chain_audit["notes"] = [
                "Selected contract metadata is reported for audit and contract realism review.",
                "Lifecycle simulation still uses the generic intraday option series and does not yet switch to contract-specific intraday prices.",
            ]
            if accepted and not selection_result.selected:
                accepted = False
                rejection_reason = (
                    "Rejected: option-chain selection failed - "
                    f"{selection_result.selection_reason}"
                )
        lifecycle_result = None
        if lifecycle_intraday_bars and accepted:
            lifecycle_result = self._lifecycle_simulator.simulate(
                effective_trade_plan,
                lifecycle_intraday_bars,
            )
            lifecycle_result = self._cost_model.apply_with_quantity(
                lifecycle_result,
                quantity=result.order_intent.quantity,
            )

        current_bar = window[-1]
        return HistoricalCandidateResult(
            timestamp=current_bar.timestamp,
            strategy_code=result.strategy_code,
            accepted=accepted,
            rejection_reason=rejection_reason,
            trade_outputs={
                "start_strike": effective_trade_plan.start_strike,
                "entry_price": effective_trade_plan.entry_price,
                "target_price": effective_trade_plan.target_price,
                "stoploss_price": effective_trade_plan.stoploss_price,
                "ideal_premium": effective_trade_plan.ideal_premium,
                "minimum_premium": effective_trade_plan.minimum_premium,
            },
            parameters=effective_parameters,
            validation=self._build_validation_payload(
                result,
                recalculation_audit,
                option_chain_audit,
            ),
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
            monthly_status=monthly_status,
            monthly_status_trigger=monthly_status_trigger,
            reversal_dominated=reversal_dominated,
            selected_branch_unique_codes=tuple(selected_branch_unique_codes or ()),
            monthly_status_candidates=monthly_status_candidates,
        )

    def _build_validation_payload(
        self,
        result,
        recalculation_audit: dict[str, object] | None,
        option_chain_audit: dict[str, object] | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
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
        }
        if recalculation_audit is not None:
            payload["s23_recalculation"] = recalculation_audit
        if option_chain_audit is not None:
            payload["option_chain_selection"] = option_chain_audit
        return payload

    def _apply_s23_recalculation_if_needed(
        self,
        *,
        rule: StrategyRule,
        base_trade_plan,
        market_levels,
        option_levels: dict[str, float],
        intraday_bars: list[OhlcBar],
        spot_intraday_bars: list[OhlcBar],
        monthly_status: str | None,
    ) -> tuple[object, list[OhlcBar], dict[str, object]]:
        base_audit: dict[str, object] = {
            "enabled": True,
            "branch_unique_code": rule.unique_code,
            "recalculation_applied": False,
            "entry_missed": None,
            "base_trade_plan": self._trade_plan_to_dict(base_trade_plan),
            "recalculated_trade_plan": None,
            "entry_missed_result": None,
            "recalculation_result": None,
            "unresolved_open_questions": [],
            "resolved_workbook_corrections": [],
        }

        if rule.unique_code not in S23_RECALC_SUPPORTED_UNIQUE_CODES:
            base_audit["warning"] = (
                "S23 recalculation is supported only for canonical S23 branch folders."
            )
            return base_trade_plan, intraday_bars, base_audit

        orpt_snapshot, spot_snapshot_source = self._find_intraday_snapshot_at_or_before(
            option_intraday_bars=intraday_bars,
            spot_intraday_bars=spot_intraday_bars,
            cutoff=S23_RECALC_ORPT_TIME,
            market_levels=market_levels,
        )
        if orpt_snapshot is None:
            base_audit["warning"] = (
                "Missing ORPT snapshot at or before 09:24:59; base trade plan kept."
            )
            return base_trade_plan, intraday_bars, base_audit

        entry_missed_result = self._entry_missed_detector.detect(
            EntryMissedInput(
                option_type=rule.option_type,
                entry_price=base_trade_plan.entry_price,
                orpt_snapshot=orpt_snapshot,
            )
        )
        base_audit["entry_missed"] = entry_missed_result.entry_missed
        base_audit["entry_missed_result"] = self._entry_missed_result_to_dict(
            entry_missed_result
        )
        base_audit["spot_snapshot_source"] = spot_snapshot_source
        base_audit["orpt_snapshot"] = self._snapshot_to_dict(orpt_snapshot)
        base_audit["notes"] = [
            "Option ORPT and recalculation snapshots come from the intraday option bar series.",
            (
                "Spot ORPT and recalculation low/high come from the provided spot intraday series."
                if spot_snapshot_source == "spot_intraday_csv"
                else "Spot ORPT and recalculation low/high fall back to current-day low/high from market levels because no dedicated spot intraday series was provided."
            ),
            "Risk approval and order intent remain based on the base trade plan; recalculation currently affects only the effective lifecycle simulation plan.",
        ]

        if not entry_missed_result.entry_missed:
            return base_trade_plan, intraday_bars, base_audit

        rc_snapshot, rc_spot_snapshot_source = self._find_intraday_snapshot_at_or_before(
            option_intraday_bars=intraday_bars,
            spot_intraday_bars=spot_intraday_bars,
            cutoff=S23_RECALC_RC_TIME,
            market_levels=market_levels,
        )
        if rc_snapshot is None:
            base_audit["warning"] = (
                "Missing recalculation snapshot at or before 09:29:59 after entry-missed detection; base trade plan kept."
            )
            return base_trade_plan, intraday_bars, base_audit
        base_audit["recalculation_snapshot"] = self._snapshot_to_dict(rc_snapshot)
        base_audit["recalculation_spot_snapshot_source"] = rc_spot_snapshot_source

        recalculation_result = self._recalculation_engine.recalculate(
            RecalculationInput(
                branch_unique_code=rule.unique_code,
                option_type=rule.option_type,
                monthly_status=self._resolve_monthly_status_for_recalculation(
                    monthly_status
                ),
                base_trade_plan=base_trade_plan,
                market_levels=market_levels,
                option_levels=option_levels,
                intraday_snapshot_at_orpt=orpt_snapshot,
                intraday_snapshot_at_recalc=rc_snapshot,
                entry_missed=True,
            )
        )
        recalculated_trade_plan = replace(
            base_trade_plan,
            start_strike=recalculation_result.recalculated_start_strike,
            end_strike=recalculation_result.recalculated_end_strike,
            ideal_premium=recalculation_result.recalculated_ideal_premium,
            minimum_premium=recalculation_result.recalculated_minimum_premium,
            entry_price=(
                recalculation_result.recalculated_entry_price
                if recalculation_result.recalculated_entry_price is not None
                else base_trade_plan.entry_price
            ),
        )
        base_audit["recalculation_applied"] = bool(recalculation_result.recalculated)
        base_audit["recalculated_trade_plan"] = self._trade_plan_to_dict(
            recalculated_trade_plan
        )
        base_audit["recalculation_result"] = self._recalculation_result_to_dict(
            recalculation_result
        )
        base_audit["unresolved_open_questions"] = self._recalculation_open_questions(
            rule.unique_code
        )
        base_audit["resolved_workbook_corrections"] = (
            self._recalculation_resolved_corrections(rule.unique_code)
        )
        base_audit["effective_lifecycle_start_after"] = rc_snapshot.timestamp.isoformat()
        lifecycle_intraday_bars = [
            bar for bar in intraday_bars if bar.timestamp > rc_snapshot.timestamp
        ]
        return recalculated_trade_plan, lifecycle_intraday_bars, base_audit

    def _find_intraday_snapshot_at_or_before(
        self,
        option_intraday_bars: list[OhlcBar],
        *,
        spot_intraday_bars: list[OhlcBar],
        cutoff: time,
        market_levels,
    ) -> tuple[IntradaySnapshot | None, str]:
        option_eligible = [
            bar
            for bar in sorted(option_intraday_bars, key=lambda item: item.timestamp)
            if bar.timestamp.time() <= cutoff
        ]
        if not option_eligible:
            return None, "missing_option_intraday_snapshot"
        option_bar = option_eligible[-1]
        spot_eligible = [
            bar
            for bar in sorted(spot_intraday_bars, key=lambda item: item.timestamp)
            if bar.timestamp.time() <= cutoff
        ]
        if spot_eligible:
            spot_bar = spot_eligible[-1]
            spot_low = spot_bar.low
            spot_high = spot_bar.high
            spot_snapshot_source = "spot_intraday_csv"
        else:
            spot_low = market_levels.current_day_low
            spot_high = market_levels.current_day_high
            spot_snapshot_source = "current_day_low_high_fallback_from_market_levels"
        return (
            IntradaySnapshot(
                timestamp=option_bar.timestamp,
                spot_low=spot_low,
                spot_high=spot_high,
                option_low=option_bar.low,
                option_high=option_bar.high,
            ),
            spot_snapshot_source,
        )

    def _resolve_monthly_status_for_recalculation(self, monthly_status: str | None):
        from tfis.domain.enums import MonthlyStatus

        if monthly_status is None:
            return MonthlyStatus.UNKNOWN
        return MonthlyStatus(monthly_status)

    def _trade_plan_to_dict(self, trade_plan) -> dict[str, object]:
        return {
            "strategy_code": trade_plan.strategy_code,
            "symbol": trade_plan.symbol,
            "option_type": (
                trade_plan.option_type.value if trade_plan.option_type is not None else None
            ),
            "start_strike": trade_plan.start_strike,
            "end_strike": trade_plan.end_strike,
            "ideal_premium": trade_plan.ideal_premium,
            "minimum_premium": trade_plan.minimum_premium,
            "entry_price": trade_plan.entry_price,
            "stoploss_price": trade_plan.stoploss_price,
            "target_price": trade_plan.target_price,
        }

    def _entry_missed_result_to_dict(self, result) -> dict[str, object]:
        return {
            "entry_missed": result.entry_missed,
            "rule_name": result.rule_name,
            "compared_value": result.compared_value,
            "threshold_entry_price": result.threshold_entry_price,
            "notes": list(result.notes),
        }

    def _snapshot_to_dict(self, snapshot: IntradaySnapshot) -> dict[str, object]:
        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "spot_low": snapshot.spot_low,
            "spot_high": snapshot.spot_high,
            "option_low": snapshot.option_low,
            "option_high": snapshot.option_high,
        }

    def _option_selection_result_to_dict(
        self,
        result: OptionSelectionResult,
    ) -> dict[str, object]:
        contract = result.selected_contract
        return {
            "selected": result.selected,
            "selected_contract": (
                {
                    "timestamp": contract.timestamp.isoformat(),
                    "symbol": contract.symbol,
                    "option_type": contract.option_type.value,
                    "strike": contract.strike,
                    "expiry": contract.expiry.isoformat(),
                    "bid": contract.bid,
                    "ask": contract.ask,
                    "ltp": contract.ltp,
                    "oi": contract.oi,
                    "volume": contract.volume,
                    "bid_ask_spread": contract.bid_ask_spread,
                }
                if contract is not None
                else None
            ),
            "selection_reason": result.selection_reason,
            "candidate_count": result.candidate_count,
        }

    def _recalculation_result_to_dict(self, result) -> dict[str, object]:
        return {
            "recalculated": result.recalculated,
            "reason": result.reason,
            "recalculated_start_strike": result.recalculated_start_strike,
            "recalculated_end_strike": result.recalculated_end_strike,
            "recalculated_ideal_premium": result.recalculated_ideal_premium,
            "recalculated_minimum_premium": result.recalculated_minimum_premium,
            "recalculated_entry_price": result.recalculated_entry_price,
            "source_rule": result.source_rule,
            "audit_notes": list(result.audit_notes),
        }

    def _recalculation_open_questions(
        self,
        unique_code: str,
    ) -> list[dict[str, object]]:
        return self._recalculation_audit_questions(unique_code, status="OPEN")

    def _recalculation_resolved_corrections(
        self,
        unique_code: str,
    ) -> list[dict[str, object]]:
        return self._recalculation_audit_questions(unique_code, status="RESOLVED")

    def _recalculation_audit_questions(
        self,
        unique_code: str,
        *,
        status: str,
    ) -> list[dict[str, object]]:
        if unique_code not in {
            "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
            "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        }:
            return []
        return [
            question
            for question in _load_importer_open_questions()
            if question.get("id") in S23_RECALC_OPEN_QUESTION_IDS
            and question.get("status") == status
        ]

    def _select_rules_for_monthly_status(
        self,
        strategy_root: Path,
        selected_branch_unique_codes: list[str],
    ) -> list[tuple[Path, StrategyRule]]:
        rules: list[tuple[Path, StrategyRule]] = []
        for strategy_folder in sorted(
            (path for path in strategy_root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        ):
            rule = load_strategy_rule(strategy_folder)
            if rule.unique_code in selected_branch_unique_codes:
                rules.append((strategy_folder, rule))
        return rules


@lru_cache(maxsize=1)
def _load_importer_open_questions() -> tuple[dict[str, Any], ...]:
    with IMPORTER_OPEN_QUESTIONS_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    questions = data.get("open_questions", [])
    if not isinstance(questions, list):
        return ()
    return tuple(question for question in questions if isinstance(question, dict))
