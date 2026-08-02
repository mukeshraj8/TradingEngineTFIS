from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from tfis.persistence import canonical_hash

from .models import (
    AccountingBuildResult,
    AccountingProjection,
    AccountingQuality,
    ChargeEvidence,
    ExitReason,
    ExcursionQuality,
    InstrumentDimensions,
    MarkQuality,
    MarkSnapshot,
    MfeMaeResult,
    PnLFact,
    PnLFactType,
    TradeFact,
    TradeFactState,
    WinLossClassification,
)


class AccountingBuildError(RuntimeError):
    pass


CALCULATION_VERSION = "tfis.short_option_accounting.v1"
BREAKEVEN_TOLERANCE = Decimal("0.01")


def short_option_realized_pnl(entry_price: Decimal, exit_price: Decimal, quantity: int, multiplier: Decimal) -> Decimal:
    _validate_quantity_unit(quantity=quantity, multiplier=multiplier)
    return _money((entry_price - exit_price) * Decimal(quantity) * multiplier)


def short_option_unrealized_pnl(entry_price: Decimal, mark_price: Decimal, quantity: int, multiplier: Decimal) -> Decimal:
    _validate_quantity_unit(quantity=quantity, multiplier=multiplier)
    return _money((entry_price - mark_price) * Decimal(quantity) * multiplier)


def select_mark_for_position(*, side: str, mark: MarkSnapshot) -> tuple[Decimal | None, MarkQuality]:
    if mark.freshness_seconds < 0:
        raise AccountingBuildError("Invalid mark freshness.")
    if mark.freshness_seconds > 900:
        return None, MarkQuality.UNKNOWN_STALE_OR_UNAVAILABLE
    if side == "SELL" and mark.ask is not None:
        return mark.ask, MarkQuality.EXECUTABLE_SIDE
    if side == "BUY" and mark.bid is not None:
        return mark.bid, MarkQuality.EXECUTABLE_SIDE
    if mark.ltp is not None:
        return mark.ltp, MarkQuality.DEGRADED_LTP_FALLBACK
    return None, MarkQuality.UNKNOWN_STALE_OR_UNAVAILABLE


def classify_win_loss(*, net_pnl: Decimal | None, remaining_quantity: int, quality: AccountingQuality, tolerance: Decimal = BREAKEVEN_TOLERANCE) -> WinLossClassification:
    if remaining_quantity > 0:
        return WinLossClassification.OPEN
    if net_pnl is None or quality in {AccountingQuality.INVALID, AccountingQuality.UNKNOWN, AccountingQuality.PARTIAL_EVIDENCE}:
        return WinLossClassification.UNKNOWN_ACCOUNTING_STATE
    if net_pnl > tolerance:
        return WinLossClassification.WIN
    if net_pnl < -tolerance:
        return WinLossClassification.LOSS
    return WinLossClassification.BREAKEVEN


def derive_exit_reason(projection: Mapping[str, Any], exit_order_purpose: str | None = None) -> ExitReason:
    state = str(projection.get("lifecycle_state"))
    if state == "CARRIED_FORWARD":
        return ExitReason.CARRIED_FORWARD
    if int(projection.get("remaining_quantity", 0)) > 0 and not exit_order_purpose:
        return ExitReason.OPEN
    mapping = {
        "TARGET": ExitReason.TARGET,
        "ORIGINAL_SL": ExitReason.ORIGINAL_SL,
        "REVISED_SL": ExitReason.REVISED_SL,
        "EOD_EXIT": ExitReason.EOD_EXIT,
        "RISK_EXIT": ExitReason.RISK_EXIT,
        "OPERATOR_EXIT": ExitReason.OPERATOR_EXIT,
    }
    return mapping.get(str(exit_order_purpose), ExitReason.UNKNOWN)


class TradeFactBuilder:
    def build(
        self,
        *,
        projection: Mapping[str, Any],
        instrument: InstrumentDimensions,
        requested_entry_quantity: int,
        entry_fills: tuple[Mapping[str, Any], ...],
        exit_fills: tuple[Mapping[str, Any], ...],
        lifecycle_requirements: tuple[Mapping[str, Any], ...],
        charge_evidence: ChargeEvidence,
        decision_context: Mapping[str, Any],
        source_hashes: Mapping[str, str],
        mark_snapshot: MarkSnapshot | None = None,
        exit_order_purpose: str | None = None,
        configuration_hash: str = "phase4i-s23-config",
        rule_matrix_version: str = "s23_authoritative_matrix_phase3d_m13b",
        supersedes_trade_fact_id: str | None = None,
    ) -> TradeFact:
        identity = projection["identity"]
        self._validate_projection(projection, instrument, entry_fills, exit_fills)
        remaining = int(projection["remaining_quantity"])
        confirmed_entry = int(projection["confirmed_entry_quantity"])
        realized_qty = int(projection["realized_quantity"])
        avg_entry = _decimal_or_none(projection.get("average_entry_price"))
        avg_exit = _decimal_or_none(projection.get("average_exit_price"))
        first_entry, last_entry = _fill_window(entry_fills)
        first_exit, final_exit = _fill_window(exit_fills)
        final_trading_date = final_exit.date() if final_exit else None
        realized_gross = short_option_realized_pnl(avg_entry, avg_exit, realized_qty, instrument.multiplier) if avg_entry is not None and avg_exit is not None and realized_qty else Decimal("0.00")
        unrealized_gross, mark_quality = self._unrealized(projection, instrument, mark_snapshot)
        charges = charge_evidence.charges
        net_realized = None if charges is None else _money(realized_gross - charges)
        quality = _trade_quality(projection, charge_evidence, mark_quality)
        state = _trade_state(remaining=remaining, quality=quality, closed=remaining == 0)
        exit_reason = derive_exit_reason(projection, exit_order_purpose)
        win_loss = classify_win_loss(net_pnl=net_realized, remaining_quantity=remaining, quality=quality)
        duration = _duration(first_entry, final_exit or datetime.now(timezone.utc), invalid_if_before=True)
        mfe_mae = _mfe_mae(decision_context.get("contract_observations", ()), avg_entry)
        trade_id = f"trade:{identity['position_cycle_id']}"
        payload = {
            "trade_id": trade_id,
            "position_cycle_id": identity["position_cycle_id"],
            "projection_hash": projection["projection_hash"],
            "source_hashes": source_hashes,
            "supersedes": supersedes_trade_fact_id,
        }
        return TradeFact(
            trade_fact_id="trade-fact:" + canonical_hash(payload)[:24],
            trade_id=trade_id,
            position_cycle_id=identity["position_cycle_id"],
            trading_session_id=identity["trading_session_id"],
            originating_trading_date=date.fromisoformat(identity["originating_trading_date"]),
            final_trading_date=final_trading_date,
            strategy_family=identity["strategy_family_id"],
            strategy_definition=identity["strategy_definition_id"],
            strategy_version=identity["strategy_version"],
            strategy_instance=identity["strategy_instance_id"],
            logical_paper_account=identity["logical_account_reference"],
            configuration_hash=configuration_hash,
            rule_matrix_version=rule_matrix_version,
            trade_fact_version=CALCULATION_VERSION,
            instrument=instrument,
            decision_context=dict(decision_context)
            | {
                "planned_prices_are_not_pnl_inputs": True,
                "acknowledgements_affect_pnl": False,
                "quantity_unit": instrument.quantity_unit,
            },
            execution={
                "requested_entry_quantity": requested_entry_quantity,
                "confirmed_entry_quantity": confirmed_entry,
                "average_entry": avg_entry,
                "entry_fill_count": len(entry_fills),
                "first_entry_timestamp": first_entry,
                "last_entry_timestamp": last_entry,
                "confirmed_exit_quantity": realized_qty,
                "average_exit": avg_exit,
                "exit_fill_count": len(exit_fills),
                "first_exit_timestamp": first_exit,
                "final_exit_timestamp": final_exit,
                "remaining_quantity": remaining,
                "partial_fill": len(entry_fills) > 1 or confirmed_entry < requested_entry_quantity,
                "partial_exit": bool(exit_fills) and realized_qty < confirmed_entry,
            },
            lifecycle={
                "target_linked": any(req.get("requirement_type") == "TARGET_EXIT_REQUIRED" for req in lifecycle_requirements),
                "original_sl_linked": any(req.get("requirement_type") == "NORMAL_SL_PLACEMENT_REQUIRED" for req in lifecycle_requirements),
                "revised_sl_linked": any(req.get("requirement_type") == "REVISED_SL_PLACEMENT_REQUIRED" for req in lifecycle_requirements),
                "target_hit": exit_reason is ExitReason.TARGET,
                "original_sl_hit": exit_reason is ExitReason.ORIGINAL_SL,
                "revised_sl_hit": exit_reason is ExitReason.REVISED_SL,
                "eod_exit": exit_reason is ExitReason.EOD_EXIT,
                "carry_forward_count": 1 if exit_reason is ExitReason.CARRIED_FORWARD else 0,
                "terminal_state": projection["lifecycle_state"],
                "final_exit_reason": exit_reason.value,
                "win_loss": win_loss.value,
            },
            performance_inputs={
                "gross_realized_pnl": realized_gross,
                "provisional_charges": charges,
                "net_realized_pnl": net_realized,
                "current_unrealized_pnl": unrealized_gross,
                "mark_quality": mark_quality.value,
                "mfe_mae": mfe_mae.to_dict(),
                "duration_seconds": duration,
                "capital_or_margin_estimate": decision_context.get("capital_or_margin_estimate"),
                "accounting_quality": quality.value,
            },
            provenance={
                "source_order_ids": tuple(str(item.get("client_order_id")) for item in (*entry_fills, *exit_fills)),
                "source_fill_ids": tuple(str(item.get("internal_fill_id")) for item in (*entry_fills, *exit_fills)),
                "source_position_event_ids": tuple(source_hashes.get("position_event_ids", ())),
                "source_lifecycle_requirement_ids": tuple(str(item.get("requirement_id")) for item in lifecycle_requirements),
                "reconciliation_quality": "INTERNAL_PAPER_ONLY_NOT_BROKER_RECONCILED",
                "correction_source": "NONE" if supersedes_trade_fact_id is None else "PHASE4I_CORRECTION",
                "source_hashes": dict(source_hashes),
            },
            state=state,
            supersedes_trade_fact_id=supersedes_trade_fact_id,
        )

    def _validate_projection(self, projection: Mapping[str, Any], instrument: InstrumentDimensions, entry_fills: tuple[Mapping[str, Any], ...], exit_fills: tuple[Mapping[str, Any], ...]) -> None:
        if not projection:
            raise AccountingBuildError("Missing PositionCycle projection.")
        identity = projection["identity"]
        if identity["authority_classification"] != "INTERNAL_PAPER_ONLY":
            raise AccountingBuildError("Only internal-paper PositionCycle projections can be accounted in Phase 4I.")
        if identity["normalized_contract"] != instrument.contract:
            raise AccountingBuildError("Instrument metadata contract mismatch.")
        if instrument.quantity_unit != "PHASE4H_CONFIRMED_UNITS":
            raise AccountingBuildError("Ambiguous quantity unit.")
        confirmed = int(projection["confirmed_entry_quantity"])
        remaining = int(projection["remaining_quantity"])
        realized = int(projection["realized_quantity"])
        if confirmed < 0 or remaining < 0 or realized < 0 or remaining + realized != confirmed:
            raise AccountingBuildError("Position quantity inconsistency.")
        if confirmed and not entry_fills:
            raise AccountingBuildError("Missing entry fill evidence.")
        if realized and not exit_fills:
            raise AccountingBuildError("Missing exit fill evidence.")
        if realized > confirmed:
            raise AccountingBuildError("Over-exit accounting evidence.")
        _fill_window(entry_fills)
        _fill_window(exit_fills)

    def _unrealized(self, projection: Mapping[str, Any], instrument: InstrumentDimensions, mark_snapshot: MarkSnapshot | None) -> tuple[Decimal | None, MarkQuality]:
        remaining = int(projection["remaining_quantity"])
        if remaining <= 0:
            return Decimal("0.00"), MarkQuality.EXECUTABLE_SIDE
        if mark_snapshot is None:
            return None, MarkQuality.UNKNOWN_STALE_OR_UNAVAILABLE
        mark_price, quality = select_mark_for_position(side=projection["identity"]["side"], mark=mark_snapshot)
        if mark_price is None:
            return None, quality
        avg_entry = _decimal_or_none(projection.get("average_entry_price"))
        if avg_entry is None:
            raise AccountingBuildError("Missing average entry for unrealized PnL.")
        return short_option_unrealized_pnl(avg_entry, mark_price, remaining, instrument.multiplier), quality


class PnLFactBuilder:
    def build(self, *, trade_fact: TradeFact, as_of_timestamp: datetime, charge_evidence: ChargeEvidence, supersedes_pnl_fact_id: str | None = None) -> tuple[PnLFact, ...]:
        facts: list[PnLFact] = []
        perf = trade_fact.performance_inputs
        if Decimal(str(perf["gross_realized_pnl"])) != Decimal("0.00") or int(trade_fact.execution["confirmed_exit_quantity"]) > 0:
            facts.append(
                self._fact(
                    trade_fact=trade_fact,
                    fact_type=PnLFactType.REALIZED_TRADE_PNL,
                    as_of_timestamp=as_of_timestamp,
                    gross=_decimal_or_none(perf["gross_realized_pnl"]),
                    charges=charge_evidence.charges,
                    net=_decimal_or_none(perf["net_realized_pnl"]),
                    realized_unrealized="REALIZED",
                    quality=AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES if charge_evidence.quality is AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES else AccountingQuality.CONFIRMED_INTERNAL_PAPER,
                    supersedes=supersedes_pnl_fact_id,
                )
            )
        if int(trade_fact.execution["remaining_quantity"]) > 0:
            unrealized = _decimal_or_none(perf["current_unrealized_pnl"])
            facts.append(
                self._fact(
                    trade_fact=trade_fact,
                    fact_type=PnLFactType.UNREALIZED_POSITION_PNL,
                    as_of_timestamp=as_of_timestamp,
                    gross=unrealized,
                    charges=Decimal("0.00") if unrealized is not None else None,
                    net=unrealized,
                    realized_unrealized="UNREALIZED",
                    quality=AccountingQuality.PROVISIONAL_MARK if unrealized is not None else AccountingQuality.UNKNOWN,
                    supersedes=None,
                )
            )
        if charge_evidence.quality is AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES:
            facts.append(
                self._fact(
                    trade_fact=trade_fact,
                    fact_type=PnLFactType.CHARGE_ESTIMATE,
                    as_of_timestamp=as_of_timestamp,
                    gross=Decimal("0.00"),
                    charges=charge_evidence.charges,
                    net=-(charge_evidence.charges or Decimal("0.00")),
                    realized_unrealized="CHARGE",
                    quality=charge_evidence.quality,
                    supersedes=None,
                )
            )
        return tuple(facts)

    def corrected_charge_fact(self, *, original: PnLFact, trade_fact: TradeFact, corrected_charges: Decimal, as_of_timestamp: datetime, reason: str) -> PnLFact:
        gross = original.gross_pnl or Decimal("0.00")
        return self._fact(
            trade_fact=trade_fact,
            fact_type=PnLFactType.CHARGE_CORRECTION,
            as_of_timestamp=as_of_timestamp,
            gross=gross,
            charges=corrected_charges,
            net=_money(gross - corrected_charges),
            realized_unrealized="REALIZED",
            quality=AccountingQuality.CORRECTED,
            supersedes=original.pnl_fact_id,
            extra={"correction_reason": reason},
        )

    def _fact(
        self,
        *,
        trade_fact: TradeFact,
        fact_type: PnLFactType,
        as_of_timestamp: datetime,
        gross: Decimal | None,
        charges: Decimal | None,
        net: Decimal | None,
        realized_unrealized: str,
        quality: AccountingQuality,
        supersedes: str | None,
        extra: Mapping[str, Any] | None = None,
    ) -> PnLFact:
        evidence = {
            "trade_fact_id": trade_fact.trade_fact_id,
            "trade_fact_hash": trade_fact.fact_hash,
            "fact_type": fact_type.value,
            "gross": gross,
            "charges": charges,
            "net": net,
            "supersedes": supersedes,
            "extra": extra or {},
        }
        evidence_hash = canonical_hash(evidence)
        return PnLFact(
            pnl_fact_id="pnl-fact:" + canonical_hash(evidence)[:24],
            fact_type=fact_type,
            as_of_timestamp=as_of_timestamp,
            trading_date=trade_fact.final_trading_date or trade_fact.originating_trading_date,
            source_identities={
                "trade_fact_id": trade_fact.trade_fact_id,
                "position_cycle_id": trade_fact.position_cycle_id,
                "source_fill_ids": trade_fact.provenance["source_fill_ids"],
                "supersession_reason": (extra or {}).get("correction_reason"),
            },
            account=trade_fact.logical_paper_account,
            strategy=trade_fact.strategy_instance,
            instrument=trade_fact.instrument.to_dict(),
            gross_pnl=gross,
            charges=charges,
            net_pnl=net,
            realized_unrealized=realized_unrealized,
            currency=trade_fact.instrument.currency,
            metadata_version=trade_fact.instrument.metadata_version,
            calculation_version=CALCULATION_VERSION,
            quality_state=quality,
            evidence_hash=evidence_hash,
            supersedes_pnl_fact_id=supersedes,
        )


def build_accounting_result(*, trade_fact: TradeFact, pnl_facts: tuple[PnLFact, ...]) -> AccountingBuildResult:
    projections = build_all_projections((trade_fact,), pnl_facts)
    return AccountingBuildResult(trade_fact=trade_fact, pnl_facts=pnl_facts, projections=projections)


def build_all_projections(trade_facts: tuple[TradeFact, ...], pnl_facts: tuple[PnLFact, ...]) -> tuple[AccountingProjection, ...]:
    latest = _latest_non_superseded(pnl_facts)
    projections = [
        _summary_projection("DAILY_PORTFOLIO", {"trading_date": _single_or_all(str(f.trading_date) for f in latest)}, trade_facts, latest),
        _summary_projection("ACCOUNT", {"account": _single_or_all(f.account for f in latest)}, trade_facts, latest),
        _summary_projection("STRATEGY", {"strategy": _single_or_all(f.strategy for f in latest)}, trade_facts, latest),
        _summary_projection("INSTRUMENT", {"contract": _single_or_all(f.instrument["contract"] for f in latest)}, trade_facts, latest),
        _dimension_projection("EXIT_REASON", "final_exit_reason", trade_facts, latest),
        _dimension_projection("PATH", "normal_gap_path", trade_facts, latest),
    ]
    return tuple(projections)


def rebuild_projections(trade_facts: tuple[TradeFact, ...], pnl_facts: tuple[PnLFact, ...]) -> tuple[AccountingProjection, ...]:
    return build_all_projections(trade_facts, pnl_facts)


def build_closed_equity_drawdown(pnl_facts: tuple[PnLFact, ...]) -> dict[str, Any]:
    realized = sorted((fact for fact in _latest_non_superseded(pnl_facts) if fact.fact_type is PnLFactType.REALIZED_TRADE_PNL and fact.net_pnl is not None), key=lambda item: item.trading_date)
    cumulative = Decimal("0.00")
    high_water = Decimal("0.00")
    max_drawdown = Decimal("0.00")
    points: list[dict[str, Any]] = []
    for fact in realized:
        cumulative += fact.net_pnl or Decimal("0.00")
        high_water = max(high_water, cumulative)
        drawdown = high_water - cumulative
        max_drawdown = max(max_drawdown, drawdown)
        points.append({"trading_date": fact.trading_date.isoformat(), "cumulative_equity": str(_money(cumulative)), "high_water_mark": str(_money(high_water)), "drawdown": str(_money(drawdown))})
    return {"opening_baseline": "0.00", "points": points, "current_drawdown": str(_money(points[-1]["drawdown"] if points else Decimal("0.00"))), "maximum_drawdown": str(_money(max_drawdown)), "method": "DAILY_CLOSED_EQUITY_CURVE"}


def _summary_projection(kind: str, dimensions: Mapping[str, Any], trade_facts: tuple[TradeFact, ...], pnl_facts: tuple[PnLFact, ...]) -> AccountingProjection:
    metrics = _metrics(trade_facts, pnl_facts)
    return AccountingProjection(
        projection_id=f"accounting-projection:{kind.lower()}:{canonical_hash({'dimensions': dimensions, 'metrics': metrics})[:16]}",
        projection_type=kind,
        dimensions=dimensions,
        metrics=metrics,
        source_fact_ids=tuple(fact.pnl_fact_id for fact in pnl_facts),
        watermark=canonical_hash({"trade_facts": [fact.fact_hash for fact in trade_facts], "pnl_facts": [fact.fact_hash for fact in pnl_facts]}),
        quality=AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES if any(fact.quality_state is AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES for fact in pnl_facts) else AccountingQuality.CONFIRMED_INTERNAL_PAPER,
    )


def _dimension_projection(kind: str, dimension: str, trade_facts: tuple[TradeFact, ...], pnl_facts: tuple[PnLFact, ...]) -> AccountingProjection:
    grouped: dict[str, Decimal] = {}
    for trade in trade_facts:
        key = str(trade.lifecycle.get(dimension) or trade.decision_context.get(dimension) or "UNKNOWN")
        grouped.setdefault(key, Decimal("0.00"))
    for fact in pnl_facts:
        if fact.net_pnl is not None:
            key = "UNKNOWN"
            for trade in trade_facts:
                if trade.trade_fact_id == fact.source_identities["trade_fact_id"]:
                    key = str(trade.lifecycle.get(dimension) or trade.decision_context.get(dimension) or "UNKNOWN")
                    break
            grouped[key] = grouped.get(key, Decimal("0.00")) + fact.net_pnl
    return AccountingProjection(
        projection_id=f"accounting-projection:{kind.lower()}:{canonical_hash(grouped)[:16]}",
        projection_type=kind,
        dimensions={"dimension": dimension},
        metrics={key: str(_money(value)) for key, value in sorted(grouped.items())},
        source_fact_ids=tuple(fact.pnl_fact_id for fact in pnl_facts),
        watermark=canonical_hash(grouped),
        quality=AccountingQuality.CONFIRMED_INTERNAL_PAPER,
    )


def _metrics(trade_facts: tuple[TradeFact, ...], pnl_facts: tuple[PnLFact, ...]) -> dict[str, Any]:
    realized = [fact for fact in pnl_facts if fact.fact_type is PnLFactType.REALIZED_TRADE_PNL and fact.net_pnl is not None]
    unrealized = [fact for fact in pnl_facts if fact.fact_type is PnLFactType.UNREALIZED_POSITION_PNL and fact.net_pnl is not None]
    wins = [trade for trade in trade_facts if trade.lifecycle.get("win_loss") == "WIN"]
    losses = [trade for trade in trade_facts if trade.lifecycle.get("win_loss") == "LOSS"]
    breakeven = [trade for trade in trade_facts if trade.lifecycle.get("win_loss") == "BREAKEVEN"]
    open_trades = [trade for trade in trade_facts if int(trade.execution["remaining_quantity"]) > 0]
    win_values = [fact.net_pnl for fact in realized if fact.net_pnl is not None and fact.net_pnl > 0]
    loss_values = [abs(fact.net_pnl) for fact in realized if fact.net_pnl is not None and fact.net_pnl < 0]
    gross = sum((fact.gross_pnl or Decimal("0.00")) for fact in pnl_facts)
    net = sum((fact.net_pnl or Decimal("0.00")) for fact in pnl_facts)
    realized_net = sum((fact.net_pnl or Decimal("0.00")) for fact in realized)
    unrealized_net = sum((fact.net_pnl or Decimal("0.00")) for fact in unrealized)
    avg_winner = _average(win_values)
    avg_loser = _average(loss_values)
    denominator = len(wins) + len(losses) + len(breakeven)
    win_rate = Decimal(len(wins)) / Decimal(denominator) if denominator else Decimal("0")
    profit_factor = (sum(win_values) / sum(loss_values)) if loss_values and sum(loss_values) else None
    loss_rate = Decimal(len(losses)) / Decimal(denominator) if denominator else Decimal("0")
    expectancy = (win_rate * (avg_winner or Decimal("0"))) - (loss_rate * (avg_loser or Decimal("0")))
    drawdown = build_closed_equity_drawdown(tuple(realized))
    return {
        "total_trades": len(trade_facts),
        "open_trades": len(open_trades),
        "closed_trades": len(trade_facts) - len(open_trades),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate": str(_money(win_rate)),
        "gross_pnl": str(_money(gross)),
        "net_pnl": str(_money(net)),
        "realized_pnl": str(_money(realized_net)),
        "unrealized_pnl": str(_money(unrealized_net)),
        "average_winner": str(_money(avg_winner or Decimal("0"))),
        "average_loser": str(_money(avg_loser or Decimal("0"))),
        "payoff_ratio": str(_money((avg_winner / avg_loser) if avg_winner is not None and avg_loser not in (None, Decimal("0")) else Decimal("0"))),
        "profit_factor": str(_money(profit_factor)) if profit_factor is not None else None,
        "expectancy": str(_money(expectancy)),
        "current_drawdown": drawdown["current_drawdown"],
        "maximum_closed_equity_drawdown": drawdown["maximum_drawdown"],
    }


def _latest_non_superseded(facts: tuple[PnLFact, ...]) -> tuple[PnLFact, ...]:
    superseded = {fact.supersedes_pnl_fact_id for fact in facts if fact.supersedes_pnl_fact_id}
    return tuple(fact for fact in facts if fact.pnl_fact_id not in superseded)


def _trade_quality(projection: Mapping[str, Any], charge: ChargeEvidence, mark_quality: MarkQuality) -> AccountingQuality:
    if projection.get("terminal_status") == "CLOSED_BY_CONFIRMED_EXIT_FILL":
        if charge.quality is AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES:
            return AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES
        return AccountingQuality.ACCOUNTING_COMPLETE
    if mark_quality is MarkQuality.UNKNOWN_STALE_OR_UNAVAILABLE:
        return AccountingQuality.PARTIAL_EVIDENCE
    return AccountingQuality.PROVISIONAL_MARK


def _trade_state(*, remaining: int, quality: AccountingQuality, closed: bool) -> TradeFactState:
    if quality is AccountingQuality.INVALID:
        return TradeFactState.INVALID
    if closed and quality is AccountingQuality.ACCOUNTING_COMPLETE:
        return TradeFactState.CLOSED_ACCOUNTING_COMPLETE
    if closed:
        return TradeFactState.CLOSED_PROVISIONAL
    if quality in {AccountingQuality.PROVISIONAL_MARK, AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES, AccountingQuality.PARTIAL_EVIDENCE}:
        return TradeFactState.OPEN_PROVISIONAL
    return TradeFactState.OPEN_ACCOUNTING_COMPLETE if remaining else TradeFactState.UNKNOWN_ACCOUNTING_STATE


def _fill_window(fills: tuple[Mapping[str, Any], ...]) -> tuple[datetime | None, datetime | None]:
    if not fills:
        return None, None
    timestamps = [datetime.fromisoformat(str(fill["recorded_timestamp"])) for fill in fills]
    if timestamps != sorted(timestamps):
        raise AccountingBuildError("Fill timestamps are inconsistent.")
    return timestamps[0], timestamps[-1]


def _duration(start: datetime | None, end: datetime | None, *, invalid_if_before: bool) -> int | None:
    if start is None or end is None:
        return None
    if invalid_if_before and end < start:
        raise AccountingBuildError("Invalid timestamp order.")
    return int((end - start).total_seconds())


def _mfe_mae(observations: Any, entry: Decimal | None) -> MfeMaeResult:
    if entry is None or not observations:
        return MfeMaeResult(mfe=None, mae=None, quality=ExcursionQuality.UNAVAILABLE, observation_count=0)
    prices = [Decimal(str(item["price"])) for item in observations if "price" in item]
    if not prices:
        return MfeMaeResult(mfe=None, mae=None, quality=ExcursionQuality.UNAVAILABLE, observation_count=0)
    favorable = max(entry - price for price in prices)
    adverse = max(price - entry for price in prices)
    quality = ExcursionQuality.COMPLETE if len(prices) >= 3 else ExcursionQuality.PARTIAL
    return MfeMaeResult(mfe=_money(favorable), mae=_money(adverse), quality=quality, observation_count=len(prices))


def _validate_quantity_unit(*, quantity: int, multiplier: Decimal) -> None:
    if quantity < 0:
        raise AccountingBuildError("Quantity cannot be negative.")
    if multiplier <= 0:
        raise AccountingBuildError("Invalid multiplier.")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _average(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values) / Decimal(len(values))


def _single_or_all(values: Any) -> str:
    unique = sorted({str(value) for value in values})
    return unique[0] if len(unique) == 1 else "ALL"
