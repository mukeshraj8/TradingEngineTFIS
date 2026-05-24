from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tfis.domain.trade_plan import TradePlan
from tfis.execution.order_plan import OrderIntent
from tfis.formulas import FormulaSafetyFinding
from tfis.market_structure.ohlc import OhlcBar
from tfis.risk.risk_policy import RiskDecision


@dataclass(frozen=True, slots=True)
class BacktestInput:
    strategy_path: Path
    daily_bars: list[OhlcBar]
    intraday_bars: list[OhlcBar] | None
    runtime_values: dict[str, object]
    lot_size: int
    trades_taken_today: int


@dataclass(frozen=True, slots=True)
class BacktestTradeResult:
    strategy_code: str
    trade_plan: TradePlan
    order_intent: OrderIntent
    risk_decision: RiskDecision
    validation: "BacktestValidation"
    accepted: bool
    reason: str


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    total_candidates: int
    accepted_trades: int
    rejected_trades: int
    rejection_reasons: dict[str, int]


@dataclass(frozen=True, slots=True)
class BacktestValidation:
    strategy_config_ok: bool
    formula_safety_findings: list[FormulaSafetyFinding]
