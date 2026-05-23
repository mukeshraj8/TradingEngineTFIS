from __future__ import annotations

from dataclasses import dataclass

from tfis.execution.order_plan import OrderIntent


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str
    checks: dict


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    max_lots_per_trade: int
    max_trades_per_day: int
    allow_short_options: bool
    paper_only: bool

    def evaluate_order(
        self,
        order_intent: OrderIntent,
        *,
        trades_taken_today: int,
    ) -> RiskDecision:
        checks = {
            "paper_only": self.paper_only,
            "max_lots_per_trade": self.max_lots_per_trade,
            "max_trades_per_day": self.max_trades_per_day,
            "trades_taken_today": trades_taken_today,
            "allow_short_options": self.allow_short_options,
            "requested_quantity": order_intent.quantity,
            "side": getattr(order_intent.side, "value", str(order_intent.side)),
        }

        if order_intent.quantity <= 0:
            return RiskDecision(
                approved=False,
                reason="Rejected: lot size must be positive",
                checks=checks,
            )

        if order_intent.quantity > self.max_lots_per_trade:
            return RiskDecision(
                approved=False,
                reason="Rejected: lot size exceeds max_lots_per_trade",
                checks=checks,
            )

        if trades_taken_today >= self.max_trades_per_day:
            return RiskDecision(
                approved=False,
                reason="Rejected: max_trades_per_day reached",
                checks=checks,
            )

        side_value = getattr(order_intent.side, "value", str(order_intent.side)).upper()
        if side_value == "SELL" and order_intent.option_type is not None and not self.allow_short_options:
            return RiskDecision(
                approved=False,
                reason="Rejected: short options are disabled",
                checks=checks,
            )

        return RiskDecision(
            approved=True,
            reason="Approved",
            checks=checks,
        )
