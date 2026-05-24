from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from tfis.domain.trade_plan import TradePlan
from tfis.market_structure.ohlc import OhlcBar


class EodExitPolicy(str, Enum):
    MARK_NO_EXIT = "mark_no_exit"
    SQUARE_OFF_AT_CLOSE = "square_off_at_close"
    CARRY_FORWARD_PENDING = "carry_forward_pending"


@dataclass(frozen=True, slots=True)
class TradeLifecycleResult:
    entered: bool
    entry_price: float | None
    exit_price: float | None
    entry_timestamp: datetime | None
    exit_timestamp: datetime | None
    bars_held: int
    exit_reason: str
    pnl_points: float | None
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None
    notes: str
    quantity: int | None = None
    gross_pnl_points: float | None = None
    total_cost_points: float | None = None
    net_pnl_points: float | None = None
    gross_pnl_rupees: float | None = None
    cost_rupees: float | None = None
    net_pnl_rupees: float | None = None
    cumulative_net_pnl_rupees: float | None = None
    drawdown_rupees: float | None = None


class TradeLifecycleSimulator:
    """Simulates a first-pass options-sell lifecycle from offline intraday bars."""

    def __init__(
        self,
        eod_policy: EodExitPolicy = EodExitPolicy.MARK_NO_EXIT,
    ) -> None:
        self._eod_policy = eod_policy

    def simulate(
        self,
        trade_plan: TradePlan,
        intraday_option_bars: list[OhlcBar],
    ) -> TradeLifecycleResult:
        sorted_bars = sorted(intraday_option_bars, key=lambda bar: bar.timestamp)
        if not sorted_bars:
            return TradeLifecycleResult(
                entered=False,
                entry_price=None,
                exit_price=None,
                entry_timestamp=None,
                exit_timestamp=None,
                bars_held=0,
                exit_reason="NO_ENTRY",
                pnl_points=None,
                max_favorable_excursion=None,
                max_adverse_excursion=None,
                notes="No intraday option bars were provided for this candidate date",
            )

        entered = False
        entry_timestamp: datetime | None = None
        bars_held = 0
        max_favorable_excursion = 0.0
        max_adverse_excursion = 0.0
        for bar in sorted_bars:
            if not entered:
                if not self._price_touched(
                    bar,
                    trade_plan.entry_price,
                ):
                    continue
                entered = True
                entry_timestamp = bar.timestamp
                bars_held = 1
                max_favorable_excursion, max_adverse_excursion = self._update_excursions(
                    trade_plan.entry_price,
                    bar,
                    max_favorable_excursion,
                    max_adverse_excursion,
                )
                stop_hit = bar.high >= trade_plan.stoploss_price
                target_hit = bar.low <= trade_plan.target_price
                if stop_hit and target_hit:
                    return self._exit_result(
                        trade_plan=trade_plan,
                        exit_price=trade_plan.stoploss_price,
                        entry_timestamp=entry_timestamp,
                        exit_timestamp=bar.timestamp,
                        bars_held=bars_held,
                        exit_reason="STOPLOSS_HIT",
                        max_favorable_excursion=max_favorable_excursion,
                        max_adverse_excursion=max_adverse_excursion,
                        notes=(
                            "Entry and both exit thresholds were touched in the same bar; "
                            "conservative stoploss result applied"
                        ),
                    )
                if stop_hit:
                    return self._exit_result(
                        trade_plan=trade_plan,
                        exit_price=trade_plan.stoploss_price,
                        entry_timestamp=entry_timestamp,
                        exit_timestamp=bar.timestamp,
                        bars_held=bars_held,
                        exit_reason="STOPLOSS_HIT",
                        max_favorable_excursion=max_favorable_excursion,
                        max_adverse_excursion=max_adverse_excursion,
                        notes="Stoploss threshold hit on the entry bar",
                    )
                if target_hit:
                    return self._exit_result(
                        trade_plan=trade_plan,
                        exit_price=trade_plan.target_price,
                        entry_timestamp=entry_timestamp,
                        exit_timestamp=bar.timestamp,
                        bars_held=bars_held,
                        exit_reason="TARGET_HIT",
                        max_favorable_excursion=max_favorable_excursion,
                        max_adverse_excursion=max_adverse_excursion,
                        notes="Target threshold hit on the entry bar",
                    )
                continue

            bars_held += 1
            max_favorable_excursion, max_adverse_excursion = self._update_excursions(
                trade_plan.entry_price,
                bar,
                max_favorable_excursion,
                max_adverse_excursion,
            )
            stop_hit = bar.high >= trade_plan.stoploss_price
            target_hit = bar.low <= trade_plan.target_price
            if stop_hit and target_hit:
                return self._exit_result(
                    trade_plan=trade_plan,
                    exit_price=trade_plan.stoploss_price,
                    entry_timestamp=entry_timestamp,
                    exit_timestamp=bar.timestamp,
                    bars_held=bars_held,
                    exit_reason="STOPLOSS_HIT",
                    max_favorable_excursion=max_favorable_excursion,
                    max_adverse_excursion=max_adverse_excursion,
                    notes=(
                        "Both target and stoploss thresholds were touched in the same bar; "
                        "conservative stoploss result applied"
                    ),
                )
            if stop_hit:
                return self._exit_result(
                    trade_plan=trade_plan,
                    exit_price=trade_plan.stoploss_price,
                    entry_timestamp=entry_timestamp,
                    exit_timestamp=bar.timestamp,
                    bars_held=bars_held,
                    exit_reason="STOPLOSS_HIT",
                    max_favorable_excursion=max_favorable_excursion,
                    max_adverse_excursion=max_adverse_excursion,
                    notes="Stoploss threshold hit after entry",
                )
            if target_hit:
                return self._exit_result(
                    trade_plan=trade_plan,
                    exit_price=trade_plan.target_price,
                    entry_timestamp=entry_timestamp,
                    exit_timestamp=bar.timestamp,
                    bars_held=bars_held,
                    exit_reason="TARGET_HIT",
                    max_favorable_excursion=max_favorable_excursion,
                    max_adverse_excursion=max_adverse_excursion,
                    notes="Target threshold hit after entry",
                )

        if not entered:
            return TradeLifecycleResult(
                entered=False,
                entry_price=None,
                exit_price=None,
                entry_timestamp=None,
                exit_timestamp=None,
                bars_held=0,
                exit_reason="NO_ENTRY",
                pnl_points=None,
                max_favorable_excursion=None,
                max_adverse_excursion=None,
                notes="Entry price was never touched by the intraday option bars",
            )

        last_bar = sorted_bars[-1]
        if self._eod_policy == EodExitPolicy.SQUARE_OFF_AT_CLOSE:
            return self._exit_result(
                trade_plan=trade_plan,
                exit_price=last_bar.close,
                entry_timestamp=entry_timestamp,
                exit_timestamp=last_bar.timestamp,
                bars_held=bars_held,
                exit_reason="EOD_SQUARE_OFF",
                max_favorable_excursion=max_favorable_excursion,
                max_adverse_excursion=max_adverse_excursion,
                notes="Entry was hit and the position was squared off at the last available intraday close",
            )
        if self._eod_policy == EodExitPolicy.CARRY_FORWARD_PENDING:
            return TradeLifecycleResult(
                entered=True,
                entry_price=trade_plan.entry_price,
                exit_price=None,
                entry_timestamp=entry_timestamp,
                exit_timestamp=None,
                bars_held=bars_held,
                exit_reason="CARRY_FORWARD_PENDING",
                pnl_points=None,
                max_favorable_excursion=float(max_favorable_excursion),
                max_adverse_excursion=float(max_adverse_excursion),
                notes="Entry was hit but next-day carry-forward simulation is not implemented yet",
            )

        return TradeLifecycleResult(
            entered=True,
            entry_price=trade_plan.entry_price,
            exit_price=None,
            entry_timestamp=entry_timestamp,
            exit_timestamp=None,
            bars_held=bars_held,
            exit_reason="NO_EXIT",
            pnl_points=None,
            max_favorable_excursion=float(max_favorable_excursion),
            max_adverse_excursion=float(max_adverse_excursion),
            notes="Entry was hit but neither target nor stoploss was reached; marked as no-exit diagnostic state",
        )

    def _price_touched(self, bar: OhlcBar, price: float) -> bool:
        return bar.low <= price <= bar.high

    def _update_excursions(
        self,
        entry_price: float,
        bar: OhlcBar,
        current_max_favorable: float,
        current_max_adverse: float,
    ) -> tuple[float, float]:
        favorable = max(0.0, entry_price - bar.low)
        adverse = max(0.0, bar.high - entry_price)
        return max(current_max_favorable, favorable), max(current_max_adverse, adverse)

    def _exit_result(
        self,
        *,
        trade_plan: TradePlan,
        exit_price: float,
        entry_timestamp: datetime | None,
        exit_timestamp: datetime,
        bars_held: int,
        exit_reason: str,
        max_favorable_excursion: float,
        max_adverse_excursion: float,
        notes: str,
    ) -> TradeLifecycleResult:
        pnl_points = trade_plan.entry_price - exit_price
        return TradeLifecycleResult(
            entered=True,
            entry_price=trade_plan.entry_price,
            exit_price=exit_price,
            entry_timestamp=entry_timestamp,
            exit_timestamp=exit_timestamp,
            bars_held=bars_held,
            exit_reason=exit_reason,
            pnl_points=float(pnl_points),
            max_favorable_excursion=float(max_favorable_excursion),
            max_adverse_excursion=float(max_adverse_excursion),
            notes=notes,
        )
