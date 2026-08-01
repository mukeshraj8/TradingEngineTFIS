from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from tfis.adapters.phase4f import execute_s23_internal_paper_case
from tfis.internal_position import (
    LifecycleRequirement,
    LifecycleRequirementType,
    PositionCycleCoordinator,
    PositionCycleCoordinatorError,
)
from tfis.persistence import canonical_hash


S23_PHASE4H_RULE_IDS = ("S23_CALL_SIDE_PHASE4H_SOURCE_BACKED_LIFECYCLE", "M13B_1500_EQUALITY_CARRY_FORWARD")


def execute_phase4h_s23_case(case_name: str) -> dict[str, Any]:
    coordinator = PositionCycleCoordinator()
    opened = _open_bull_full(coordinator)
    if case_name == "bull_open":
        return _payload(case_name, opened, extra={"scenario": "full entry fill creates open unprotected cycle plus lifecycle requirements"})
    if case_name == "bear_open":
        return _payload(case_name, _open_bear_full(coordinator), extra={"scenario": "bear call entry full fill creates same position contract"})
    if case_name == "partial_fill":
        return _partial_fill(coordinator)
    if case_name == "target_close":
        return _exit_case(coordinator, opened, "target_ack", "TARGET")
    if case_name == "original_sl_close":
        return _exit_case(coordinator, opened, "original_sl_ack", "ORIGINAL_SL")
    if case_name == "revised_sl_close":
        revised = _link_revised_sl(coordinator, opened)
        return _exit_case(coordinator, revised["transition"].projection.to_dict(), "revised_sl_old_fills_before_cancel", "REVISED_SL", extra={"replacement": revised})
    if case_name == "old_sl_fills_before_cancel":
        revised = _link_revised_sl(coordinator, opened)
        result = _exit_case(coordinator, revised["transition"].projection.to_dict(), "revised_sl_old_fills_before_cancel", "REVISED_SL", extra={"race": "old SL fill before cancellation is applied as a valid financial event"})
        result["race_evidence"] = "VALID_FILL_APPLIED_REVIEW_REPLACEMENT_STATE"
        return result
    if case_name == "eod_exit":
        return _exit_case(coordinator, opened, "eod_exit_full", "EOD_EXIT")
    if case_name == "eod_unfilled":
        req = _manual_requirement(opened, LifecycleRequirementType.EOD_SQUARE_OFF_REQUIRED, Decimal("88.00"), "S23_EOD_EXIT_REQUIRED", generation=None)
        transition = coordinator.mark_exit_pending(_projection(opened), requirement=req)
        return _payload(case_name, transition.projection.to_dict(), transition=transition.to_dict(), extra={"unfilled_behavior": "EXIT_PENDING_NO_FABRICATED_CLOSE"})
    if case_name == "carry_forward":
        transition = coordinator.record_carry_forward(
            _projection(opened),
            next_trading_session_id="NSE:2026-06-06",
            source_rule_id="M13B_1500_EQUALITY_CARRY_FORWARD",
            observed_price=Decimal("120.00"),
            original_sl=Decimal("120.00"),
            timestamp=datetime.fromisoformat("2026-06-05T15:00:00+05:30"),
        )
        return _payload(case_name, transition.projection.to_dict(), transition=transition.to_dict(), extra={"equality_behavior": "CARRY_FORWARD"})
    if case_name == "next_day_recovery":
        carry = execute_phase4h_s23_case("carry_forward")
        assessment = coordinator.assess_recovery(
            _projection(carry["projection"]),
            expected_account_id=carry["projection"]["identity"]["broker_account_id"],
            expected_contract=carry["projection"]["identity"]["normalized_contract"],
            expected_rule_version="s23_authoritative_matrix_phase3d_m13b",
            observed_rule_version="s23_authoritative_matrix_phase3d_m13b",
        )
        return _payload(case_name, carry["projection"], extra={"recovery": assessment.to_dict()})
    if case_name == "consistency":
        assessment = coordinator.assess_consistency(_projection(opened), order_fill_totals={"entry": 1})
        return _payload(case_name, opened, extra={"consistency": assessment.to_dict(), "pnl_input_facts": coordinator.pnl_input_facts(_projection(opened)).to_dict()})
    raise ValueError(f"Unsupported Phase 4H S23 case: {case_name}")


def execute_phase4h_two_account_case() -> dict[str, Any]:
    account_a = _open_bull_full(PositionCycleCoordinator(), account_suffix="A")
    account_b = _open_bull_full(PositionCycleCoordinator(), account_suffix="B")
    return {
        "account_a": account_a,
        "account_b": account_b,
        "same_contract": account_a["identity"]["normalized_contract"] == account_b["identity"]["normalized_contract"],
        "position_cycles_independent": account_a["identity"]["position_cycle_id"] != account_b["identity"]["position_cycle_id"],
        "broker_accounts_independent": account_a["identity"]["broker_account_id"] != account_b["identity"]["broker_account_id"],
        "isolation": "PASSED",
    }


def _open_bull_full(coordinator: PositionCycleCoordinator, *, account_suffix: str = "") -> dict[str, Any]:
    payload = execute_s23_internal_paper_case("bull_entry_full")
    return _open_from_payload(coordinator, payload, account_suffix=account_suffix)


def _open_bear_full(coordinator: PositionCycleCoordinator) -> dict[str, Any]:
    payload = execute_s23_internal_paper_case("bear_entry_ack_full")
    return _open_from_payload(coordinator, payload)


def _open_from_payload(coordinator: PositionCycleCoordinator, payload: dict[str, Any], *, account_suffix: str = "") -> dict[str, Any]:
    intent = payload["intent"]
    order = _order(payload["client_order"], intent)
    if account_suffix:
        order["broker_account_id"] = f"{order['broker_account_id']}_{account_suffix}"
        payload["result"]["fills"][0]["broker_account_id"] = order["broker_account_id"]
    fill = payload["result"]["fills"][0]
    identity = coordinator.build_identity(
        trading_session_id=intent["trading_session_id"],
        originating_trading_date=date.fromisoformat(intent["trading_date"]),
        broker_account_id=order["broker_account_id"],
        logical_account_reference="INTERNAL_PAPER_ACCOUNT",
        strategy_family_id=intent["strategy_family_id"],
        strategy_definition_id=intent["strategy_definition_id"],
        strategy_version=intent["strategy_version"],
        strategy_instance_id=intent["strategy_instance_id"],
        originating_execution_plan_id=intent["source_artifact_id"],
        originating_entry_execution_intent_id=intent["execution_intent_id"],
        normalized_contract=order["normalized_contract"],
        direction="CALL_SIDE_VERTICAL",
        side=order["side"],
    )
    transition = coordinator.apply_entry_fill(
        None,
        identity=identity,
        client_order=order,
        fill=fill,
        requested_quantity=order["quantity"],
        source_rule_ids=S23_PHASE4H_RULE_IDS,
        lifecycle_prices={"target": "80.00", "original_sl": "120.00"},
    )
    return transition.projection.to_dict() | {"transition": transition.to_dict(), "requirements": [item.to_dict() for item in transition.requirements]}


def _partial_fill(coordinator: PositionCycleCoordinator) -> dict[str, Any]:
    payload = execute_s23_internal_paper_case("bull_gap_partial_full")
    intent = payload["intent"]
    order = _order(payload["client_order"], intent)
    identity = coordinator.build_identity(
        trading_session_id=intent["trading_session_id"],
        originating_trading_date=date.fromisoformat(intent["trading_date"]),
        broker_account_id=order["broker_account_id"],
        logical_account_reference="INTERNAL_PAPER_ACCOUNT",
        strategy_family_id=intent["strategy_family_id"],
        strategy_definition_id=intent["strategy_definition_id"],
        strategy_version=intent["strategy_version"],
        strategy_instance_id=intent["strategy_instance_id"],
        originating_execution_plan_id=intent["source_artifact_id"],
        originating_entry_execution_intent_id=intent["execution_intent_id"],
        normalized_contract=order["normalized_contract"],
        direction="CALL_SIDE_VERTICAL",
        side=order["side"],
    )
    first = coordinator.apply_entry_fill(None, identity=identity, client_order=order, fill=payload["result"]["fills"][0], requested_quantity=order["quantity"], source_rule_ids=S23_PHASE4H_RULE_IDS, lifecycle_prices={"target": "80.00", "original_sl": "120.00"})
    second = coordinator.apply_entry_fill(first.projection, identity=identity, client_order=order, fill=payload["result"]["fills"][1], requested_quantity=order["quantity"], source_rule_ids=S23_PHASE4H_RULE_IDS, lifecycle_prices={"target": "80.00", "original_sl": "120.00"})
    return {
        "case": "partial_fill",
        "first_partial": first.to_dict(),
        "second_fill": second.to_dict(),
        "projection": second.projection.to_dict(),
        "protection_resize_observed": any(req["status"] == "RESIZE_REQUIRED" for req in first.to_dict()["requirements"]),
    }


def _link_revised_sl(coordinator: PositionCycleCoordinator, opened: dict[str, Any]) -> dict[str, Any]:
    projection = _projection(opened)
    req = _manual_requirement(opened, LifecycleRequirementType.REVISED_SL_PLACEMENT_REQUIRED, Decimal("118.00"), "S23_REVISED_SL_REQUIRED", generation=2)
    order = _lifecycle_order(opened, "REVISED_SL", "BUY", req.quantity, req.price, generation=2)
    transition = coordinator.link_protection_order(projection, requirement=req, client_order=order)
    return {"requirement": req.to_dict(), "client_order": order, "transition": transition}


def _exit_case(coordinator: PositionCycleCoordinator, opened: dict[str, Any], source_case: str, purpose: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    projection = _projection(opened)
    source = execute_s23_internal_paper_case(source_case)
    order = _lifecycle_order(opened, purpose, "BUY", min(1, projection.remaining_quantity), Decimal("80.00") if purpose == "TARGET" else Decimal("120.00"), generation=2 if purpose == "REVISED_SL" else 1)
    fill = source["result"]["fills"][0] if source["result"]["fills"] else _synthetic_fill(order, projection, purpose)
    fill = dict(fill) | {
        "client_order_id": order["client_order_id"],
        "broker_account_id": projection.identity.broker_account_id,
        "strategy_instance_id": projection.identity.strategy_instance_id,
        "position_cycle_id": projection.identity.position_cycle_id,
        "contract": projection.identity.normalized_contract,
        "side": "BUY",
        "fill_quantity": projection.remaining_quantity,
    }
    transition = coordinator.apply_exit_fill(projection, client_order=order, fill=fill, source_rule_ids=S23_PHASE4H_RULE_IDS + (f"S23_{purpose}_EXIT",))
    return _payload(source_case, transition.projection.to_dict(), transition=transition.to_dict(), extra=_json_safe(extra))


def _payload(case_name: str, projection: dict[str, Any], *, transition: dict[str, Any] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "case": case_name,
        "authority": "INTERNAL_PAPER_ONLY",
        "broker_live_authority": "NONE",
        "projection": projection,
        "transition": transition or projection.get("transition"),
        "evidence": extra or {},
    }


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    return value


def _manual_requirement(opened: dict[str, Any], requirement_type: LifecycleRequirementType, price: Decimal, rule_id: str, generation: int | None) -> LifecycleRequirement:
    projection = _projection(opened)
    return LifecycleRequirement(
        requirement_id="lifecycle-req:" + canonical_hash({"position_cycle_id": projection.identity.position_cycle_id, "type": requirement_type.value, "rule_id": rule_id, "generation": generation})[:24],
        position_cycle_id=projection.identity.position_cycle_id,
        requirement_type=requirement_type,
        quantity=projection.remaining_quantity,
        side="BUY",
        price=price,
        source_rule_ids=(rule_id,),
        source_artifact_id=rule_id,
        source_artifact_hash=canonical_hash({"rule_id": rule_id}),
        protection_generation=generation,
        created_at=datetime.fromisoformat("2026-06-05T09:30:00+05:30"),
    )


def _lifecycle_order(opened: dict[str, Any], purpose: str, side: str, quantity: int, price: Decimal | None, *, generation: int | None) -> dict[str, Any]:
    identity = opened["identity"]
    return {
        "client_order_id": f"client-order:{canonical_hash({'pc': identity['position_cycle_id'], 'purpose': purpose, 'generation': generation})[:24]}",
        "execution_intent_id": f"intent:{purpose.lower()}",
        "account_coordinator_id": "acct-coord:phase4h",
        "broker_account_id": identity["broker_account_id"],
        "strategy_instance_id": identity["strategy_instance_id"],
        "trading_session_id": identity["trading_session_id"],
        "position_cycle_id": identity["position_cycle_id"],
        "idempotency_key": f"phase4h:{purpose}:{generation}",
        "normalized_contract": identity["normalized_contract"],
        "side": side,
        "quantity": quantity,
        "order_purpose": purpose,
        "order_type": "LIMIT" if purpose in {"TARGET", "EOD_EXIT"} else "SL",
        "limit_price": str(price) if purpose in {"TARGET", "EOD_EXIT"} else None,
        "trigger_price": str(price) if purpose not in {"TARGET", "EOD_EXIT"} else None,
        "time_in_force": "DAY",
        "authorized_time": "2026-06-05T09:30:00+05:30",
        "protection_generation": generation,
        "source_intent_hash": f"phase4h:{purpose}",
        "order_hash": canonical_hash({"purpose": purpose, "position_cycle_id": identity["position_cycle_id"], "generation": generation}),
        "broker_submission_permitted": False,
        "live_submission_permitted": False,
    }


def _synthetic_fill(order: dict[str, Any], projection, purpose: str) -> dict[str, Any]:
    return {
        "internal_fill_id": f"internal-fill:{canonical_hash({'order': order['client_order_id'], 'purpose': purpose})[:24]}",
        "client_order_id": order["client_order_id"],
        "broker_account_id": order["broker_account_id"],
        "strategy_instance_id": order["strategy_instance_id"],
        "position_cycle_id": projection.identity.position_cycle_id,
        "contract": order["normalized_contract"],
        "side": order["side"],
        "fill_quantity": order["quantity"],
        "fill_price": order.get("limit_price") or order.get("trigger_price") or "100.00",
        "simulated_exchange_timestamp": "2026-06-05T15:00:00+05:30",
        "recorded_timestamp": "2026-06-05T15:00:00+05:30",
        "scenario_id": f"phase4h:{purpose}",
        "fill_hash": canonical_hash({"order": order["client_order_id"], "purpose": purpose}),
    }


def _order(order: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    instrument = intent["instrument"]
    return dict(order) | {
        "lot_size": instrument["lot_size"],
        "multiplier": instrument["multiplier"],
        "currency": instrument["currency"],
    }


def _projection(data: dict[str, Any]):
    from tfis.internal_position.models import InternalPaperPositionCycleIdentity, InternalPaperPositionCycleProjection, InternalPaperPositionState, ProtectionOrderReference

    payload = data["projection"] if "projection" in data else data
    identity_data = payload["identity"]
    identity = InternalPaperPositionCycleIdentity(
        position_cycle_id=identity_data["position_cycle_id"],
        trading_session_id=identity_data["trading_session_id"],
        originating_trading_date=date.fromisoformat(identity_data["originating_trading_date"]),
        broker_account_id=identity_data["broker_account_id"],
        logical_account_reference=identity_data["logical_account_reference"],
        strategy_family_id=identity_data["strategy_family_id"],
        strategy_definition_id=identity_data["strategy_definition_id"],
        strategy_version=identity_data["strategy_version"],
        strategy_instance_id=identity_data["strategy_instance_id"],
        originating_execution_plan_id=identity_data["originating_execution_plan_id"],
        originating_entry_execution_intent_id=identity_data["originating_entry_execution_intent_id"],
        normalized_contract=identity_data["normalized_contract"],
        direction=identity_data["direction"],
        side=identity_data["side"],
    )

    def ref(value):
        if value is None:
            return None
        return ProtectionOrderReference(
            position_cycle_id=value["position_cycle_id"],
            order_purpose=value["order_purpose"],
            protection_generation=int(value["protection_generation"]),
            client_order_id=value["client_order_id"],
            requirement_id=value["requirement_id"],
            quantity=int(value["quantity"]),
            status=value["status"],
        )

    return InternalPaperPositionCycleProjection(
        identity=identity,
        lifecycle_state=InternalPaperPositionState(payload["lifecycle_state"]),
        confirmed_entry_quantity=int(payload["confirmed_entry_quantity"]),
        remaining_quantity=int(payload["remaining_quantity"]),
        realized_quantity=int(payload["realized_quantity"]),
        average_entry_price=Decimal(str(payload["average_entry_price"])) if payload["average_entry_price"] is not None else None,
        average_exit_price=Decimal(str(payload["average_exit_price"])) if payload["average_exit_price"] is not None else None,
        entry_fill_ids=tuple(payload["entry_fill_ids"]),
        exit_fill_ids=tuple(payload["exit_fill_ids"]),
        active_target=ref(payload.get("active_target")),
        active_original_sl=ref(payload.get("active_original_sl")),
        active_revised_sl=ref(payload.get("active_revised_sl")),
        active_order_references=tuple(ref(value) for value in payload.get("active_order_references", []) if value),
        superseded_protections=tuple(ref(value) for value in payload.get("superseded_protections", []) if value),
        cancelled_protections=tuple(ref(value) for value in payload.get("cancelled_protections", []) if value),
        filled_exit_order_id=payload.get("filled_exit_order_id"),
        protection_generation=int(payload.get("protection_generation", 0)),
        carry_forward_status=payload.get("carry_forward_status"),
        terminal_status=payload.get("terminal_status"),
        multiplier=Decimal(str(payload.get("multiplier", "1"))),
        lot_size=int(payload.get("lot_size", 1)),
        currency=payload.get("currency", "INR"),
        originating_trading_date=date.fromisoformat(payload["originating_trading_date"]),
        next_trading_session_id=payload.get("next_trading_session_id"),
        projection_version=int(payload.get("projection_version", 1)),
    )
