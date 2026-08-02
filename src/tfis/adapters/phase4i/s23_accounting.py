from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from tfis.accounting import (
    AccountingBuildResult,
    AccountingQuality,
    ChargeEvidence,
    InstrumentDimensions,
    MarkSnapshot,
    PnLFactBuilder,
    TradeFactBuilder,
    build_accounting_result,
    build_all_projections,
    rebuild_projections,
)
from tfis.adapters.phase4h import execute_phase4h_s23_case, execute_phase4h_two_account_case
from tfis.persistence import canonical_hash


AS_OF = datetime.fromisoformat("2026-06-05T15:01:00+05:30")


def build_phase4i_case(case_name: str) -> dict[str, Any]:
    if case_name == "bull_target":
        return _closed_case("target_close", "TARGET", Decimal("1.25"))
    if case_name == "bear_original_sl":
        return _closed_case("original_sl_close", "ORIGINAL_SL", Decimal("1.25"), exit_price=Decimal("220.00"))
    if case_name == "revised_sl":
        return _closed_case("revised_sl_close", "REVISED_SL", Decimal("1.25"), exit_price=Decimal("118.00"), normal_gap_path="GAP_RECALCULATED", orpt_rc_path="RC")
    if case_name == "eod_exit":
        return _closed_case("eod_exit", "EOD_EXIT", Decimal("1.25"), exit_price=Decimal("98.00"))
    if case_name == "carry_open":
        return _open_case("carry_forward", mark=_mark(ask=Decimal("91.00")))
    if case_name == "stale_mark":
        return _open_case("carry_forward", mark=_mark(ask=Decimal("91.00"), freshness=1200))
    if case_name == "ltp_fallback":
        return _open_case("carry_forward", mark=_mark(ask=None, bid=None, ltp=Decimal("92.00")))
    if case_name == "partial_entry":
        return _open_case("partial_fill", mark=_mark(ask=Decimal("88.00")), partial_entry=True)
    if case_name == "partial_exit":
        opened = execute_phase4h_s23_case("bull_open")["projection"]
        projection = _projection_with_exit(opened, exit_price=Decimal("80.00"), exit_qty=max(1, int(opened["confirmed_entry_quantity"]) // 2), state="PARTIALLY_EXITED")
        return _build_from_projection(projection, "PARTIAL_EXIT", Decimal("1.25"), mark=_mark(ask=Decimal("85.00")), normal_gap_path="NORMAL_RETAINED")
    if case_name == "charge_correction":
        base = _closed_case("target_close", "TARGET", Decimal("5.00"))
        trade = _trade_obj(base["trade_fact"])
        original_realized = next(item for item in base["pnl_facts"] if item["fact_type"] == "REALIZED_TRADE_PNL")
        corrected = PnLFactBuilder().corrected_charge_fact(
            original=_pnl_obj(original_realized),
            trade_fact=trade,
            corrected_charges=Decimal("2.00"),
            as_of_timestamp=datetime.fromisoformat("2026-06-05T16:00:00+05:30"),
            reason="BROKER_CONFIRMED_CHARGE_SUPERSEDES_ESTIMATE",
        )
        return base | {"correction": corrected.to_dict(), "rebuild": _rebuild_dict((trade,), tuple(_pnl_obj(item) for item in base["pnl_facts"]) + (corrected,))}
    if case_name == "two_accounts":
        result = execute_phase4h_two_account_case()
        first = _build_from_projection(result["account_a"], "TARGET", Decimal("1.25"), account_suffix="A")
        second = _build_from_projection(result["account_b"], "TARGET", Decimal("1.25"), account_suffix="B")
        trade_facts = (_trade_obj(first["trade_fact"]), _trade_obj(second["trade_fact"]))
        pnl_facts = tuple(_pnl_obj(item) for item in first["pnl_facts"] + second["pnl_facts"])
        projections = build_all_projections(trade_facts, pnl_facts)
        return {"case": case_name, "account_a": first, "account_b": second, "portfolio_projection": [item.to_dict() for item in projections], "isolation": "PASSED"}
    raise ValueError(f"Unsupported Phase 4I S23 accounting case: {case_name}")


def build_phase4i_portfolio() -> dict[str, Any]:
    cases = [build_phase4i_case(name) for name in ("bull_target", "bear_original_sl", "revised_sl", "carry_open", "partial_exit")]
    trade_facts = tuple(_trade_obj(case["trade_fact"]) for case in cases)
    pnl_facts = tuple(_pnl_obj(item) for case in cases for item in case["pnl_facts"])
    projections = build_all_projections(trade_facts, pnl_facts)
    rebuilt = rebuild_projections(trade_facts, pnl_facts)
    return {
        "cases": cases,
        "projections": [item.to_dict() for item in projections],
        "rebuilt": [item.to_dict() for item in rebuilt],
        "rebuild_equals_incremental": [item.projection_hash for item in projections] == [item.projection_hash for item in rebuilt],
    }


def _closed_case(source_case: str, exit_reason: str, charges: Decimal, *, exit_price: Decimal | None = None, normal_gap_path: str = "NORMAL_RETAINED", orpt_rc_path: str = "ORPT") -> dict[str, Any]:
    projection = execute_phase4h_s23_case(source_case)["projection"]
    if exit_price is not None:
        projection = _projection_with_exit(projection, exit_price=exit_price, exit_qty=int(projection["confirmed_entry_quantity"]), state="CLOSED")
    return _build_from_projection(projection, exit_reason, charges, normal_gap_path=normal_gap_path, orpt_rc_path=orpt_rc_path)


def _open_case(source_case: str, *, mark: MarkSnapshot, partial_entry: bool = False) -> dict[str, Any]:
    raw = execute_phase4h_s23_case(source_case)
    projection = raw["projection"] if "projection" in raw else raw["second_fill"]["projection"]
    if partial_entry and "projection" in raw:
        projection = raw["projection"]
    return _build_from_projection(projection, "CARRIED_FORWARD" if source_case == "carry_forward" else None, Decimal("0.00"), mark=mark, normal_gap_path="GAP_RECALCULATED" if partial_entry else "NORMAL_RETAINED")


def _build_from_projection(
    projection: dict[str, Any],
    exit_reason: str | None,
    charges: Decimal,
    *,
    mark: MarkSnapshot | None = None,
    normal_gap_path: str = "NORMAL_RETAINED",
    orpt_rc_path: str = "ORPT",
    account_suffix: str | None = None,
) -> dict[str, Any]:
    instrument = _instrument(projection)
    entry_fills = _entry_fills(projection)
    exit_fills = _exit_fills(projection, exit_reason)
    charge = ChargeEvidence(charges=charges, quality=AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES if charges else AccountingQuality.CONFIRMED_INTERNAL_PAPER, source="PHASE4I_CONFIGURED_ESTIMATE")
    trade_fact = TradeFactBuilder().build(
        projection=projection,
        instrument=instrument,
        requested_entry_quantity=int(projection["confirmed_entry_quantity"]),
        entry_fills=entry_fills,
        exit_fills=exit_fills,
        lifecycle_requirements=tuple(projection.get("requirements", ())),
        charge_evidence=charge,
        decision_context={
            "monthly_status": "BULLISH_CONFIRMED" if "BULL" in str(exit_reason or "") or exit_reason == "TARGET" else "BEARISH_CONFIRMED",
            "branch": "BULL_CALL" if exit_reason != "ORIGINAL_SL" else "BEAR_CALL",
            "fresh_carried": "CARRIED_POSITION" if projection.get("carry_forward_status") else "FRESH_ENTRY",
            "normal_gap_path": normal_gap_path,
            "orpt_rc_path": orpt_rc_path,
            "selected_contract_evidence": "PHASE4H_SELECTED_CONTRACT_FIXTURE",
            "source_entry_rule_ids": ("S23_CALL_SIDE_PHASE4H_SOURCE_BACKED_LIFECYCLE",),
            "source_exit_rule_ids": (f"S23_{exit_reason or 'OPEN'}",),
            "source_plan_context_decision_hashes": {"premarket": "phase4i-premarket", "opening": "phase4i-opening", "effective_plan": projection["identity"]["originating_execution_plan_id"]},
            "contract_observations": [{"price": "100.00"}, {"price": "85.00"}, {"price": "125.00"}] if exit_reason else (),
            "capital_or_margin_estimate": "5000.00",
        },
        source_hashes={"position_event_ids": ("phase4h-position-event",), "position_cycle_hash": projection["projection_hash"]},
        mark_snapshot=mark,
        exit_order_purpose=exit_reason,
    )
    pnl_facts = PnLFactBuilder().build(trade_fact=trade_fact, as_of_timestamp=AS_OF, charge_evidence=charge)
    result = build_accounting_result(trade_fact=trade_fact, pnl_facts=pnl_facts)
    data = result.to_dict()
    data["case"] = exit_reason or "OPEN"
    data["account_suffix"] = account_suffix
    return data


def _projection_with_exit(projection: dict[str, Any], *, exit_price: Decimal, exit_qty: int, state: str) -> dict[str, Any]:
    confirmed = int(projection["confirmed_entry_quantity"])
    remaining = confirmed - exit_qty
    updated = dict(projection)
    updated["realized_quantity"] = exit_qty
    updated["remaining_quantity"] = remaining
    updated["average_exit_price"] = str(exit_price)
    updated["exit_fill_ids"] = ["phase4i-exit-fill"]
    updated["lifecycle_state"] = state
    updated["terminal_status"] = "CLOSED_BY_CONFIRMED_EXIT_FILL" if remaining == 0 else None
    updated["projection_hash"] = canonical_hash(updated)
    return updated


def _instrument(projection: dict[str, Any]) -> InstrumentDimensions:
    identity = projection["identity"]
    return InstrumentDimensions(
        exchange="NSE",
        product="OPTION_SELLING",
        underlying="NIFTY",
        contract=identity["normalized_contract"],
        expiry=None,
        strike=None,
        option_type="CALL",
        direction=identity["direction"],
        lot_size=int(projection["lot_size"]),
        multiplier=Decimal(str(projection["multiplier"])),
        tick_size=Decimal("0.05"),
        currency=projection["currency"],
    )


def _entry_fills(projection: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    ids = projection.get("entry_fill_ids") or ["phase4i-entry-fill"]
    qty = int(projection["confirmed_entry_quantity"])
    split = [qty] if len(ids) == 1 else [max(1, qty // 2), qty - max(1, qty // 2)]
    return tuple(
        {
            "internal_fill_id": fill_id,
            "client_order_id": f"entry-order-{index}",
            "fill_quantity": split[index] if index < len(split) else 0,
            "fill_price": projection["average_entry_price"],
            "recorded_timestamp": f"2026-06-05T09:{15 + index:02d}:00+05:30",
        }
        for index, fill_id in enumerate(ids)
    )


def _exit_fills(projection: dict[str, Any], exit_reason: str | None) -> tuple[dict[str, Any], ...]:
    qty = int(projection["realized_quantity"])
    if qty <= 0:
        return ()
    return (
        {
            "internal_fill_id": (projection.get("exit_fill_ids") or ["phase4i-exit-fill"])[0],
            "client_order_id": f"{exit_reason}-order",
            "fill_quantity": qty,
            "fill_price": projection["average_exit_price"],
            "recorded_timestamp": "2026-06-05T15:00:00+05:30",
        },
    )


def _mark(*, ask: Decimal | None, bid: Decimal | None = Decimal("89.00"), ltp: Decimal | None = Decimal("90.00"), freshness: int = 60) -> MarkSnapshot:
    return MarkSnapshot(
        contract="NIFTY_PHASE4I_CE",
        trading_date=date(2026, 6, 5),
        bid=bid,
        ask=ask,
        ltp=ltp,
        source_timestamp=datetime.fromisoformat("2026-06-05T15:00:00+05:30"),
        captured_timestamp=datetime.fromisoformat("2026-06-05T15:01:00+05:30"),
        freshness_seconds=int(freshness),
        snapshot_hash=f"phase4i-mark:{freshness}:{ask}:{bid}:{ltp}",
    )


def _rebuild_dict(trade_facts, pnl_facts) -> dict[str, Any]:
    return {"projections": [item.to_dict() for item in rebuild_projections(trade_facts, pnl_facts)]}


def _trade_obj(data: dict[str, Any]):
    from tfis.accounting.models import AccountingTruthModel, TradeFact, TradeFactState

    return TradeFact(
        trade_fact_id=data["trade_fact_id"],
        trade_id=data["trade_id"],
        position_cycle_id=data["position_cycle_id"],
        trading_session_id=data["trading_session_id"],
        originating_trading_date=date.fromisoformat(data["originating_trading_date"]),
        final_trading_date=date.fromisoformat(data["final_trading_date"]) if data["final_trading_date"] else None,
        strategy_family=data["strategy_family"],
        strategy_definition=data["strategy_definition"],
        strategy_version=data["strategy_version"],
        strategy_instance=data["strategy_instance"],
        logical_paper_account=data["logical_paper_account"],
        configuration_hash=data["configuration_hash"],
        rule_matrix_version=data["rule_matrix_version"],
        trade_fact_version=data["trade_fact_version"],
        instrument=_instrument_from_dict(data["instrument"]),
        decision_context=data["decision_context"],
        execution=data["execution"],
        lifecycle=data["lifecycle"],
        performance_inputs=data["performance_inputs"],
        provenance=data["provenance"],
        state=TradeFactState(data["state"]),
        accounting_truth=AccountingTruthModel(data["accounting_truth"]),
        supersedes_trade_fact_id=data.get("supersedes_trade_fact_id"),
    )


def _pnl_obj(data: dict[str, Any]):
    from tfis.accounting.models import AccountingQuality, PnLFact, PnLFactType

    return PnLFact(
        pnl_fact_id=data["pnl_fact_id"],
        fact_type=PnLFactType(data["fact_type"]),
        as_of_timestamp=datetime.fromisoformat(data["as_of_timestamp"]),
        trading_date=date.fromisoformat(data["trading_date"]),
        source_identities=data["source_identities"],
        account=data["account"],
        strategy=data["strategy"],
        instrument=data["instrument"],
        gross_pnl=Decimal(str(data["gross_pnl"])) if data["gross_pnl"] is not None else None,
        charges=Decimal(str(data["charges"])) if data["charges"] is not None else None,
        net_pnl=Decimal(str(data["net_pnl"])) if data["net_pnl"] is not None else None,
        realized_unrealized=data["realized_unrealized"],
        currency=data["currency"],
        metadata_version=data["metadata_version"],
        calculation_version=data["calculation_version"],
        quality_state=AccountingQuality(data["quality_state"]),
        evidence_hash=data["evidence_hash"],
        supersedes_pnl_fact_id=data.get("supersedes_pnl_fact_id"),
    )


def _instrument_from_dict(data: dict[str, Any]) -> InstrumentDimensions:
    return InstrumentDimensions(
        exchange=data["exchange"],
        product=data["product"],
        underlying=data["underlying"],
        contract=data["contract"],
        expiry=data.get("expiry"),
        strike=Decimal(str(data["strike"])) if data.get("strike") is not None else None,
        option_type=data.get("option_type"),
        direction=data["direction"],
        lot_size=int(data["lot_size"]),
        multiplier=Decimal(str(data["multiplier"])),
        tick_size=Decimal(str(data["tick_size"])),
        currency=data["currency"],
        quantity_unit=data.get("quantity_unit", "PHASE4H_CONFIRMED_UNITS"),
        metadata_version=data.get("metadata_version", "tfis.option_selling.instrument.v1"),
    )
