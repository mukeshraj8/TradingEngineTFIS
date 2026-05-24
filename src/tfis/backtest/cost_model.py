from __future__ import annotations

from dataclasses import dataclass, replace

from tfis.backtest.trade_lifecycle import TradeLifecycleResult


@dataclass(frozen=True, slots=True)
class CostModel:
    slippage_points_per_side: float = 0.0
    brokerage_points_per_trade: float = 0.0
    other_cost_points_per_trade: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "slippage_points_per_side",
            "brokerage_points_per_trade",
            "other_cost_points_per_trade",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")

    @property
    def total_cost_points(self) -> float:
        return float(
            self.brokerage_points_per_trade
            + self.other_cost_points_per_trade
            + (2 * self.slippage_points_per_side)
        )

    def apply(self, result: TradeLifecycleResult) -> TradeLifecycleResult:
        return self.apply_with_quantity(result, quantity=result.quantity)

    def apply_with_quantity(
        self,
        result: TradeLifecycleResult,
        *,
        quantity: int | None,
    ) -> TradeLifecycleResult:
        normalized_quantity = int(quantity) if quantity is not None else None
        if result.pnl_points is None:
            return replace(
                result,
                quantity=normalized_quantity,
                gross_pnl_points=None,
                total_cost_points=None,
                net_pnl_points=None,
                gross_pnl_rupees=None,
                cost_rupees=None,
                net_pnl_rupees=None,
            )

        gross_pnl_points = float(result.pnl_points)
        total_cost_points = self.total_cost_points
        net_pnl_points = gross_pnl_points - total_cost_points
        gross_pnl_rupees = None
        cost_rupees = None
        net_pnl_rupees = None
        if normalized_quantity is not None:
            gross_pnl_rupees = gross_pnl_points * normalized_quantity
            cost_rupees = total_cost_points * normalized_quantity
            net_pnl_rupees = net_pnl_points * normalized_quantity
        return replace(
            result,
            quantity=normalized_quantity,
            gross_pnl_points=gross_pnl_points,
            total_cost_points=total_cost_points,
            net_pnl_points=net_pnl_points,
            gross_pnl_rupees=gross_pnl_rupees,
            cost_rupees=cost_rupees,
            net_pnl_rupees=net_pnl_rupees,
        )
