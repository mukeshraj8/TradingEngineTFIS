from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Literal

from tfis.backtest.cost_model import CostModel
from tfis.backtest.hsre_s23_final_order_decision import (
    HsreS23FinalOrderDecisionBuilder,
    HsreS23FinalOrderDecisionPacket,
    hsre_s23_final_order_decision_packet_to_dict,
)
from tfis.backtest.nifty_hsre_data_adapter import (
    HistoricalOptionMinuteBar,
    HsreDataError,
    NiftyHsreHistoricalMarketDataProvider,
    parse_nifty_option_symbol,
)
from tfis.backtest.trade_lifecycle import EodExitPolicy, TradeLifecycleResult, TradeLifecycleSimulator
from tfis.domain.enums import OptionType
from tfis.domain.trade_plan import TradePlan
from tfis.market_structure.ohlc import OhlcBar


HsreS23LifecycleStatus = Literal[
    "ENTRY_NOT_TRIGGERED",
    "TRADE_CLOSED",
    "TRADE_OPEN_NO_EXIT",
    "LIFECYCLE_EVIDENCE_INCOMPLETE",
    "FINAL_ORDER_NOT_READY",
]


@dataclass(frozen=True, slots=True)
class HsreS23LifecycleBarEvidence:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    source_file: str


@dataclass(frozen=True, slots=True)
class HsreS23ContractSeriesAudit:
    contract: str
    source_file: str | None
    bar_count: int
    first_usable_bar: HsreS23LifecycleBarEvidence | None
    last_usable_bar: HsreS23LifecycleBarEvidence | None
    session_high: float | None
    session_high_timestamp: str | None
    session_low: float | None
    session_low_timestamp: str | None
    order_start_boundary: str
    chronology_policy: str


@dataclass(frozen=True, slots=True)
class HsreS23LifecycleEvent:
    timestamp: str | None
    event: str
    threshold: float | None
    price: float | None
    bar: HsreS23LifecycleBarEvidence | None
    target_state: str
    stoploss_state: str
    notes: str


@dataclass(frozen=True, slots=True)
class HsreS23PnlAudit:
    point_pnl_authoritative: bool
    gross_points: float
    total_cost_points: float
    net_points: float
    cost_model: str
    rupee_pnl_status: str
    rupee_pnl: float | None
    rupee_pnl_reason: str


@dataclass(frozen=True, slots=True)
class HsreS23TradeLifecyclePacket:
    session_date: str
    monthly_status: str | None
    branch: str | None
    contract: str | None
    status: HsreS23LifecycleStatus
    status_reason: str
    final_order_hash: str | None
    order_ready_time: str | None
    entry_threshold: float | None
    initial_target: float | None
    initial_stoploss: float | None
    entry_triggered: bool
    trigger_time: str | None
    trigger_bar: HsreS23LifecycleBarEvidence | None
    fill_price: float | None
    exit_time: str | None
    exit_price: float | None
    exit_reason: str | None
    contract_series_audit: HsreS23ContractSeriesAudit | None
    lifecycle_events: tuple[HsreS23LifecycleEvent, ...]
    lifecycle_result: dict[str, Any] | None
    pnl: HsreS23PnlAudit
    evidence_completeness: str
    data_provenance: dict[str, Any]
    no_lookahead_evidence: tuple[str, ...]


class HsreS23TradeLifecycleBuilder:
    """Run the accepted HSRE S23 final order through existing TFIS lifecycle semantics."""

    ENTRY_TRIGGER_COMPARATOR = "bar.low <= entry_price <= bar.high"
    TARGET_COMPARATOR = "bar.low <= target_price"
    STOPLOSS_COMPARATOR = "bar.high >= stoploss_price"
    FILL_PRICE_POLICY = "fill at planned entry_price when OHLC touches entry"

    def __init__(
        self,
        provider: NiftyHsreHistoricalMarketDataProvider,
        *,
        final_order_builder: HsreS23FinalOrderDecisionBuilder | None = None,
        lifecycle_simulator: TradeLifecycleSimulator | None = None,
        cost_model: CostModel | None = None,
        eod_policy: EodExitPolicy = EodExitPolicy.MARK_NO_EXIT,
    ) -> None:
        self.provider = provider
        self.final_order_builder = final_order_builder or HsreS23FinalOrderDecisionBuilder(provider)
        self.lifecycle_simulator = lifecycle_simulator or TradeLifecycleSimulator(eod_policy=eod_policy)
        self.cost_model = cost_model or CostModel()

    def build_for_session(
        self,
        *,
        session_date: date,
        planning_time: time = time(9, 16),
    ) -> HsreS23TradeLifecyclePacket:
        final_order = self.final_order_builder.build_for_session(
            session_date=session_date,
            planning_time=planning_time,
        )
        return self.build_from_final_order(final_order)

    def build_from_final_order(
        self,
        final_order: HsreS23FinalOrderDecisionPacket,
    ) -> HsreS23TradeLifecyclePacket:
        if final_order.final_effective_contract is None or final_order.final_effective_entry is None:
            return self._minimal_packet(
                final_order=final_order,
                status="FINAL_ORDER_NOT_READY",
                status_reason=final_order.status_reason,
            )
        if final_order.timing_authority is None:
            return self._minimal_packet(
                final_order=final_order,
                status="FINAL_ORDER_NOT_READY",
                status_reason="Final order packet lacks timing authority.",
            )

        session_date = date.fromisoformat(final_order.session_date)
        order_ready = datetime.combine(
            session_date,
            time.fromisoformat(final_order.timing_authority.effective_order_time),
        )
        identity = parse_nifty_option_symbol(final_order.final_effective_contract)
        all_contract_bars = self.provider.get_contract_session_bars(session_date, identity)
        usable_bars = tuple(bar for bar in all_contract_bars if bar.timestamp > order_ready)
        series_audit = self._series_audit(
            contract=final_order.final_effective_contract,
            bars=usable_bars,
            order_ready=order_ready,
        )
        if not usable_bars:
            return self._minimal_packet(
                final_order=final_order,
                status="LIFECYCLE_EVIDENCE_INCOMPLETE",
                status_reason="No selected-contract bars exist after the final order ready time.",
                series_audit=series_audit,
            )

        trade_plan = TradePlan(
            strategy_code="S23",
            symbol="NIFTY",
            option_type=identity.option_type,
            start_strike=None,
            end_strike=None,
            ideal_premium=None,
            minimum_premium=None,
            entry_price=float(final_order.final_effective_entry),
            target_price=float(final_order.final_effective_target),
            stoploss_price=float(final_order.final_effective_stoploss),
        )
        ohlc_bars = [self._to_ohlc(bar) for bar in usable_bars]
        lifecycle = self.lifecycle_simulator.simulate(trade_plan, ohlc_bars)
        lifecycle_with_costs = self.cost_model.apply_with_quantity(lifecycle, quantity=None)
        entry_bar = self._find_bar(usable_bars, lifecycle.entry_timestamp)
        exit_bar = self._find_bar(usable_bars, lifecycle.exit_timestamp)
        events = self._events(
            order_ready=order_ready,
            trade_plan=trade_plan,
            lifecycle=lifecycle_with_costs,
            entry_bar=entry_bar,
            exit_bar=exit_bar,
        )
        pnl = self._pnl(lifecycle_with_costs)
        if not lifecycle_with_costs.entered:
            status: HsreS23LifecycleStatus = "ENTRY_NOT_TRIGGERED"
            status_reason = (
                "Entry threshold was never touched by exact selected-contract bars "
                "after order activation."
            )
        elif lifecycle_with_costs.exit_price is None:
            status = "TRADE_OPEN_NO_EXIT"
            status_reason = lifecycle_with_costs.notes
        else:
            status = "TRADE_CLOSED"
            status_reason = lifecycle_with_costs.notes

        return HsreS23TradeLifecyclePacket(
            session_date=final_order.session_date,
            monthly_status=final_order.monthly_status,
            branch=final_order.branch,
            contract=final_order.final_effective_contract,
            status=status,
            status_reason=status_reason,
            final_order_hash=self.final_order_builder.stable_packet_hash(final_order),
            order_ready_time=order_ready.isoformat(),
            entry_threshold=trade_plan.entry_price,
            initial_target=trade_plan.target_price,
            initial_stoploss=trade_plan.stoploss_price,
            entry_triggered=lifecycle_with_costs.entered,
            trigger_time=lifecycle_with_costs.entry_timestamp.isoformat()
            if lifecycle_with_costs.entry_timestamp else None,
            trigger_bar=self._bar_evidence(entry_bar) if entry_bar is not None else None,
            fill_price=lifecycle_with_costs.entry_price,
            exit_time=lifecycle_with_costs.exit_timestamp.isoformat()
            if lifecycle_with_costs.exit_timestamp else None,
            exit_price=lifecycle_with_costs.exit_price,
            exit_reason=lifecycle_with_costs.exit_reason,
            contract_series_audit=series_audit,
            lifecycle_events=events,
            lifecycle_result=asdict(lifecycle_with_costs),
            pnl=pnl,
            evidence_completeness="COMPLETE_FOR_SAME_SESSION_LIFECYCLE",
            data_provenance={
                "final_order": hsre_s23_final_order_decision_packet_to_dict(final_order),
                "contract_source_file": series_audit.source_file,
                "business_components_reused": (
                    "HsreS23FinalOrderDecisionBuilder",
                    "TradeLifecycleSimulator",
                    "CostModel",
                ),
            },
            no_lookahead_evidence=(
                "contract_bars_filtered_to_exact_symbol",
                "contract_bars_filtered_to_timestamp_gt_order_ready_time",
                "trade_lifecycle_simulator_processes_sorted_bars_chronologically",
                "target_stoploss_evaluation_starts_only_after_entry_touch",
                "same_bar_target_stoploss_ambiguity_uses_existing_conservative_stoploss_policy",
            ),
        )

    @staticmethod
    def stable_packet_hash(packet: HsreS23TradeLifecyclePacket) -> str:
        encoded = json.dumps(
            hsre_s23_trade_lifecycle_packet_to_dict(packet, for_hash=True),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _minimal_packet(
        self,
        *,
        final_order: HsreS23FinalOrderDecisionPacket,
        status: HsreS23LifecycleStatus,
        status_reason: str,
        series_audit: HsreS23ContractSeriesAudit | None = None,
    ) -> HsreS23TradeLifecyclePacket:
        return HsreS23TradeLifecyclePacket(
            session_date=final_order.session_date,
            monthly_status=final_order.monthly_status,
            branch=final_order.branch,
            contract=final_order.final_effective_contract,
            status=status,
            status_reason=status_reason,
            final_order_hash=self.final_order_builder.stable_packet_hash(final_order)
            if final_order.final_effective_contract is not None else None,
            order_ready_time=None,
            entry_threshold=final_order.final_effective_entry,
            initial_target=final_order.final_effective_target,
            initial_stoploss=final_order.final_effective_stoploss,
            entry_triggered=False,
            trigger_time=None,
            trigger_bar=None,
            fill_price=None,
            exit_time=None,
            exit_price=None,
            exit_reason=None,
            contract_series_audit=series_audit,
            lifecycle_events=(),
            lifecycle_result=None,
            pnl=self._zero_pnl(),
            evidence_completeness=status,
            data_provenance={
                "final_order": hsre_s23_final_order_decision_packet_to_dict(final_order),
            },
            no_lookahead_evidence=(),
        )

    @staticmethod
    def _series_audit(
        *,
        contract: str,
        bars: tuple[HistoricalOptionMinuteBar, ...],
        order_ready: datetime,
    ) -> HsreS23ContractSeriesAudit:
        source_file = str(bars[0].source_file) if bars else None
        high_bar = max(bars, key=lambda bar: (bar.high, bar.timestamp)) if bars else None
        low_bar = min(bars, key=lambda bar: (bar.low, bar.timestamp)) if bars else None
        return HsreS23ContractSeriesAudit(
            contract=contract,
            source_file=source_file,
            bar_count=len(bars),
            first_usable_bar=HsreS23TradeLifecycleBuilder._bar_evidence(bars[0]) if bars else None,
            last_usable_bar=HsreS23TradeLifecycleBuilder._bar_evidence(bars[-1]) if bars else None,
            session_high=high_bar.high if high_bar is not None else None,
            session_high_timestamp=high_bar.timestamp.isoformat() if high_bar is not None else None,
            session_low=low_bar.low if low_bar is not None else None,
            session_low_timestamp=low_bar.timestamp.isoformat() if low_bar is not None else None,
            order_start_boundary=order_ready.isoformat(),
            chronology_policy=(
                "Bars must have timestamp strictly greater than the order-ready "
                "timestamp; the 09:24 minute is excluded for a 09:24:59 order."
            ),
        )

    @staticmethod
    def _events(
        *,
        order_ready: datetime,
        trade_plan: TradePlan,
        lifecycle: TradeLifecycleResult,
        entry_bar: HistoricalOptionMinuteBar | None,
        exit_bar: HistoricalOptionMinuteBar | None,
    ) -> tuple[HsreS23LifecycleEvent, ...]:
        events: list[HsreS23LifecycleEvent] = [
            HsreS23LifecycleEvent(
                timestamp=order_ready.isoformat(),
                event="ORDER_READY",
                threshold=trade_plan.entry_price,
                price=None,
                bar=None,
                target_state=f"target={trade_plan.target_price}",
                stoploss_state=f"stoploss={trade_plan.stoploss_price}",
                notes=(
                    "Waiting sell order becomes eligible; exact selected-contract "
                    "bars before this timestamp are excluded."
                ),
            )
        ]
        if not lifecycle.entered:
            events.append(
                HsreS23LifecycleEvent(
                    timestamp=None,
                    event="ENTRY_NOT_TRIGGERED",
                    threshold=trade_plan.entry_price,
                    price=None,
                    bar=None,
                    target_state="not_applicable",
                    stoploss_state="not_applicable",
                    notes=lifecycle.notes,
                )
            )
            return tuple(events)
        events.append(
            HsreS23LifecycleEvent(
                timestamp=lifecycle.entry_timestamp.isoformat()
                if lifecycle.entry_timestamp else None,
                event="ENTRY_TRIGGERED",
                threshold=trade_plan.entry_price,
                price=lifecycle.entry_price,
                bar=HsreS23TradeLifecycleBuilder._bar_evidence(entry_bar)
                if entry_bar is not None else None,
                target_state=f"active target={trade_plan.target_price}",
                stoploss_state=f"active stoploss={trade_plan.stoploss_price}",
                notes=(
                    f"Entry comparator: {HsreS23TradeLifecycleBuilder.ENTRY_TRIGGER_COMPARATOR}; "
                    f"fill policy: {HsreS23TradeLifecycleBuilder.FILL_PRICE_POLICY}."
                ),
            )
        )
        if lifecycle.exit_price is not None:
            events.append(
                HsreS23LifecycleEvent(
                    timestamp=lifecycle.exit_timestamp.isoformat()
                    if lifecycle.exit_timestamp else None,
                    event=lifecycle.exit_reason,
                    threshold=lifecycle.exit_price,
                    price=lifecycle.exit_price,
                    bar=HsreS23TradeLifecycleBuilder._bar_evidence(exit_bar)
                    if exit_bar is not None else None,
                    target_state=(
                        "hit" if lifecycle.exit_reason == "TARGET_HIT" else "not_hit_or_conservative_order"
                    ),
                    stoploss_state=(
                        "hit" if lifecycle.exit_reason == "STOPLOSS_HIT" else "not_hit"
                    ),
                    notes=lifecycle.notes,
                )
            )
        return tuple(events)

    def _pnl(self, lifecycle: TradeLifecycleResult) -> HsreS23PnlAudit:
        if not lifecycle.entered:
            return self._zero_pnl()
        gross = float(lifecycle.gross_pnl_points or 0.0)
        costs = float(lifecycle.total_cost_points or 0.0)
        net = float(lifecycle.net_pnl_points or 0.0)
        return HsreS23PnlAudit(
            point_pnl_authoritative=lifecycle.pnl_points is not None,
            gross_points=gross,
            total_cost_points=costs,
            net_points=net,
            cost_model=self._cost_model_label(),
            rupee_pnl_status="NOT_CERTIFIED",
            rupee_pnl=None,
            rupee_pnl_reason=(
                "Historical Jan-2024 quantity and lot-size effective-date treatment "
                "is not certified by this HSRE packet."
            ),
        )

    def _zero_pnl(self) -> HsreS23PnlAudit:
        return HsreS23PnlAudit(
            point_pnl_authoritative=True,
            gross_points=0.0,
            total_cost_points=0.0,
            net_points=0.0,
            cost_model=self._cost_model_label(),
            rupee_pnl_status="NOT_CERTIFIED",
            rupee_pnl=None,
            rupee_pnl_reason="No entry triggered; no authoritative historical quantity applied.",
        )

    def _cost_model_label(self) -> str:
        if self.cost_model.total_cost_points == 0:
            return "ZERO/default historical model"
        return (
            f"slippage_per_side={self.cost_model.slippage_points_per_side}; "
            f"brokerage={self.cost_model.brokerage_points_per_trade}; "
            f"other={self.cost_model.other_cost_points_per_trade}"
        )

    @staticmethod
    def _find_bar(
        bars: tuple[HistoricalOptionMinuteBar, ...],
        timestamp: datetime | None,
    ) -> HistoricalOptionMinuteBar | None:
        if timestamp is None:
            return None
        for bar in bars:
            if bar.timestamp == timestamp:
                return bar
        return None

    @staticmethod
    def _to_ohlc(bar: HistoricalOptionMinuteBar) -> OhlcBar:
        return OhlcBar(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )

    @staticmethod
    def _bar_evidence(bar: HistoricalOptionMinuteBar) -> HsreS23LifecycleBarEvidence:
        return HsreS23LifecycleBarEvidence(
            timestamp=bar.timestamp.isoformat(),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            source_file=str(bar.source_file),
        )


def hsre_s23_trade_lifecycle_packet_to_dict(
    packet: HsreS23TradeLifecyclePacket,
    *,
    for_hash: bool = False,
) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if hasattr(value, "__dataclass_fields__"):
            return {key: convert(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            result = {str(key): convert(item) for key, item in value.items()}
            if for_hash:
                for path_key in ("source_file", "source_files", "source_config_paths", "strategy_config_paths", "data_root"):
                    result.pop(path_key, None)
            return result
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value

    return convert(packet)
